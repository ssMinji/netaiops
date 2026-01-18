#!/bin/bash

# A2A Performance Agent - Application Load Balancer Deployment (Part 2/3)
# This script creates the Application Load Balancer and related resources

set -e  # Exit on any error

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

log_info "Starting A2A Performance Agent ALB Deployment (Part 2/3)"
log_info "AWS Region: $AWS_REGION"

# Step 1: Validate Prerequisites
log_info "Step 1: Validating prerequisites..."

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check jq for JSON parsing
if ! command -v jq &> /dev/null; then
    log_error "jq is not installed. Please install it first (required for JSON parsing)."
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    log_error "AWS credentials not configured. Please run 'aws configure' first."
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log_success "Prerequisites validated. AWS Account ID: $AWS_ACCOUNT_ID"

# Step 2: Load configuration from module3-config.json
log_info "Step 2: Loading configuration..."

STAGE4_CONFIG="../../module3-config.json"
if [ ! -f "$STAGE4_CONFIG" ]; then
    log_error "module3-config.json not found at $STAGE4_CONFIG"
    log_error "Please ensure you ran the first script (01-deploy-ecs-cluster-service.sh) first"
    exit 1
fi

# Get VPC ID from config
VPC_ID=$(jq -r '.vpc_id // empty' "$STAGE4_CONFIG")
if [ -z "$VPC_ID" ]; then
    log_error "VPC ID not found in configuration. Please run 01-deploy-ecs-cluster-service.sh first."
    exit 1
fi

log_info "Using VPC: $VPC_ID"

# Step 3: Get subnet information for ALB (matching ECS service AZs)
log_info "Step 3: Getting subnet information for ALB (using same AZs as ECS service)..."

# Get the selected AZs from config (set by script 01)
SELECTED_AZ_1=$(jq -r '.selected_azs.az_1 // empty' "$STAGE4_CONFIG")
SELECTED_AZ_2=$(jq -r '.selected_azs.az_2 // empty' "$STAGE4_CONFIG")

if [ -z "$SELECTED_AZ_1" ] || [ -z "$SELECTED_AZ_2" ]; then
    log_error "Selected AZs not found in config. Please run 01-deploy-ecs-cluster-service.sh first."
    exit 1
fi

log_info "Using AZs from ECS service configuration: $SELECTED_AZ_1, $SELECTED_AZ_2"

# Get all subnets in the VPC with their AZs
SUBNET_INFO=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[].[SubnetId,AvailabilityZone,MapPublicIpOnLaunch]" --output text)

if [ -z "$SUBNET_INFO" ]; then
  log_error "No subnets found in VPC"
  exit 1
fi

# Find one public subnet in each of the selected AZs for the ALB
SUBNET_1=$(echo "$SUBNET_INFO" | awk -v az="$SELECTED_AZ_1" '$2 == az && $3 == "True" {print $1; exit}')
SUBNET_2=$(echo "$SUBNET_INFO" | awk -v az="$SELECTED_AZ_2" '$2 == az && $3 == "True" {print $1; exit}')

if [ -z "$SUBNET_1" ]; then
    log_error "No public subnet found in AZ $SELECTED_AZ_1. ALB requires public subnets."
    exit 1
fi

if [ -z "$SUBNET_2" ]; then
    log_error "No public subnet found in AZ $SELECTED_AZ_2. ALB requires public subnets."
    exit 1
fi

AZ_1="$SELECTED_AZ_1"
AZ_2="$SELECTED_AZ_2"

log_info "Using subnets for ALB: $SUBNET_1 (AZ: $AZ_1), $SUBNET_2 (AZ: $AZ_2)"
log_success "ALB will use the same AZs as the ECS service for compatibility"

# Save subnet information to config
jq --arg subnet1 "$SUBNET_1" --arg subnet2 "$SUBNET_2" \
   '.alb_subnets = {subnet_1: $subnet1, subnet_2: $subnet2}' \
   "$STAGE4_CONFIG" > "$STAGE4_CONFIG.tmp" && mv "$STAGE4_CONFIG.tmp" "$STAGE4_CONFIG"

# Step 4: Create Security Group for ALB
log_info "Step 4: Creating security group for ALB..."

ALB_SG_ID=$(aws ec2 create-security-group \
  --group-name a2a-performance-alb-sg \
  --description "Security group for A2A Performance ALB" \
  --vpc-id $VPC_ID \
  --query "GroupId" --output text 2>/dev/null || \
  aws ec2 describe-security-groups --filters "Name=group-name,Values=a2a-performance-alb-sg" --query "SecurityGroups[0].GroupId" --output text)

# Allow HTTP traffic to ALB
aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG_ID \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0 2>/dev/null || true

# Allow HTTPS traffic to ALB
aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG_ID \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0 2>/dev/null || true

log_info "ALB security group created: $ALB_SG_ID"

# Save ALB security group ID to config
jq --arg alb_sg_id "$ALB_SG_ID" '.alb_security_group_id = $alb_sg_id' \
   "$STAGE4_CONFIG" > "$STAGE4_CONFIG.tmp" && mv "$STAGE4_CONFIG.tmp" "$STAGE4_CONFIG"

# Step 5: Create Application Load Balancer
log_info "Step 5: Creating Application Load Balancer..."

ALB_ARN=$(aws elbv2 create-load-balancer \
  --name a2a-performance-alb \
  --subnets $SUBNET_1 $SUBNET_2 \
  --security-groups $ALB_SG_ID \
  --scheme internet-facing \
  --type application \
  --ip-address-type ipv4 \
  --query "LoadBalancers[0].LoadBalancerArn" --output text 2>/dev/null || \
  aws elbv2 describe-load-balancers --names a2a-performance-alb --query "LoadBalancers[0].LoadBalancerArn" --output text)

log_info "ALB created: $ALB_ARN"

# Configure ALB idle timeout to 15 minutes (900 seconds) for long-running tasks
log_info "Configuring ALB idle timeout to 15 minutes (900 seconds) for long-running tasks..."
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn $ALB_ARN \
  --attributes Key=idle_timeout.timeout_seconds,Value=900 \
  --region $AWS_REGION

if [ $? -eq 0 ]; then
    log_success "ALB idle timeout configured to 900 seconds (15 minutes)"
else
    log_error "Failed to configure ALB idle timeout"
    exit 1
fi

# Get ALB DNS name
ALB_DNS_NAME=$(aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN --query "LoadBalancers[0].DNSName" --output text)
log_info "ALB DNS Name: $ALB_DNS_NAME"

# Save ALB information to module3-config.json
log_info "Saving ALB information to module3-config.json..."

# Create a Python script to update the JSON file
cat > update_alb_config.py << 'EOF'
#!/usr/bin/env python3
import json
import sys
import os

def update_alb_config():
    # Get values from environment variables
    alb_arn = os.environ.get('ALB_ARN')
    alb_dns = os.environ.get('ALB_DNS_NAME')
    
    if not alb_arn or not alb_dns:
        print("Error: ALB environment variables not set", file=sys.stderr)
        sys.exit(1)
    
    config_file = "../../module3-config.json"
    
    try:
        # Load existing config
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Ensure agentcore_performance section exists
        if 'agentcore_performance' not in config:
            config['agentcore_performance'] = {}
        
        # Add the ALB information
        config['agentcore_performance']['alb_arn'] = alb_arn
        config['agentcore_performance']['alb_dns'] = alb_dns
        
        # Write updated config
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"Successfully updated module3-config.json with ALB information")
        
    except FileNotFoundError:
        print(f"Error: {config_file} not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {config_file}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error updating config file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    update_alb_config()
EOF

# Set environment variables and run the Python script
export ALB_ARN="$ALB_ARN"
export ALB_DNS_NAME="$ALB_DNS_NAME"

if python3 update_alb_config.py; then
    log_success "ALB information saved to module3-config.json"
    rm update_alb_config.py
else
    log_error "Failed to save ALB information to module3-config.json"
    rm update_alb_config.py
    exit 1
fi

# Step 6: Create Target Group
log_info "Step 6: Creating target group..."

TARGET_GROUP_ARN=$(aws elbv2 create-target-group \
  --name a2a-performance-tg \
  --protocol HTTP \
  --port 10005 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-enabled \
  --health-check-interval-seconds 60 \
  --health-check-path /health \
  --health-check-protocol HTTP \
  --health-check-timeout-seconds 30 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 5 \
  --query "TargetGroups[0].TargetGroupArn" --output text 2>/dev/null || \
  aws elbv2 describe-target-groups --names a2a-performance-tg --query "TargetGroups[0].TargetGroupArn" --output text)

log_info "Target group created: $TARGET_GROUP_ARN"

# Save target group ARN to config
jq --arg target_group_arn "$TARGET_GROUP_ARN" \
   '.agentcore_performance.target_group_arn = $target_group_arn' \
   "$STAGE4_CONFIG" > "$STAGE4_CONFIG.tmp" && mv "$STAGE4_CONFIG.tmp" "$STAGE4_CONFIG"

# Step 7: Create ALB Listener
log_info "Step 7: Creating ALB listener..."

LISTENER_ARN=$(aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TARGET_GROUP_ARN \
  --query "Listeners[0].ListenerArn" --output text 2>/dev/null || \
  aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --query "Listeners[0].ListenerArn" --output text)

log_info "ALB listener created: $LISTENER_ARN"

# Step 8: Wait for Load Balancer to be Ready
log_info "Step 8: Waiting for load balancer to be ready..."

wait_for_alb_ready() {
    local alb_arn=$1
    local alb_dns=$2
    local max_wait=900  # 15 minutes max wait
    local check_interval=15
    local elapsed_time=0
    
    log_info "Waiting for load balancer to be fully provisioned and ready (max wait: ${max_wait}s)..."
    
    while [ $elapsed_time -lt $max_wait ]; do
        # Check ALB state
        local alb_state=$(aws elbv2 describe-load-balancers --load-balancer-arns "$alb_arn" --query "LoadBalancers[0].State.Code" --output text 2>/dev/null || echo "unknown")
        
        log_info "Load balancer state: $alb_state (waited ${elapsed_time}s)"
        
        if [ "$alb_state" = "active" ]; then
            # ALB is active, now test DNS resolution and basic connectivity
            log_info "ALB is active, testing DNS resolution and connectivity..."
            
            # Test DNS resolution
            if nslookup "$alb_dns" >/dev/null 2>&1; then
                log_info "DNS resolution successful for $alb_dns"
                
                # Test basic connectivity (should get connection refused or timeout, but not DNS error)
                if timeout 10 bash -c "</dev/tcp/${alb_dns}/80" 2>/dev/null || [ $? -eq 124 ] || [ $? -eq 1 ]; then
                    log_success "Load balancer is fully ready and accessible"
                    return 0
                else
                    log_info "ALB not yet accepting connections, continuing to wait..."
                fi
            else
                log_info "DNS resolution not yet available, continuing to wait..."
            fi
        fi
        
        sleep $check_interval
        elapsed_time=$((elapsed_time + check_interval))
    done
    
    log_error "Load balancer did not become ready within ${max_wait} seconds"
    return 1
}

if wait_for_alb_ready "$ALB_ARN" "$ALB_DNS_NAME"; then
    log_success "Load balancer is fully ready"
else
    log_error "Load balancer provisioning failed or timed out"
    exit 1
fi

# Step 9: Fix ALB Networking - Ensure Internet Gateway Route
log_info "Step 9: Fixing ALB networking - ensuring Internet Gateway route..."

# Get Internet Gateway ID for the VPC
IGW_ID=$(aws ec2 describe-internet-gateways --filters "Name=attachment.vpc-id,Values=$VPC_ID" --query "InternetGateways[0].InternetGatewayId" --output text 2>/dev/null)

if [ "$IGW_ID" == "None" ] || [ -z "$IGW_ID" ]; then
    log_error "No Internet Gateway found for VPC $VPC_ID. Internet-facing ALB requires an Internet Gateway."
    exit 1
fi

log_info "Found Internet Gateway: $IGW_ID"

# Check and fix route table for ALB subnets
for SUBNET_ID in $SUBNET_1 $SUBNET_2; do
    log_info "Checking route table for subnet $SUBNET_ID..."
    
    # Get route table ID for this subnet
    ROUTE_TABLE_ID=$(aws ec2 describe-route-tables \
        --filters "Name=association.subnet-id,Values=$SUBNET_ID" \
        --query "RouteTables[0].RouteTableId" --output text 2>/dev/null)
    
    if [ "$ROUTE_TABLE_ID" == "None" ] || [ -z "$ROUTE_TABLE_ID" ]; then
        # If no explicit association, get the main route table
        ROUTE_TABLE_ID=$(aws ec2 describe-route-tables \
            --filters "Name=vpc-id,Values=$VPC_ID" "Name=association.main,Values=true" \
            --query "RouteTables[0].RouteTableId" --output text)
        log_info "Using main route table for subnet $SUBNET_ID: $ROUTE_TABLE_ID"
    else
        log_info "Found explicit route table for subnet $SUBNET_ID: $ROUTE_TABLE_ID"
    fi
    
    # Check current default route (0.0.0.0/0)
    CURRENT_ROUTE_TARGET=$(aws ec2 describe-route-tables \
        --route-table-ids $ROUTE_TABLE_ID \
        --query "RouteTables[0].Routes[?DestinationCidrBlock=='0.0.0.0/0'].GatewayId" \
        --output text 2>/dev/null)
    
    CURRENT_NAT_TARGET=$(aws ec2 describe-route-tables \
        --route-table-ids $ROUTE_TABLE_ID \
        --query "RouteTables[0].Routes[?DestinationCidrBlock=='0.0.0.0/0'].NatGatewayId" \
        --output text 2>/dev/null)
    
    log_info "Current route target for 0.0.0.0/0 in $ROUTE_TABLE_ID:"
    log_info "  Gateway ID: $CURRENT_ROUTE_TARGET"
    log_info "  NAT Gateway ID: $CURRENT_NAT_TARGET"
    
    # Check if route needs to be fixed
    NEEDS_FIX=false
    
    if [ -n "$CURRENT_NAT_TARGET" ] && [ "$CURRENT_NAT_TARGET" != "None" ]; then
        log_warning "Found NAT Gateway route ($CURRENT_NAT_TARGET) - this will prevent internet-facing ALB from working"
        NEEDS_FIX=true
    elif [ "$CURRENT_ROUTE_TARGET" != "$IGW_ID" ]; then
        if [ -n "$CURRENT_ROUTE_TARGET" ] && [ "$CURRENT_ROUTE_TARGET" != "None" ]; then
            log_warning "Found non-IGW route target ($CURRENT_ROUTE_TARGET) - expected Internet Gateway ($IGW_ID)"
            NEEDS_FIX=true
        else
            log_warning "No default route found - adding Internet Gateway route"
            NEEDS_FIX=true
        fi
    else
        log_success "Route table $ROUTE_TABLE_ID already has correct Internet Gateway route"
    fi
    
    if [ "$NEEDS_FIX" = true ]; then
        log_info "Fixing route table $ROUTE_TABLE_ID to use Internet Gateway $IGW_ID..."
        
        # Try to replace existing route first
        if aws ec2 replace-route \
            --route-table-id $ROUTE_TABLE_ID \
            --destination-cidr-block 0.0.0.0/0 \
            --gateway-id $IGW_ID 2>/dev/null; then
            log_success "Successfully replaced route in $ROUTE_TABLE_ID"
        else
            # If replace fails, try to create new route
            log_info "Replace failed, trying to create new route..."
            if aws ec2 create-route \
                --route-table-id $ROUTE_TABLE_ID \
                --destination-cidr-block 0.0.0.0/0 \
                --gateway-id $IGW_ID 2>/dev/null; then
                log_success "Successfully created route in $ROUTE_TABLE_ID"
            else
                log_error "Failed to create route in $ROUTE_TABLE_ID"
                log_error "Manual fix required: aws ec2 replace-route --route-table-id $ROUTE_TABLE_ID --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID"
                exit 1
            fi
        fi
        
        # Verify the fix
        sleep 5
        UPDATED_ROUTE_TARGET=$(aws ec2 describe-route-tables \
            --route-table-ids $ROUTE_TABLE_ID \
            --query "RouteTables[0].Routes[?DestinationCidrBlock=='0.0.0.0/0'].GatewayId" \
            --output text 2>/dev/null)
        
        if [ "$UPDATED_ROUTE_TARGET" = "$IGW_ID" ]; then
            log_success "Route fix verified for $ROUTE_TABLE_ID"
        else
            log_error "Route fix verification failed for $ROUTE_TABLE_ID"
            log_error "Expected: $IGW_ID, Got: $UPDATED_ROUTE_TARGET"
            exit 1
        fi
    fi
done

log_success "ALB networking configuration verified and fixed"

log_success "A2A Performance Agent ALB deployment completed successfully!"
log_info "=== ALB DEPLOYMENT SUMMARY ==="
log_info "Load Balancer ARN: $ALB_ARN"
log_info "Load Balancer DNS: $ALB_DNS_NAME"
log_info "Target Group ARN: $TARGET_GROUP_ARN"
log_info "Security Group: $ALB_SG_ID"
log_info "Subnets: $SUBNET_1 ($AZ_1), $SUBNET_2 ($AZ_2)"
log_info "=============================="
log_info ""
log_info "ALB URL: http://$ALB_DNS_NAME"
log_info "Note: The ALB is not yet connected to the ECS service."
log_info "Next step: Run 03-connect-service-to-alb.sh to connect the ECS service to the ALB"
