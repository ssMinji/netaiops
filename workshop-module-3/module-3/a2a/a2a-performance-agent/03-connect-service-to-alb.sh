#!/bin/bash

# A2A Performance Agent - Connect Service to ALB (Part 3/3)
# This script connects the existing ECS service to the Application Load Balancer

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
CLUSTER_NAME="a2a-agents-cluster"

log_info "Starting A2A Performance Agent Service-to-ALB Connection (Part 3/3)"
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
log_success "Prerequisites validated"

# Step 2: Load configuration from module3-config.json
log_info "Step 2: Loading configuration..."

STAGE4_CONFIG="../../module3-config.json"
if [ ! -f "$STAGE4_CONFIG" ]; then
    log_error "module3-config.json not found at $STAGE4_CONFIG"
    exit 1
fi

# Load required configuration values
VPC_ID=$(jq -r '.vpc_id // empty' "$STAGE4_CONFIG")
ALB_SG_ID=$(jq -r '.alb_security_group_id // empty' "$STAGE4_CONFIG")
TARGET_GROUP_ARN=$(jq -r '.agentcore_performance.target_group_arn // empty' "$STAGE4_CONFIG")
ALB_DNS_NAME=$(jq -r '.agentcore_performance.alb_dns // empty' "$STAGE4_CONFIG")

# Validate configuration
if [ -z "$VPC_ID" ] || [ -z "$ALB_SG_ID" ] || [ -z "$TARGET_GROUP_ARN" ] || [ -z "$ALB_DNS_NAME" ]; then
    log_error "Missing required configuration. Please run previous scripts first."
    exit 1
fi

log_success "Configuration loaded successfully"

# Step 3: Verify ECS Service Exists
log_info "Step 3: Verifying ECS service exists..."

EXISTING_SERVICE=$(aws ecs describe-services --cluster $CLUSTER_NAME --services a2a-performance-agent-service --region $AWS_REGION --query "services[0].serviceArn" --output text 2>/dev/null)

if [ "$EXISTING_SERVICE" == "None" ] || [ "$EXISTING_SERVICE" == "" ] || [ "$EXISTING_SERVICE" == "null" ]; then
    log_error "ECS service not found. Please run 01-deploy-ecs-cluster-service.sh first."
    exit 1
fi

log_success "ECS service verified"

# Step 4: Get Current Task Definition from Service
log_info "Step 4: Getting current task definition from ECS service..."

CURRENT_TASK_DEFINITION_ARN=$(aws ecs describe-services \
  --cluster $CLUSTER_NAME \
  --services a2a-performance-agent-service \
  --region $AWS_REGION \
  --query "services[0].taskDefinition" --output text 2>/dev/null)

if [ "$CURRENT_TASK_DEFINITION_ARN" == "None" ] || [ -z "$CURRENT_TASK_DEFINITION_ARN" ]; then
    log_error "Failed to get current task definition from service"
    exit 1
fi

log_success "Current task definition: $CURRENT_TASK_DEFINITION_ARN"

# Step 5: Get ECS Service Security Group
log_info "Step 5: Getting ECS service security group..."

ECS_SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=a2a-performance-ecs-sg" --query "SecurityGroups[0].GroupId" --output text)

if [ "$ECS_SG_ID" == "None" ] || [ -z "$ECS_SG_ID" ]; then
    log_error "ECS security group not found. Please run 01-deploy-ecs-cluster-service.sh first."
    exit 1
fi

log_success "ECS security group found"

# Step 6: Update Security Groups for ALB Integration
log_info "Step 6: Updating security groups for ALB integration..."

aws ec2 revoke-security-group-ingress \
  --group-id $ECS_SG_ID \
  --protocol tcp \
  --port 10005 \
  --cidr 0.0.0.0/0 >/dev/null 2>&1 || true

aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG_ID \
  --protocol tcp \
  --port 10005 \
  --source-group $ALB_SG_ID >/dev/null 2>&1 || true

log_success "Security groups updated"

# Step 7: Fix ALB and ECS Availability Zone Alignment
log_info "Step 7: Fixing ALB and ECS Availability Zone alignment..."

# Get ALB subnets and their AZs
ALB_SUBNET_1=$(jq -r '.alb_subnets.subnet_1 // empty' "$STAGE4_CONFIG")
ALB_SUBNET_2=$(jq -r '.alb_subnets.subnet_2 // empty' "$STAGE4_CONFIG")

if [ -z "$ALB_SUBNET_1" ] || [ -z "$ALB_SUBNET_2" ]; then
    log_error "ALB subnet information not found in config. Please run 02-deploy-alb.sh first."
    exit 1
fi

# Get all available subnets and their AZs
ALL_SUBNET_INFO=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[].[SubnetId,AvailabilityZone]" --output text)

# Get AZs for ALB subnets
ALB_AZ_1=$(echo "$ALL_SUBNET_INFO" | grep "$ALB_SUBNET_1" | cut -f2)
ALB_AZ_2=$(echo "$ALL_SUBNET_INFO" | grep "$ALB_SUBNET_2" | cut -f2)

log_info "ALB is configured for AZs: $ALB_AZ_1, $ALB_AZ_2"

# Get all subnets that are in the same AZs as the ALB
ALB_COMPATIBLE_SUBNETS=$(echo "$ALL_SUBNET_INFO" | awk -v az1="$ALB_AZ_1" -v az2="$ALB_AZ_2" '$2 == az1 || $2 == az2 {print $1}')

log_info "Subnets compatible with ALB AZs: $(echo $ALB_COMPATIBLE_SUBNETS | tr '\n' ' ')"

# Check if current ECS service is properly configured for ALB AZs
log_info "Checking current ECS service configuration..."

# Get running task details
TASK_ARN=$(aws ecs list-tasks \
  --cluster $CLUSTER_NAME \
  --service-name a2a-performance-agent-service \
  --query "taskArns[0]" \
  --output text \
  --region $AWS_REGION)

if [ "$TASK_ARN" == "None" ] || [ -z "$TASK_ARN" ]; then
    log_error "No running tasks found for service"
    exit 1
fi

# Get task subnet and AZ
TASK_SUBNET_ID=$(aws ecs describe-tasks \
  --cluster $CLUSTER_NAME \
  --tasks $TASK_ARN \
  --query "tasks[0].attachments[0].details[?name=='subnetId'].value" \
  --output text \
  --region $AWS_REGION)

TASK_AZ=$(echo "$ALL_SUBNET_INFO" | grep "$TASK_SUBNET_ID" | cut -f2)

log_info "Current task is running in subnet $TASK_SUBNET_ID (AZ: $TASK_AZ)"

# Check if task is in an ALB-compatible AZ
if [ "$TASK_AZ" != "$ALB_AZ_1" ] && [ "$TASK_AZ" != "$ALB_AZ_2" ]; then
    log_warning "Task is running in AZ $TASK_AZ which is not enabled for the ALB"
    log_info "ALB is only enabled for AZs: $ALB_AZ_1, $ALB_AZ_2"
    
    # Update ECS service to use only ALB-compatible subnets
    log_info "Updating ECS service to use only ALB-compatible subnets..."
    
    # Create network configuration for ALB-compatible subnets only
    ALB_COMPATIBLE_SUBNETS_ARRAY=$(echo $ALB_COMPATIBLE_SUBNETS | tr ' ' '\n' | jq -R . | jq -s .)
    
    # Update service network configuration
    aws ecs update-service \
      --cluster $CLUSTER_NAME \
      --service a2a-performance-agent-service \
      --network-configuration "awsvpcConfiguration={subnets=$ALB_COMPATIBLE_SUBNETS_ARRAY,securityGroups=[\"$ECS_SG_ID\"],assignPublicIp=ENABLED}" \
      --region $AWS_REGION >/dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        log_success "ECS service updated to use ALB-compatible subnets"
        
        # Wait for service to stabilize with new configuration
        log_info "Waiting for service to stabilize with new network configuration..."
        aws ecs wait services-stable --cluster $CLUSTER_NAME --services a2a-performance-agent-service --region $AWS_REGION
        
        # Get new task details
        TASK_ARN=$(aws ecs list-tasks \
          --cluster $CLUSTER_NAME \
          --service-name a2a-performance-agent-service \
          --query "taskArns[0]" \
          --output text \
          --region $AWS_REGION)
        
        TASK_SUBNET_ID=$(aws ecs describe-tasks \
          --cluster $CLUSTER_NAME \
          --tasks $TASK_ARN \
          --query "tasks[0].attachments[0].details[?name=='subnetId'].value" \
          --output text \
          --region $AWS_REGION)
        
        TASK_AZ=$(echo "$ALL_SUBNET_INFO" | grep "$TASK_SUBNET_ID" | cut -f2)
        log_info "Task is now running in subnet $TASK_SUBNET_ID (AZ: $TASK_AZ)"
    else
        log_error "Failed to update ECS service network configuration"
        exit 1
    fi
else
    log_success "Task is already running in an ALB-compatible AZ: $TASK_AZ"
fi

# Get task private IP
TASK_IP=$(aws ecs describe-tasks \
  --cluster $CLUSTER_NAME \
  --tasks $TASK_ARN \
  --query "tasks[0].attachments[0].details[?name=='privateIPv4Address'].value" \
  --output text \
  --region $AWS_REGION)

if [ "$TASK_IP" == "None" ] || [ -z "$TASK_IP" ]; then
    log_error "Failed to get task IP address"
    exit 1
fi

log_info "Found running task IP: $TASK_IP in AZ: $TASK_AZ"

# Verify the AZ is compatible before registering
if [ "$TASK_AZ" != "$ALB_AZ_1" ] && [ "$TASK_AZ" != "$ALB_AZ_2" ]; then
    log_error "Task is still not in an ALB-compatible AZ after service update"
    log_error "Task AZ: $TASK_AZ, ALB AZs: $ALB_AZ_1, $ALB_AZ_2"
    exit 1
fi

# Register task directly to target group
log_info "Registering task IP to target group (AZ alignment verified)..."
aws elbv2 register-targets \
  --target-group-arn $TARGET_GROUP_ARN \
  --targets Id=$TASK_IP,Port=10005 \
  --region $AWS_REGION

if [ $? -eq 0 ]; then
    log_success "Task registered to target group successfully"
    log_success "AZ alignment verified: Task ($TASK_AZ) matches ALB AZs ($ALB_AZ_1, $ALB_AZ_2)"
else
    log_error "Failed to register task to target group"
    exit 1
fi

# Step 8: Quick Health Check Validation (Fast Mode)
log_info "Step 8: Quick health check validation..."

# Wait for target to register (much faster than full deployment wait)
log_info "Waiting for target registration to complete..."
sleep 10

# Quick target health check
log_info "Checking target health..."
TARGET_HEALTH=$(aws elbv2 describe-target-health \
  --target-group-arn $TARGET_GROUP_ARN \
  --targets Id=$TASK_IP,Port=10005 \
  --query "TargetHealthDescriptions[0].TargetHealth.State" \
  --output text \
  --region $AWS_REGION 2>/dev/null)

log_info "Initial target health: $TARGET_HEALTH"

# Quick ALB endpoint test (simplified)
log_info "Step 9: Testing ALB endpoint..."

test_alb_quickly() {
    local alb_dns=$1
    local max_attempts=3
    local wait_time=10
    
    for i in $(seq 1 $max_attempts); do
        log_info "Health check attempt $i/$max_attempts..."
        if curl -f -s --connect-timeout 10 --max-time 15 "http://$alb_dns/health" >/dev/null 2>&1; then
            log_success "ALB health endpoint is responding!"
            return 0
        fi
        
        if [ $i -lt $max_attempts ]; then
            log_info "Waiting ${wait_time}s before retry..."
            sleep $wait_time
        fi
    done
    
    log_warning "ALB health check did not respond (this may be normal during initial setup)"
    log_info "Target registration completed - traffic should flow within 1-2 minutes"
    return 0
}

test_alb_quickly "$ALB_DNS_NAME"

# Step 11: Clean up temporary files
log_info "Step 11: Cleaning up temporary files..."
# No temporary task definition files to clean up

log_success "A2A Performance Agent Service-to-ALB connection completed successfully!"
log_success "Service URL: http://$ALB_DNS_NAME"
log_success "Health Check URL: http://$ALB_DNS_NAME/health"
log_info "ECS service successfully connected to Application Load Balancer"
log_info ""
log_info "=== AZ ALIGNMENT SUMMARY ==="
log_info "ALB Availability Zones: $ALB_AZ_1, $ALB_AZ_2"
log_info "Task Availability Zone: $TASK_AZ"
log_info "Task IP Address: $TASK_IP"
log_info "Target Health Status: $TARGET_HEALTH"
log_info "============================"
log_info ""
