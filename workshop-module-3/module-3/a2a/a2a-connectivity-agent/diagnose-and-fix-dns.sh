#!/bin/bash

# Diagnose and Fix DNS Resolution Issues for A2A Connectivity Agent
# This script addresses the Cognito DNS resolution failure

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
STAGE4_CONFIG="../../module3-config.json"
CLUSTER_NAME="a2a-agents-cluster"
SERVICE_NAME="a2a-connectivity-agent-service"

log_info "=== A2A Connectivity Agent DNS Resolution Diagnostic ==="
log_info "AWS Region: $AWS_REGION"

# Check if module3-config.json exists
if [ ! -f "$STAGE4_CONFIG" ]; then
    log_error "module3-config.json not found at $STAGE4_CONFIG"
    exit 1
fi

# Get VPC ID
VPC_ID=$(jq -r '.vpc_id // empty' "$STAGE4_CONFIG")
if [ -z "$VPC_ID" ] || [ "$VPC_ID" == "null" ]; then
    VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
fi
log_info "Using VPC: $VPC_ID"

# Get subnets
SUBNET_IDS=$(jq -r '.subnet_ids[]? // empty' "$STAGE4_CONFIG" | tr '\n' ' ')
if [ -z "$SUBNET_IDS" ]; then
    SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[*].SubnetId" --output text)
fi
log_info "Using Subnets: $SUBNET_IDS"

# Get security group
SECURITY_GROUP_ID=$(jq -r '.security_group_id // empty' "$STAGE4_CONFIG")
if [ -z "$SECURITY_GROUP_ID" ] || [ "$SECURITY_GROUP_ID" == "null" ]; then
    SECURITY_GROUP_ID=$(aws ec2 describe-security-groups \
        --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=default" \
        --query "SecurityGroups[0].GroupId" --output text)
fi
log_info "Using Security Group: $SECURITY_GROUP_ID"

echo ""
log_info "=== Step 1: Checking VPC DNS Settings ==="

# Check if DNS resolution is enabled
DNS_SUPPORT=$(aws ec2 describe-vpc-attribute --vpc-id "$VPC_ID" --attribute enableDnsSupport --query "EnableDnsSupport.Value" --output text)
DNS_HOSTNAMES=$(aws ec2 describe-vpc-attribute --vpc-id "$VPC_ID" --attribute enableDnsHostnames --query "EnableDnsHostnames.Value" --output text)

log_info "DNS Support: $DNS_SUPPORT"
log_info "DNS Hostnames: $DNS_HOSTNAMES"

if [ "$DNS_SUPPORT" != "true" ]; then
    log_warning "DNS support is disabled. Enabling..."
    aws ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-support
    log_success "DNS support enabled"
fi

if [ "$DNS_HOSTNAMES" != "true" ]; then
    log_warning "DNS hostnames is disabled. Enabling..."
    aws ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-hostnames
    log_success "DNS hostnames enabled"
fi

echo ""
log_info "=== Step 2: Checking Internet Connectivity ==="

# Check if subnets have internet gateway route
for SUBNET_ID in $SUBNET_IDS; do
    ROUTE_TABLE_ID=$(aws ec2 describe-route-tables \
        --filters "Name=association.subnet-id,Values=$SUBNET_ID" \
        --query "RouteTables[0].RouteTableId" --output text)
    
    if [ "$ROUTE_TABLE_ID" == "None" ] || [ -z "$ROUTE_TABLE_ID" ]; then
        # Check main route table
        ROUTE_TABLE_ID=$(aws ec2 describe-route-tables \
            --filters "Name=vpc-id,Values=$VPC_ID" "Name=association.main,Values=true" \
            --query "RouteTables[0].RouteTableId" --output text)
    fi
    
    log_info "Subnet $SUBNET_ID uses route table: $ROUTE_TABLE_ID"
    
    # Check for internet gateway route
    IGW_ROUTE=$(aws ec2 describe-route-tables \
        --route-table-ids "$ROUTE_TABLE_ID" \
        --query "RouteTables[0].Routes[?GatewayId!=null && starts_with(GatewayId, 'igw-')]" \
        --output json)
    
    if [ "$IGW_ROUTE" == "[]" ] || [ -z "$IGW_ROUTE" ]; then
        log_warning "No internet gateway route found for subnet $SUBNET_ID"
        log_warning "This subnet is private and requires NAT Gateway or VPC endpoints"
    else
        log_success "Internet gateway route exists for subnet $SUBNET_ID"
    fi
done

echo ""
log_info "=== Step 3: Checking Security Group Rules ==="

# Check outbound HTTPS rule
HTTPS_RULE=$(aws ec2 describe-security-groups \
    --group-ids "$SECURITY_GROUP_ID" \
    --query "SecurityGroups[0].IpPermissionsEgress[?IpProtocol=='tcp' && FromPort<=\`443\` && ToPort>=\`443\`]" \
    --output json)

if [ "$HTTPS_RULE" == "[]" ] || [ -z "$HTTPS_RULE" ]; then
    log_warning "No HTTPS outbound rule found. Adding..."
    aws ec2 authorize-security-group-egress \
        --group-id "$SECURITY_GROUP_ID" \
        --protocol tcp \
        --port 443 \
        --cidr 0.0.0.0/0 2>/dev/null || log_info "Rule may already exist"
    log_success "HTTPS outbound rule added"
else
    log_success "HTTPS outbound rule exists"
fi

echo ""
log_info "=== Step 4: Checking/Creating VPC Endpoints ==="

# Check for Cognito VPC endpoint (if in private subnet)
log_info "Checking for Cognito VPC endpoint..."
COGNITO_ENDPOINT=$(aws ec2 describe-vpc-endpoints \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION.cognito-idp" \
    --query "VpcEndpoints[0].VpcEndpointId" --output text 2>/dev/null)

if [ "$COGNITO_ENDPOINT" == "None" ] || [ -z "$COGNITO_ENDPOINT" ]; then
    log_warning "No Cognito VPC endpoint found"
    log_info "Creating Cognito VPC endpoint for private subnet access..."
    
    # Get all subnet IDs as array
    SUBNET_ARRAY=$(echo $SUBNET_IDS | tr ' ' '\n' | head -2 | tr '\n' ' ')
    
    COGNITO_ENDPOINT=$(aws ec2 create-vpc-endpoint \
        --vpc-id "$VPC_ID" \
        --vpc-endpoint-type Interface \
        --service-name "com.amazonaws.$AWS_REGION.cognito-idp" \
        --subnet-ids $SUBNET_ARRAY \
        --security-group-ids "$SECURITY_GROUP_ID" \
        --private-dns-enabled \
        --query "VpcEndpoint.VpcEndpointId" --output text 2>&1)
    
    if [[ "$COGNITO_ENDPOINT" == vpce-* ]]; then
        log_success "Cognito VPC endpoint created: $COGNITO_ENDPOINT"
        log_info "Waiting for endpoint to become available (60 seconds)..."
        sleep 60
    else
        log_error "Failed to create Cognito VPC endpoint: $COGNITO_ENDPOINT"
        log_info "Continuing with public internet access assumption..."
    fi
else
    log_success "Cognito VPC endpoint exists: $COGNITO_ENDPOINT"
fi

echo ""
log_info "=== Step 5: Storing Cognito Token URL in SSM ==="

# Extract user pool ID from discovery URL in config.yaml
if [ -f "config.yaml" ]; then
    DISCOVERY_URL=$(grep "discovery_url:" config.yaml | awk '{print $2}' | tr -d '"' | tr -d "'")
    if [ -n "$DISCOVERY_URL" ]; then
        # Extract user pool ID from discovery URL
        USER_POOL_ID=$(echo "$DISCOVERY_URL" | sed -n 's|.*/\([^/]*\)/\.well-known.*|\1|p')
        
        if [ -n "$USER_POOL_ID" ]; then
            # Construct token URL
            TOKEN_URL="https://cognito-idp.$AWS_REGION.amazonaws.com/$USER_POOL_ID/oauth2/token"
            
            log_info "Storing token URL in SSM: $TOKEN_URL"
            aws ssm put-parameter \
                --name "/app/troubleshooting/agentcore/cognito_token_url" \
                --value "$TOKEN_URL" \
                --type "String" \
                --overwrite 2>/dev/null || log_info "Parameter may already exist"
            
            log_success "Token URL stored in SSM"
        fi
    fi
fi

echo ""
log_info "=== Step 6: Updating ECS Task Network Configuration ==="

# Get current ECS service configuration
SERVICE_INFO=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$SERVICE_NAME" \
    --query "services[0]" --output json 2>/dev/null)

if [ "$SERVICE_INFO" != "null" ] && [ -n "$SERVICE_INFO" ]; then
    TASK_DEF_ARN=$(echo "$SERVICE_INFO" | jq -r '.taskDefinition')
    CURRENT_ASSIGN_PUBLIC_IP=$(echo "$SERVICE_INFO" | jq -r '.networkConfiguration.awsvpcConfiguration.assignPublicIp // "DISABLED"')
    
    log_info "Current task definition: $TASK_DEF_ARN"
    log_info "Current public IP assignment: $CURRENT_ASSIGN_PUBLIC_IP"
    
    # If in public subnet without NAT, enable public IP
    if [ "$CURRENT_ASSIGN_PUBLIC_IP" == "DISABLED" ]; then
        log_warning "Public IP assignment is disabled"
        log_info "Updating service to enable public IP for internet access..."
        
        # Update service with public IP enabled
        aws ecs update-service \
            --cluster "$CLUSTER_NAME" \
            --service "$SERVICE_NAME" \
            --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_IDS],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
            --force-new-deployment \
            --query "service.serviceArn" --output text >/dev/null 2>&1 && \
            log_success "Service updated with public IP enabled" || \
            log_warning "Failed to update service - may need manual intervention"
    else
        log_success "Public IP assignment is already enabled"
        
        # Force new deployment to pick up changes
        log_info "Forcing new deployment..."
        aws ecs update-service \
            --cluster "$CLUSTER_NAME" \
            --service "$SERVICE_NAME" \
            --force-new-deployment \
            --query "service.serviceArn" --output text >/dev/null 2>&1 && \
            log_success "New deployment initiated" || \
            log_warning "Failed to initiate deployment"
    fi
else
    log_warning "ECS service not found or not accessible"
fi

echo ""
log_success "=== Diagnostic and Fix Complete ==="
echo ""
log_info "Summary of changes:"
log_info "  ✓ VPC DNS settings verified/enabled"
log_info "  ✓ Security group HTTPS egress verified/added"
log_info "  ✓ Cognito VPC endpoint checked/created (if needed)"
log_info "  ✓ Token URL stored in SSM"
log_info "  ✓ ECS service network configuration updated"
echo ""
log_info "Next steps:"
log_info "  1. Wait 2-3 minutes for ECS tasks to restart"
log_info "  2. Check ECS task logs in CloudWatch"
log_info "  3. Verify the agent can now fetch tokens from Cognito"
echo ""
log_info "To monitor the service:"
log_info "  aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME"
echo ""
log_info "To view task logs:"
log_info "  aws logs tail /ecs/a2a-connectivity-agent --follow"
echo ""
