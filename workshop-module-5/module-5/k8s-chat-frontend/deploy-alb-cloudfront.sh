#!/bin/bash

# K8s Chat Frontend - ALB + CloudFront Deployment
# Creates ALB → EC2:8501 with CloudFront CDN for external HTTPS access
#
# Architecture:
#   Browser (HTTPS) → CloudFront (*.cloudfront.net) → ALB (HTTP:80) → EC2:8501 (Streamlit)
#
# Security: ALB only accepts traffic from CloudFront managed prefix list

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
AWS_REGION=${AWS_REGION:-us-west-2}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log_info "Starting K8s Chat Frontend ALB + CloudFront Deployment"
log_info "AWS Region: $AWS_REGION"

# ==========================================================================
# Step 1: Validate Prerequisites
# ==========================================================================
log_info "Step 1: Validating prerequisites..."

for cmd in aws jq curl; do
    if ! command -v $cmd &> /dev/null; then
        log_error "$cmd is not installed. Please install it first."
        exit 1
    fi
done

if ! aws sts get-caller-identity &> /dev/null; then
    log_error "AWS credentials not configured. Please run 'aws configure' first."
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log_success "Prerequisites validated. AWS Account ID: $AWS_ACCOUNT_ID"

# ==========================================================================
# Step 2: Infrastructure Discovery
# ==========================================================================
log_info "Step 2: Discovering infrastructure..."

# Allow manual override via environment variable
if [ -n "${INSTANCE_ID:-}" ]; then
    log_info "Using provided INSTANCE_ID: $INSTANCE_ID"
else

# Find the EC2 instance running the K8s chat frontend (tagged or running Streamlit on 8501)
# First try to find by Name tag pattern
INSTANCE_ID=$(aws ec2 describe-instances \
    --region $AWS_REGION \
    --filters "Name=tag:Name,Values=*Chat-Frontend*,*chat-frontend*" "Name=instance-state-name,Values=running" \
    --query "Reservations[0].Instances[0].InstanceId" --output text 2>/dev/null)

if [ "$INSTANCE_ID" == "None" ] || [ -z "$INSTANCE_ID" ]; then
    # Try broader search - look for instances with sample-app or NetAIOps tag
    INSTANCE_ID=$(aws ec2 describe-instances \
        --region $AWS_REGION \
        --filters "Name=tag:Name,Values=*ChatFrontend*,*chat*frontend*,*streamlit*" "Name=instance-state-name,Values=running" \
        --query "Reservations[0].Instances[0].InstanceId" --output text 2>/dev/null)
fi

if [ "$INSTANCE_ID" == "None" ] || [ -z "$INSTANCE_ID" ]; then
    # Last resort: find any instance from the NetAIOps stack that might be the chat frontend
    INSTANCE_ID=$(aws ec2 describe-instances \
        --region $AWS_REGION \
        --filters "Name=tag:aws:cloudformation:stack-name,Values=*sample-app*" "Name=instance-state-name,Values=running" \
        --query "Reservations[].Instances[].[InstanceId,Tags[?Key=='Name'].Value|[0]]" --output text 2>/dev/null | head -1 | awk '{print $1}')
fi

if [ "$INSTANCE_ID" == "None" ] || [ -z "$INSTANCE_ID" ]; then
    log_error "Could not find K8s Chat Frontend EC2 instance."
    log_error "Please set INSTANCE_ID environment variable manually:"
    log_error "  INSTANCE_ID=i-xxxx bash $0"
    exit 1
fi

log_info "Found EC2 instance: $INSTANCE_ID"

fi  # end of INSTANCE_ID discovery

# Get instance details
INSTANCE_INFO=$(aws ec2 describe-instances \
    --region $AWS_REGION \
    --instance-ids $INSTANCE_ID \
    --query "Reservations[0].Instances[0].[VpcId,SubnetId,SecurityGroups[0].GroupId]" --output text)

VPC_ID=$(echo "$INSTANCE_INFO" | awk '{print $1}')
INSTANCE_SUBNET_ID=$(echo "$INSTANCE_INFO" | awk '{print $2}')
INSTANCE_SG_ID=$(echo "$INSTANCE_INFO" | awk '{print $3}')

if [ -z "$VPC_ID" ] || [ "$VPC_ID" == "None" ]; then
    log_error "Could not determine VPC ID from instance $INSTANCE_ID"
    exit 1
fi

log_info "VPC: $VPC_ID"
log_info "Instance Subnet: $INSTANCE_SUBNET_ID"
log_info "Instance Security Group: $INSTANCE_SG_ID"

# Get the AZ of the instance
INSTANCE_AZ=$(aws ec2 describe-subnets \
    --region $AWS_REGION \
    --subnet-ids $INSTANCE_SUBNET_ID \
    --query "Subnets[0].AvailabilityZone" --output text)

log_info "Instance AZ: $INSTANCE_AZ"

# Find 2 public subnets in different AZs for the ALB
SUBNET_INFO=$(aws ec2 describe-subnets \
    --region $AWS_REGION \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query "Subnets[].[SubnetId,AvailabilityZone,MapPublicIpOnLaunch]" --output text)

if [ -z "$SUBNET_INFO" ]; then
    log_error "No subnets found in VPC $VPC_ID"
    exit 1
fi

# Get unique AZs with public subnets
SUBNET_1=""
SUBNET_2=""
AZ_1=""
AZ_2=""

# First pick a public subnet in the instance's AZ
SUBNET_1=$(echo "$SUBNET_INFO" | awk -v az="$INSTANCE_AZ" '$2 == az && $3 == "True" {print $1; exit}')
AZ_1="$INSTANCE_AZ"

# Then pick a public subnet in a different AZ
while IFS=$'\t' read -r sid az pub; do
    if [ "$pub" == "True" ] && [ "$az" != "$AZ_1" ] && [ -z "$SUBNET_2" ]; then
        SUBNET_2="$sid"
        AZ_2="$az"
    fi
done <<< "$SUBNET_INFO"

# If no public subnet in instance AZ, pick any two public subnets
if [ -z "$SUBNET_1" ]; then
    log_warning "No public subnet in instance AZ $INSTANCE_AZ, finding alternatives..."
    SUBNET_1=""
    SUBNET_2=""
    while IFS=$'\t' read -r sid az pub; do
        if [ "$pub" == "True" ]; then
            if [ -z "$SUBNET_1" ]; then
                SUBNET_1="$sid"
                AZ_1="$az"
            elif [ -z "$SUBNET_2" ] && [ "$az" != "$AZ_1" ]; then
                SUBNET_2="$sid"
                AZ_2="$az"
            fi
        fi
    done <<< "$SUBNET_INFO"
fi

if [ -z "$SUBNET_1" ] || [ -z "$SUBNET_2" ]; then
    log_error "Could not find 2 public subnets in different AZs. ALB requires at least 2."
    exit 1
fi

log_info "ALB Subnets: $SUBNET_1 ($AZ_1), $SUBNET_2 ($AZ_2)"

# Verify Internet Gateway exists
IGW_ID=$(aws ec2 describe-internet-gateways \
    --region $AWS_REGION \
    --filters "Name=attachment.vpc-id,Values=$VPC_ID" \
    --query "InternetGateways[0].InternetGatewayId" --output text 2>/dev/null)

if [ "$IGW_ID" == "None" ] || [ -z "$IGW_ID" ]; then
    log_error "No Internet Gateway found for VPC $VPC_ID. Internet-facing ALB requires an IGW."
    exit 1
fi

log_success "Infrastructure discovery complete. IGW: $IGW_ID"

# ==========================================================================
# Step 3: Security Groups
# ==========================================================================
log_info "Step 3: Creating ALB security group..."

# Create ALB security group (CloudFront-only access)
ALB_SG_NAME="k8s-chat-alb-sg"

ALB_SG_ID=$(aws ec2 create-security-group \
    --region $AWS_REGION \
    --group-name $ALB_SG_NAME \
    --description "K8s Chat ALB - CloudFront origin-facing only" \
    --vpc-id $VPC_ID \
    --query "GroupId" --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --region $AWS_REGION \
        --filters "Name=group-name,Values=$ALB_SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
        --query "SecurityGroups[0].GroupId" --output text)

log_info "ALB Security Group: $ALB_SG_ID"

# Get CloudFront managed prefix list ID
CF_PREFIX_LIST_ID=$(aws ec2 describe-managed-prefix-lists \
    --region $AWS_REGION \
    --filters "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing" \
    --query "PrefixLists[0].PrefixListId" --output text 2>/dev/null)

if [ "$CF_PREFIX_LIST_ID" == "None" ] || [ -z "$CF_PREFIX_LIST_ID" ]; then
    log_warning "CloudFront managed prefix list not found. Falling back to 0.0.0.0/0 for ALB SG."
    aws ec2 authorize-security-group-ingress \
        --region $AWS_REGION \
        --group-id $ALB_SG_ID \
        --protocol tcp \
        --port 80 \
        --cidr 0.0.0.0/0 2>/dev/null || true
else
    log_info "CloudFront prefix list: $CF_PREFIX_LIST_ID"
    # Allow HTTP:80 only from CloudFront prefix list
    aws ec2 authorize-security-group-ingress \
        --region $AWS_REGION \
        --group-id $ALB_SG_ID \
        --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,PrefixListIds=[{PrefixListId=$CF_PREFIX_LIST_ID,Description=CloudFront origin-facing}]" \
        2>/dev/null || true
fi

log_success "ALB security group configured: $ALB_SG_ID"

# Add inbound rule to EC2 security group: allow ALB SG → port 8501
log_info "Adding ALB → EC2:8501 inbound rule to instance security group..."
aws ec2 authorize-security-group-ingress \
    --region $AWS_REGION \
    --group-id $INSTANCE_SG_ID \
    --protocol tcp \
    --port 8501 \
    --source-group $ALB_SG_ID 2>/dev/null || true

log_success "EC2 security group updated: ALB SG → port 8501 allowed"

# ==========================================================================
# Step 4: ALB + Target Group
# ==========================================================================
log_info "Step 4: Creating Application Load Balancer..."

ALB_NAME="k8s-chat-alb"

ALB_ARN=$(aws elbv2 create-load-balancer \
    --region $AWS_REGION \
    --name $ALB_NAME \
    --subnets $SUBNET_1 $SUBNET_2 \
    --security-groups $ALB_SG_ID \
    --scheme internet-facing \
    --type application \
    --ip-address-type ipv4 \
    --query "LoadBalancers[0].LoadBalancerArn" --output text 2>/dev/null || \
    aws elbv2 describe-load-balancers \
        --region $AWS_REGION \
        --names $ALB_NAME \
        --query "LoadBalancers[0].LoadBalancerArn" --output text)

log_info "ALB ARN: $ALB_ARN"

# Configure ALB idle timeout to 300 seconds (Streamlit WebSocket)
aws elbv2 modify-load-balancer-attributes \
    --region $AWS_REGION \
    --load-balancer-arn $ALB_ARN \
    --attributes Key=idle_timeout.timeout_seconds,Value=300 > /dev/null

log_success "ALB idle timeout set to 300s"

# Get ALB DNS name
ALB_DNS_NAME=$(aws elbv2 describe-load-balancers \
    --region $AWS_REGION \
    --load-balancer-arns $ALB_ARN \
    --query "LoadBalancers[0].DNSName" --output text)

log_info "ALB DNS: $ALB_DNS_NAME"

# Create Target Group (instance target type, port 8501)
TG_NAME="k8s-chat-tg"

TARGET_GROUP_ARN=$(aws elbv2 create-target-group \
    --region $AWS_REGION \
    --name $TG_NAME \
    --protocol HTTP \
    --port 8501 \
    --vpc-id $VPC_ID \
    --target-type instance \
    --health-check-enabled \
    --health-check-protocol HTTP \
    --health-check-path "/_stcore/health" \
    --health-check-interval-seconds 30 \
    --health-check-timeout-seconds 10 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3 \
    --query "TargetGroups[0].TargetGroupArn" --output text 2>/dev/null || \
    aws elbv2 describe-target-groups \
        --region $AWS_REGION \
        --names $TG_NAME \
        --query "TargetGroups[0].TargetGroupArn" --output text)

log_info "Target Group ARN: $TARGET_GROUP_ARN"

# Enable session stickiness
aws elbv2 modify-target-group-attributes \
    --region $AWS_REGION \
    --target-group-arn $TARGET_GROUP_ARN \
    --attributes Key=stickiness.enabled,Value=true Key=stickiness.type,Value=lb_cookie Key=stickiness.lb_cookie.duration_seconds,Value=86400 > /dev/null

log_success "Session stickiness enabled (24h)"

# Register EC2 instance as target
aws elbv2 register-targets \
    --region $AWS_REGION \
    --target-group-arn $TARGET_GROUP_ARN \
    --targets Id=$INSTANCE_ID,Port=8501 2>/dev/null || true

log_success "EC2 instance registered as target"

# Create HTTP:80 listener
LISTENER_ARN=$(aws elbv2 create-listener \
    --region $AWS_REGION \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn=$TARGET_GROUP_ARN \
    --query "Listeners[0].ListenerArn" --output text 2>/dev/null || \
    aws elbv2 describe-listeners \
        --region $AWS_REGION \
        --load-balancer-arn $ALB_ARN \
        --query "Listeners[0].ListenerArn" --output text)

log_success "ALB listener created: HTTP:80 → TG:8501"

# ==========================================================================
# Step 5: Streamlit Proxy Configuration
# ==========================================================================
log_info "Step 5: Configuring Streamlit for proxy compatibility..."

# Write a single shell script and send it via SSM for reliable execution
SSM_SCRIPT=$(cat <<'SSMEOF'
#!/bin/bash
set -e

# Create Streamlit config in home dir
mkdir -p /home/ec2-user/.streamlit
cat > /home/ec2-user/.streamlit/config.toml << 'TOML'
[server]
enableCORS = false
enableXsrfProtection = false
TOML
chown -R ec2-user:ec2-user /home/ec2-user/.streamlit

# Also create in app directory if found
APP_DIR=$(find /home/ec2-user -name 'app.py' -path '*/k8s-chat-frontend/*' -exec dirname {} \; 2>/dev/null | head -1)
if [ -n "$APP_DIR" ]; then
    mkdir -p "$APP_DIR/.streamlit"
    cp /home/ec2-user/.streamlit/config.toml "$APP_DIR/.streamlit/config.toml"
    chown -R ec2-user:ec2-user "$APP_DIR/.streamlit"
fi

# Restart Streamlit
pkill -f 'streamlit run' || true
sleep 2

if [ -n "$APP_DIR" ]; then
    cd "$APP_DIR"
    nohup su - ec2-user -c "cd $APP_DIR && streamlit run app.py --server.port=8501 --server.address=0.0.0.0" > /tmp/streamlit.log 2>&1 &
    sleep 5
    curl -sf http://localhost:8501/_stcore/health && echo 'Streamlit is healthy' || echo 'Streamlit health check failed - check /tmp/streamlit.log'
fi
SSMEOF
)

# Send the script via SSM
SSM_CMD_ID=$(aws ssm send-command \
    --region $AWS_REGION \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[\"$(echo "$SSM_SCRIPT" | sed 's/"/\\"/g' | tr '\n' '\a' | sed 's/\a/\\n/g')\"]" \
    --comment "Configure Streamlit proxy and restart" \
    --query "Command.CommandId" --output text 2>/dev/null) || true

if [ -n "$SSM_CMD_ID" ] && [ "$SSM_CMD_ID" != "None" ]; then
    log_info "SSM command sent: $SSM_CMD_ID"
    # Wait for completion
    for i in $(seq 1 12); do
        SSM_STATUS=$(aws ssm get-command-invocation \
            --region $AWS_REGION \
            --command-id "$SSM_CMD_ID" \
            --instance-id "$INSTANCE_ID" \
            --query "Status" --output text 2>/dev/null || echo "Pending")
        if [ "$SSM_STATUS" == "Success" ]; then
            log_success "Streamlit proxy configuration applied and service restarted"
            break
        elif [ "$SSM_STATUS" == "Failed" ] || [ "$SSM_STATUS" == "TimedOut" ]; then
            log_warning "SSM command $SSM_STATUS - Streamlit may need manual restart"
            log_warning "Check: aws ssm get-command-invocation --command-id $SSM_CMD_ID --instance-id $INSTANCE_ID --region $AWS_REGION"
            break
        fi
        sleep 5
    done
else
    log_warning "Could not send SSM command. Configure Streamlit manually on the instance."
    log_warning "Create ~/.streamlit/config.toml with: [server] enableCORS=false, enableXsrfProtection=false"
fi

# ==========================================================================
# Step 6: Wait for ALB to be ready
# ==========================================================================
log_info "Step 6: Waiting for ALB to become active..."

wait_for_alb_ready() {
    local alb_arn=$1
    local max_wait=600
    local check_interval=15
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        local state=$(aws elbv2 describe-load-balancers \
            --region $AWS_REGION \
            --load-balancer-arns "$alb_arn" \
            --query "LoadBalancers[0].State.Code" --output text 2>/dev/null || echo "unknown")

        if [ "$state" = "active" ]; then
            log_success "ALB is active"
            return 0
        fi

        log_info "ALB state: $state (waited ${elapsed}s)"
        sleep $check_interval
        elapsed=$((elapsed + check_interval))
    done

    log_error "ALB did not become active within ${max_wait}s"
    return 1
}

wait_for_alb_ready "$ALB_ARN"

# Check target health
log_info "Checking target health..."
for i in $(seq 1 20); do
    HEALTH=$(aws elbv2 describe-target-health \
        --region $AWS_REGION \
        --target-group-arn $TARGET_GROUP_ARN \
        --query "TargetHealthDescriptions[0].TargetHealth.State" --output text 2>/dev/null)

    if [ "$HEALTH" == "healthy" ]; then
        log_success "Target is healthy"
        break
    fi

    log_info "Target health: $HEALTH (attempt $i/20)"
    sleep 15
done

if [ "$HEALTH" != "healthy" ]; then
    log_warning "Target not yet healthy (state: $HEALTH). CloudFront will be created anyway."
    log_warning "Check: aws elbv2 describe-target-health --target-group-arn $TARGET_GROUP_ARN --region $AWS_REGION"
fi

# ==========================================================================
# Step 7: CloudFront Distribution
# ==========================================================================
log_info "Step 7: Creating CloudFront distribution..."

# Check if distribution already exists for this ALB
EXISTING_CF_ID=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Origins.Items[0].DomainName=='$ALB_DNS_NAME'].Id" \
    --output text 2>/dev/null)

if [ -n "$EXISTING_CF_ID" ] && [ "$EXISTING_CF_ID" != "None" ] && [ "$EXISTING_CF_ID" != "" ]; then
    log_info "CloudFront distribution already exists: $EXISTING_CF_ID"
    CF_DOMAIN=$(aws cloudfront get-distribution \
        --id $EXISTING_CF_ID \
        --query "Distribution.DomainName" --output text)
else
    # Create CloudFront distribution config
    CF_CONFIG=$(cat <<CFEOF
{
    "CallerReference": "k8s-chat-$(date +%s)",
    "Comment": "K8s Chat UI - Module 5",
    "Enabled": true,
    "Origins": {
        "Quantity": 1,
        "Items": [
            {
                "Id": "k8s-chat-alb",
                "DomainName": "$ALB_DNS_NAME",
                "CustomOriginConfig": {
                    "HTTPPort": 80,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "http-only",
                    "OriginSslProtocols": {
                        "Quantity": 1,
                        "Items": ["TLSv1.2"]
                    },
                    "OriginReadTimeout": 60,
                    "OriginKeepaliveTimeout": 5
                }
            }
        ]
    },
    "DefaultCacheBehavior": {
        "TargetOriginId": "k8s-chat-alb",
        "ViewerProtocolPolicy": "redirect-to-https",
        "AllowedMethods": {
            "Quantity": 7,
            "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
            "CachedMethods": {
                "Quantity": 2,
                "Items": ["GET", "HEAD"]
            }
        },
        "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
        "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3",
        "Compress": true
    },
    "PriceClass": "PriceClass_100",
    "HttpVersion": "http2and3"
}
CFEOF
)

    # Write config to temp file
    CF_CONFIG_FILE=$(mktemp /tmp/cf-config-XXXXXX.json)
    echo "$CF_CONFIG" > "$CF_CONFIG_FILE"

    CF_OUTPUT=$(aws cloudfront create-distribution \
        --distribution-config file://$CF_CONFIG_FILE \
        --output json 2>&1)

    if [ $? -ne 0 ]; then
        log_error "Failed to create CloudFront distribution:"
        echo "$CF_OUTPUT"
        rm -f "$CF_CONFIG_FILE"
        exit 1
    fi

    rm -f "$CF_CONFIG_FILE"

    EXISTING_CF_ID=$(echo "$CF_OUTPUT" | jq -r '.Distribution.Id')
    CF_DOMAIN=$(echo "$CF_OUTPUT" | jq -r '.Distribution.DomainName')
fi

log_success "CloudFront Distribution ID: $EXISTING_CF_ID"
log_success "CloudFront Domain: $CF_DOMAIN"

# ==========================================================================
# Step 8: Verify & Summary
# ==========================================================================
log_info "Step 8: Verification..."

# Wait a bit for CloudFront to start propagating
log_info "Waiting for CloudFront to deploy (this may take a few minutes)..."

CF_STATUS=""
for i in $(seq 1 40); do
    CF_STATUS=$(aws cloudfront get-distribution \
        --id $EXISTING_CF_ID \
        --query "Distribution.Status" --output text 2>/dev/null)

    if [ "$CF_STATUS" == "Deployed" ]; then
        log_success "CloudFront distribution is deployed"
        break
    fi

    log_info "CloudFront status: $CF_STATUS (attempt $i/40)"
    sleep 15
done

# Test health endpoint via CloudFront
if [ "$CF_STATUS" == "Deployed" ]; then
    log_info "Testing health endpoint via CloudFront..."
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "https://$CF_DOMAIN/_stcore/health" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" == "200" ]; then
        log_success "Health check passed (HTTP $HTTP_CODE)"
    else
        log_warning "Health check returned HTTP $HTTP_CODE (may need time for target to become healthy)"
    fi
fi

echo ""
log_success "=========================================="
log_success "  K8s Chat Frontend Deployment Complete"
log_success "=========================================="
echo ""
log_info "=== RESOURCE SUMMARY ==="
log_info "EC2 Instance:      $INSTANCE_ID"
log_info "VPC:               $VPC_ID"
log_info "ALB Name:          $ALB_NAME"
log_info "ALB ARN:           $ALB_ARN"
log_info "ALB DNS:           $ALB_DNS_NAME"
log_info "Target Group:      $TARGET_GROUP_ARN"
log_info "ALB Security Group: $ALB_SG_ID"
log_info "CloudFront ID:     $EXISTING_CF_ID"
log_info "CloudFront Domain: $CF_DOMAIN"
log_info "========================"
echo ""
log_success "Access URL: https://$CF_DOMAIN"
echo ""
log_info "Useful commands:"
log_info "  Check target health:  aws elbv2 describe-target-health --target-group-arn $TARGET_GROUP_ARN --region $AWS_REGION"
log_info "  Check CF status:      aws cloudfront get-distribution --id $EXISTING_CF_ID --query Distribution.Status"
log_info "  Test health:          curl https://$CF_DOMAIN/_stcore/health"
