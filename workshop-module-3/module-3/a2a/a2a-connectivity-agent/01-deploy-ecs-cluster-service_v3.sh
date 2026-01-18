#!/bin/bash

# A2A Connectivity Troubleshooting Agent - ECS Cluster and Service Deployment (Part 1/3)
# This script creates ECS cluster, task definition, and service without ALB

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
CONNECTIVITY_REPO="a2a-connectivity-agent"

log_info "Starting A2A Connectivity Troubleshooting Agent ECS Cluster and Service Deployment (Part 1/3)"
log_info "AWS Region: $AWS_REGION"

# Step 1: Validate Prerequisites
log_info "Step 1: Validating prerequisites..."

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed. Please install it first."
    exit 1
fi

# Check jq for JSON parsing
if ! command -v jq &> /dev/null; then
    log_error "jq is not installed. Please install it first (required for JSON parsing)."
    log_info "On Ubuntu/Debian: sudo apt-get install jq"
    log_info "On RHEL/CentOS: sudo yum install jq"
    log_info "On macOS: brew install jq"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    log_error "AWS credentials not configured. Please run 'aws configure' first."
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log_success "Prerequisites validated. AWS Account ID: $AWS_ACCOUNT_ID"

# Step 2: Create ECR Repository
log_info "Step 2: Creating ECR repository..."

aws ecr create-repository --repository-name $CONNECTIVITY_REPO --region $AWS_REGION 2>/dev/null || log_warning "Repository $CONNECTIVITY_REPO already exists"

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

log_success "ECR repository created and logged in"

# Step 3: Setup Docker Builder
log_info "Step 3: Setting up Docker builder for AMD64 builds..."

# Clean up any existing buildx configuration that might cause issues
docker buildx rm multiarch-builder 2>/dev/null || true
docker buildx prune -f 2>/dev/null || true

# Use default docker builder to avoid Docker Hub authentication issues
log_info "Using default docker builder to avoid buildkit authentication requirements..."
docker buildx use default 2>/dev/null || true

# Verify docker is working
if docker version >/dev/null 2>&1; then
    log_success "Docker is working correctly"
else
    log_error "Docker is not accessible"
    exit 1
fi

log_success "Docker builder configured successfully (using default builder)"

# Step 4: Update config.yaml with values from module3-config.json
log_info "Step 4: Updating config.yaml with values from module3-config.json..."

# Check if module3-config.json exists
STAGE4_CONFIG="../../module3-config.json"
if [ ! -f "$STAGE4_CONFIG" ]; then
    log_error "module3-config.json not found at $STAGE4_CONFIG"
    log_error "Please ensure module3-config.json exists in the module-3 directory"
    exit 1
fi

# Extract values from module3-config.json
RUNTIME_ARN=$(jq -r '.agentcore_troubleshooting.runtime_arn // empty' "$STAGE4_CONFIG")
MACHINE_CLIENT_ID=$(jq -r '.agentcore_troubleshooting.machine_client_id // empty' "$STAGE4_CONFIG")
COGNITO_DISCOVERY_URL=$(jq -r '.agentcore_troubleshooting.cognito_discovery_url // empty' "$STAGE4_CONFIG")
COGNITO_PROVIDER=$(jq -r '.agentcore_troubleshooting.cognito_provider // empty' "$STAGE4_CONFIG")
COGNITO_AUTH_SCOPE=$(jq -r '.agentcore_troubleshooting.cognito_auth_scope // empty' "$STAGE4_CONFIG")

# Validate that all required values were found
if [ -z "$RUNTIME_ARN" ] || [ -z "$MACHINE_CLIENT_ID" ] || [ -z "$COGNITO_DISCOVERY_URL" ] || [ -z "$COGNITO_PROVIDER" ] || [ -z "$COGNITO_AUTH_SCOPE" ]; then
    log_error "Missing required values in module3-config.json agentcore_troubleshooting section:"
    log_error "  runtime_arn: $RUNTIME_ARN"
    log_error "  machine_client_id: $MACHINE_CLIENT_ID"
    log_error "  cognito_discovery_url: $COGNITO_DISCOVERY_URL"
    log_error "  cognito_provider: $COGNITO_PROVIDER"
    log_error "  cognito_auth_scope: $COGNITO_AUTH_SCOPE"
    exit 1
fi

log_info "Found configuration values:"
log_info "  Agent ARN: $RUNTIME_ARN"
log_info "  Client ID: $MACHINE_CLIENT_ID"
log_info "  Discovery URL: $COGNITO_DISCOVERY_URL"
log_info "  Identity Group: $COGNITO_PROVIDER"
log_info "  Scope: $COGNITO_AUTH_SCOPE"

# Create a backup of the original config.yaml
cp config.yaml config.yaml.backup
log_info "Created backup: config.yaml.backup"

# Update config.yaml using a Python script
cat > update_config_temp.py << 'EOF'
#!/usr/bin/env python3
import yaml
import sys
import os

def update_config():
    # Get values from environment variables
    runtime_arn = os.environ.get('RUNTIME_ARN')
    machine_client_id = os.environ.get('MACHINE_CLIENT_ID')
    cognito_discovery_url = os.environ.get('COGNITO_DISCOVERY_URL')
    cognito_provider = os.environ.get('COGNITO_PROVIDER')
    cognito_auth_scope = os.environ.get('COGNITO_AUTH_SCOPE')
    
    if not all([runtime_arn, machine_client_id, cognito_discovery_url, cognito_provider, cognito_auth_scope]):
        print("Error: Missing required environment variables", file=sys.stderr)
        sys.exit(1)
    
    # Load existing config
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config.yaml: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Update agent_card_info section
    if 'agent_card_info' not in config:
        config['agent_card_info'] = {}
    
    config['agent_card_info']['agent_arn'] = runtime_arn
    config['agent_card_info']['client_id'] = machine_client_id
    config['agent_card_info']['discovery_url'] = cognito_discovery_url
    config['agent_card_info']['identity_group'] = cognito_provider
    config['agent_card_info']['scope'] = cognito_auth_scope
    
    # Write updated config
    try:
        with open('config.yaml', 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print("Successfully updated config.yaml")
    except Exception as e:
        print(f"Error writing config.yaml: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    update_config()
EOF

# Set environment variables and run the Python script
export RUNTIME_ARN="$RUNTIME_ARN"
export MACHINE_CLIENT_ID="$MACHINE_CLIENT_ID"
export COGNITO_DISCOVERY_URL="$COGNITO_DISCOVERY_URL"
export COGNITO_PROVIDER="$COGNITO_PROVIDER"
export COGNITO_AUTH_SCOPE="$COGNITO_AUTH_SCOPE"

if python3 update_config_temp.py; then
    log_success "config.yaml updated successfully"
    rm update_config_temp.py
else
    log_error "Failed to update config.yaml"
    # Restore backup
    cp config.yaml.backup config.yaml
    rm update_config_temp.py
    exit 1
fi

# Step 5: Build and Push Connectivity Agent
log_info "Step 5: Building and pushing Connectivity Agent..."

# Verify we have all required files for Docker build
REQUIRED_FILES=("Dockerfile" "requirements.txt" "__init__.py" "__main__.py" "agent_executer.py" "utils.py" "config.yaml")
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        log_error "Required file missing: $file"
        log_error "Please ensure you're running this script from the a2a-connectivity-agent directory"
        exit 1
    fi
done
log_success "All required files found for Docker build"

# Clean up Docker buildkit cache and force clean build
log_info "Cleaning Docker buildkit cache and forcing clean build..."
docker builder prune -f 2>/dev/null || true
docker system prune -f 2>/dev/null || true
docker buildx prune -f 2>/dev/null || true

# Build and push directly to ECR with platform specification
log_info "Building and pushing Connectivity Agent image for linux/amd64..."
BUILD_SUCCESS=false
for i in {1..3}; do
    log_info "Build attempt $i of 3..."
    
    # Capture build output and check for errors
    # Use standard docker build and push separately to avoid buildx authentication issues
    if docker build \
        --no-cache \
        --pull \
        --tag $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$CONNECTIVITY_REPO:latest \
        . 2>&1 | tee build_log_$i.txt; then
        
        # Push the image after successful build
        if docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$CONNECTIVITY_REPO:latest 2>&1 | tee -a build_log_$i.txt; then
            log_success "Build and push completed successfully"
        else
            log_warning "Build succeeded but push failed"
            continue
        fi
        
        # Check if build actually succeeded by looking for error patterns
        if grep -q "ERROR\|failed to solve\|exit code:" build_log_$i.txt; then
            log_warning "Build attempt $i failed (detected errors in build log)"
            log_info "Build log saved to build_log_$i.txt"
            log_info "Error details:"
            grep -A 2 -B 2 "ERROR\|failed to solve\|exit code:" build_log_$i.txt || true
        else
            BUILD_SUCCESS=true
            log_success "Build and push attempt $i succeeded"
            break
        fi
    else
        log_warning "Build attempt $i failed (docker command returned non-zero exit code)"
        log_info "Build log saved to build_log_$i.txt"
    fi
    
    if [ $i -lt 3 ]; then
        log_info "Retrying in 10 seconds..."
        sleep 10
        docker system prune -f 2>/dev/null || true
    fi
done

if [ "$BUILD_SUCCESS" = false ]; then
    log_error "Failed to build and push Docker image after 3 attempts"
    log_error "Check the build logs (build_log_*.txt) for details"
    exit 1
fi

# Verify the image exists in ECR
log_info "Verifying image exists in ECR..."
if aws ecr describe-images --repository-name $CONNECTIVITY_REPO --image-ids imageTag=latest --region $AWS_REGION &>/dev/null; then
    log_success "Image successfully pushed to ECR"
    # Get image details
    IMAGE_DETAILS=$(aws ecr describe-images --repository-name $CONNECTIVITY_REPO --image-ids imageTag=latest --region $AWS_REGION --query "imageDetails[0]" 2>/dev/null)
    IMAGE_SIZE=$(echo "$IMAGE_DETAILS" | jq -r '.imageSizeInBytes // "unknown"')
    PUSH_DATE=$(echo "$IMAGE_DETAILS" | jq -r '.imagePushedAt // "unknown"')
    log_info "Image size: $IMAGE_SIZE bytes, pushed at: $PUSH_DATE"
else
    log_error "Image not found in ECR after build. This may cause deployment failures."
    log_error "Please check your AWS credentials and ECR permissions."
    exit 1
fi

log_success "Connectivity Agent image built and pushed successfully"

# Step 6: Create VPC Endpoints for ECR Access
log_info "Step 6: Creating VPC endpoints for ECR access..."

# Get VPC ID from module3-config.json or use default VPC
VPC_ID_FROM_CONFIG=$(jq -r '.vpc_id // empty' "$STAGE4_CONFIG")
if [ -n "$VPC_ID_FROM_CONFIG" ]; then
    # Verify the VPC exists before using it
    if aws ec2 describe-vpcs --vpc-ids "$VPC_ID_FROM_CONFIG" &>/dev/null; then
        VPC_ID="$VPC_ID_FROM_CONFIG"
        log_info "Using VPC from config: $VPC_ID"
    else
        log_warning "VPC from config ($VPC_ID_FROM_CONFIG) does not exist, falling back to default VPC"
        VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
        log_info "Using default VPC: $VPC_ID"
    fi
else
    VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
    log_info "Using default VPC: $VPC_ID"
fi

# Validate that we have a valid VPC ID
if [ "$VPC_ID" == "None" ] || [ -z "$VPC_ID" ]; then
    log_error "No valid VPC found. Please ensure you have a default VPC or specify a valid VPC ID in module3-config.json"
    exit 1
fi

# Save VPC_ID to config for other scripts
jq --arg vpc_id "$VPC_ID" '.vpc_id = $vpc_id' "$STAGE4_CONFIG" > "$STAGE4_CONFIG.tmp" && mv "$STAGE4_CONFIG.tmp" "$STAGE4_CONFIG"

# Get route table for the VPC
ROUTE_TABLE_ID=$(aws ec2 describe-route-tables --filters "Name=vpc-id,Values=$VPC_ID" "Name=association.main,Values=true" --query "RouteTables[0].RouteTableId" --output text)
log_info "Using route table: $ROUTE_TABLE_ID"

# Create security group for VPC endpoints
VPC_ENDPOINT_SG_ID=$(aws ec2 create-security-group \
  --group-name a2a-vpc-endpoints-sg \
  --description "Security group for A2A VPC endpoints" \
  --vpc-id $VPC_ID \
  --query "GroupId" --output text 2>/dev/null || \
  aws ec2 describe-security-groups --filters "Name=group-name,Values=a2a-vpc-endpoints-sg" --query "SecurityGroups[0].GroupId" --output text)

# Allow HTTPS traffic from VPC CIDR to VPC endpoints
VPC_CIDR=$(aws ec2 describe-vpcs --vpc-ids $VPC_ID --query "Vpcs[0].CidrBlock" --output text)
aws ec2 authorize-security-group-ingress \
  --group-id $VPC_ENDPOINT_SG_ID \
  --protocol tcp \
  --port 443 \
  --cidr $VPC_CIDR 2>/dev/null || true

log_info "VPC Endpoint security group created: $VPC_ENDPOINT_SG_ID"

# Get all subnets for VPC endpoints
ALL_SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[].SubnetId" --output text)
log_info "Available subnets for VPC endpoints: $ALL_SUBNET_IDS"

# Get subnets in first 2 AZs for ECS service (to match future ALB deployment)
log_info "Selecting subnets in first 2 availability zones for ECS service (to match ALB)..."
SUBNET_INFO=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[].[SubnetId,AvailabilityZone]" --output text)

# Get unique AZs and select first 2
UNIQUE_AZS=$(echo "$SUBNET_INFO" | awk '{print $2}' | sort -u | head -n 2)
AZ_ARRAY=($UNIQUE_AZS)

if [ ${#AZ_ARRAY[@]} -lt 2 ]; then
    log_error "Need at least 2 availability zones for ALB compatibility. Found: ${#AZ_ARRAY[@]}"
    exit 1
fi

log_info "Selected availability zones: ${AZ_ARRAY[0]}, ${AZ_ARRAY[1]}"

# Get all subnets in these 2 AZs for ECS service
ECS_SUBNET_IDS=$(echo "$SUBNET_INFO" | awk -v az1="${AZ_ARRAY[0]}" -v az2="${AZ_ARRAY[1]}" '$2 == az1 || $2 == az2 {print $1}')

if [ -z "$ECS_SUBNET_IDS" ]; then
    log_error "No subnets found in selected AZs"
    exit 1
fi

log_info "ECS service will use subnets in AZs ${AZ_ARRAY[0]} and ${AZ_ARRAY[1]}: $(echo $ECS_SUBNET_IDS | tr '\n' ' ')"

# Save the selected AZs to config for ALB script to use
jq --arg az1 "${AZ_ARRAY[0]}" --arg az2 "${AZ_ARRAY[1]}" \
   '.selected_azs = {az_1: $az1, az_2: $az2}' \
   "$STAGE4_CONFIG" > "$STAGE4_CONFIG.tmp" && mv "$STAGE4_CONFIG.tmp" "$STAGE4_CONFIG"

# Create VPC endpoints
log_info "Creating VPC endpoints..."

# ECR API endpoint
aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.ecr.api \
  --vpc-endpoint-type Interface \
  --subnet-ids $ALL_SUBNET_IDS \
  --security-group-ids $VPC_ENDPOINT_SG_ID 2>/dev/null || log_warning "ECR API endpoint may already exist"

# ECR DKR endpoint
aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.ecr.dkr \
  --vpc-endpoint-type Interface \
  --subnet-ids $ALL_SUBNET_IDS \
  --security-group-ids $VPC_ENDPOINT_SG_ID 2>/dev/null || log_warning "ECR DKR endpoint may already exist"

# S3 endpoint (required for ECR layer downloads)
aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.s3 \
  --vpc-endpoint-type Gateway \
  --route-table-ids $ROUTE_TABLE_ID 2>/dev/null || log_warning "S3 endpoint may already exist"

# CloudWatch Logs endpoint
aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.logs \
  --vpc-endpoint-type Interface \
  --subnet-ids $ALL_SUBNET_IDS \
  --security-group-ids $VPC_ENDPOINT_SG_ID 2>/dev/null || log_warning "Logs endpoint may already exist"

# SSM endpoint (CRITICAL - this is missing and causing the timeout!)
aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.ssm \
  --vpc-endpoint-type Interface \
  --subnet-ids $ALL_SUBNET_IDS \
  --security-group-ids $VPC_ENDPOINT_SG_ID 2>/dev/null || log_warning "SSM endpoint may already exist"

# Bedrock AgentCore endpoint
aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.bedrock-agentcore \
  --vpc-endpoint-type Interface \
  --subnet-ids $ALL_SUBNET_IDS \
  --security-group-ids $VPC_ENDPOINT_SG_ID 2>/dev/null || log_warning "Bedrock endpoint may already exist"

log_success "VPC endpoints created for ECR, SSM, and Bedrock access"

# Wait for VPC endpoints to become fully available
log_info "Waiting for VPC endpoints to become fully available (2 minutes)..."
log_info "This ensures endpoints are ready before ECS service creation"
sleep 60
log_success "VPC endpoint stabilization period complete"

# Step 7: Create ECS Infrastructure
log_info "Step 7: Creating ECS infrastructure..."

# Create ECS cluster
aws ecs create-cluster --cluster-name $CLUSTER_NAME --region $AWS_REGION 2>/dev/null || log_warning "Cluster $CLUSTER_NAME already exists"

# Create CloudWatch log group
aws logs create-log-group --log-group-name /ecs/a2a-connectivity-agent --region $AWS_REGION 2>/dev/null || log_warning "Log group already exists"

log_success "ECS infrastructure created"

# Step 8: Create IAM Roles and Service-Linked Role
log_info "Step 8: Creating IAM roles and ECS service-linked role..."

# Create ECS Service-Linked Role (required for ALB integration)
log_info "Creating ECS service-linked role for ALB integration..."
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com 2>/dev/null || log_warning "ECS service-linked role already exists"

# Create ECS task execution role trust policy
cat > ecs-task-execution-role-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create ECS task execution role
aws iam create-role \
  --role-name ecsTaskExecutionRole \
  --assume-role-policy-document file://ecs-task-execution-role-trust-policy.json 2>/dev/null || log_warning "Role ecsTaskExecutionRole already exists"

aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy 2>/dev/null || true

# Create task role policy for connectivity agent
cat > a2a-connectivity-agent-task-role-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath"
      ],
      "Resource": [
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/performance/agentcore/*",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/troubleshooting/agentcore/*",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/troubleshooting/agentcore/gateway_url",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/troubleshooting/agentcore/machine_client_secret",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/troubleshooting/agentcore/machine_client_id",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/troubleshooting/agentcore/cognito_discovery_url",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/troubleshooting/agentcore/cognito_auth_scope",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/troubleshooting/agentcore/cognito_provider",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/troubleshooting/agentcore/cognito_token_url",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/performance/agentcore/gateway_url",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/performance/agentcore/machine_client_secret",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/performance/agentcore/machine_client_id",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/performance/agentcore/cognito_discovery_url",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/performance/agentcore/cognito_auth_scope",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/performance/agentcore/cognito_provider",
        "arn:aws:ssm:$AWS_REGION:*:parameter/a2a/app/performance/agentcore/cognito_token_url"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeAgent",
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
EOF

# Create task role for connectivity agent
aws iam create-role \
  --role-name a2a-connectivity-agent-task-role \
  --assume-role-policy-document file://ecs-task-execution-role-trust-policy.json 2>/dev/null || log_warning "Role a2a-connectivity-agent-task-role already exists"

aws iam put-role-policy \
  --role-name a2a-connectivity-agent-task-role \
  --policy-name A2AConnectivityAgentTaskPolicy \
  --policy-document file://a2a-connectivity-agent-task-role-policy.json 2>/dev/null || true

log_success "IAM roles created"

# Step 9: Create Security Group for ECS Service
log_info "Step 9: Creating security group for ECS service..."

ECS_SG_ID=$(aws ec2 create-security-group \
  --group-name a2a-connectivity-ecs-sg \
  --description "Security group for A2A Connectivity ECS service" \
  --vpc-id $VPC_ID \
  --query "GroupId" --output text 2>/dev/null || \
  aws ec2 describe-security-groups --filters "Name=group-name,Values=a2a-connectivity-ecs-sg" --query "SecurityGroups[0].GroupId" --output text)

# Allow outbound HTTPS traffic for AWS API calls
aws ec2 authorize-security-group-egress \
  --group-id $ECS_SG_ID \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0 2>/dev/null || true

# Allow outbound HTTP traffic
aws ec2 authorize-security-group-egress \
  --group-id $ECS_SG_ID \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0 2>/dev/null || true

# Allow inbound HTTP traffic from anywhere (will be restricted by ALB later)
aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG_ID \
  --protocol tcp \
  --port 10003 \
  --cidr 0.0.0.0/0 2>/dev/null || true

log_info "ECS security group created: $ECS_SG_ID"

# Step 10: Create ECS Service with Full Task Definition
log_info "Step 10: Creating ECS service with full task definition..."

# Create comprehensive task definition with health checks
cat > connectivity-agent-task-definition.json << EOF
{
  "family": "a2a-connectivity-agent",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::$AWS_ACCOUNT_ID:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::$AWS_ACCOUNT_ID:role/a2a-connectivity-agent-task-role",
  "containerDefinitions": [
    {
      "name": "connectivity-agent",
      "image": "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/a2a-connectivity-agent:latest",
      "portMappings": [
        {
          "containerPort": 10003,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "AWS_DEFAULT_REGION",
          "value": "$AWS_REGION"
        },
        {
          "name": "HOST",
          "value": "0.0.0.0"
        },
        {
          "name": "PORT",
          "value": "10003"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/a2a-connectivity-agent",
          "awslogs-region": "$AWS_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:10003/health', timeout=30)\" || exit 1"
        ],
        "interval": 60,
        "timeout": 30,
        "retries": 5,
        "startPeriod": 300
      },
      "essential": true
    }
  ]
}
EOF

# Register the full task definition
log_info "Registering full task definition with health checks..."
TASK_DEFINITION_ARN=$(aws ecs register-task-definition \
  --cli-input-json file://connectivity-agent-task-definition.json \
  --region $AWS_REGION \
  --query "taskDefinition.taskDefinitionArn" --output text)

log_success "Full task definition registered: $TASK_DEFINITION_ARN"

# Create a temporary JSON file for network configuration using only the selected 2-AZ subnets
cat > /tmp/network-config.json << EOF
{
  "awsvpcConfiguration": {
    "subnets": [$( echo $ECS_SUBNET_IDS | sed 's/ /","/g' | sed 's/^/"/' | sed 's/$/"/' )],
    "securityGroups": ["$ECS_SG_ID"],
    "assignPublicIp": "ENABLED"
  }
}
EOF

# Create service WITHOUT load balancer with retry mechanism
# Retry logic: 3 attempts with 30 seconds wait between retries
SERVICE_CREATE_SUCCESS=false
MAX_RETRIES=3

for attempt in $(seq 1 $MAX_RETRIES); do
    log_info "ECS service creation attempt $attempt of $MAX_RETRIES..."
    
    # First check if service already exists and is ACTIVE
    SERVICE_STATUS=$(aws ecs describe-services \
      --cluster $CLUSTER_NAME \
      --services a2a-connectivity-agent-service \
      --region $AWS_REGION \
      --query "services[0].status" --output text 2>/dev/null || echo "")

    if [ "$SERVICE_STATUS" = "ACTIVE" ]; then
        log_warning "Service a2a-connectivity-agent-service already exists and is ACTIVE. Updating with new task definition..."
        # Update the service instead of creating a new one
        SERVICE_ARN=$(aws ecs update-service \
          --cluster $CLUSTER_NAME \
          --service a2a-connectivity-agent-service \
          --task-definition $TASK_DEFINITION_ARN \
          --region $AWS_REGION \
          --query "service.serviceArn" --output text 2>&1)
        SERVICE_CREATE_EXIT_CODE=$?
    elif [ "$SERVICE_STATUS" = "INACTIVE" ]; then
        log_warning "Service exists but is INACTIVE. Waiting for complete deletion..."
        sleep 60
        log_info "Creating new ECS service..."
        SERVICE_ARN=$(aws ecs create-service \
          --cluster $CLUSTER_NAME \
          --service-name a2a-connectivity-agent-service \
          --task-definition $TASK_DEFINITION_ARN \
          --desired-count 1 \
          --launch-type FARGATE \
          --platform-version LATEST \
          --network-configuration file:///tmp/network-config.json \
          --enable-execute-command \
          --region $AWS_REGION \
          --query "service.serviceArn" --output text 2>&1)
        SERVICE_CREATE_EXIT_CODE=$?
    else
        # Create new service
        log_info "Creating new ECS service..."
        SERVICE_ARN=$(aws ecs create-service \
          --cluster $CLUSTER_NAME \
          --service-name a2a-connectivity-agent-service \
          --task-definition $TASK_DEFINITION_ARN \
          --desired-count 1 \
          --launch-type FARGATE \
          --platform-version LATEST \
          --network-configuration file:///tmp/network-config.json \
          --enable-execute-command \
          --region $AWS_REGION \
          --query "service.serviceArn" --output text 2>&1)
        SERVICE_CREATE_EXIT_CODE=$?
    fi

    # Check if service creation/update was successful
    if [ $SERVICE_CREATE_EXIT_CODE -eq 0 ] && [ "$SERVICE_ARN" != "None" ] && [ -n "$SERVICE_ARN" ] && [ "$SERVICE_ARN" != "null" ]; then
        log_success "ECS service created/updated successfully: $SERVICE_ARN"
        SERVICE_CREATE_SUCCESS=true
        break
    else
        log_warning "Attempt $attempt failed. Exit code: $SERVICE_CREATE_EXIT_CODE"
        log_warning "Error output: $SERVICE_ARN"
        
        if [ $attempt -lt $MAX_RETRIES ]; then
            log_info "Waiting 30 seconds before retry..."
            sleep 30
        fi
    fi
done

# Clean up temp file
rm -f /tmp/network-config.json

# Final check if service creation succeeded
if [ "$SERVICE_CREATE_SUCCESS" = false ]; then
    log_error "Failed to create/update ECS service after $MAX_RETRIES attempts"
    log_error "Last error: $SERVICE_ARN"
    exit 1
fi

# Note: Service stability check removed to prevent CloudFormation timeouts
# The service will continue deploying in the background
# You can check service status manually with:
#   aws ecs describe-services --cluster $CLUSTER_NAME --services a2a-connectivity-agent-service
# And check task logs in CloudWatch Logs: /ecs/a2a-connectivity-agent

log_info "ECS service deployment initiated. Service will become available once tasks are running and healthy."
log_warning "Note: Service stability check has been skipped to prevent timeouts."
log_info "The service may take 5-10 minutes to become fully operational."

# Get task public IP for testing
log_info "Getting task public IP..."
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER_NAME --service-name a2a-connectivity-agent-service --query "taskArns[0]" --output text)
if [ "$TASK_ARN" != "None" ] && [ -n "$TASK_ARN" ]; then
    TASK_PUBLIC_IP=$(aws ecs describe-tasks --cluster $CLUSTER_NAME --tasks $TASK_ARN --query "tasks[0].attachments[0].details[?name=='publicIPv4Address'].value" --output text)
    if [ -n "$TASK_PUBLIC_IP" ] && [ "$TASK_PUBLIC_IP" != "None" ]; then
        log_success "Task is running with public IP: $TASK_PUBLIC_IP"
        log_info "You can test the service at: http://$TASK_PUBLIC_IP:10003/health"
        
        # Save task IP to config for reference
        jq --arg task_ip "$TASK_PUBLIC_IP" '.agentcore_troubleshooting.task_ip = $task_ip' "$STAGE4_CONFIG" > "$STAGE4_CONFIG.tmp" && mv "$STAGE4_CONFIG.tmp" "$STAGE4_CONFIG"
    fi
fi

# Clean up temporary files
log_info "Cleaning up temporary files..."
rm -f ecs-task-execution-role-trust-policy.json
rm -f a2a-connectivity-agent-task-role-policy.json
rm -f connectivity-agent-task-definition.json

log_success "A2A Connectivity Troubleshooting Agent ECS Cluster and Service deployment completed!"
log_info "Cluster: $CLUSTER_NAME"
log_info "Service: a2a-connectivity-agent-service"
log_info "Task Definition: $TASK_DEFINITION_ARN"
log_info "ECS service created with full task definition and health checks"
log_info "Next step: Run 02-deploy-alb.sh to create the Application Load Balancer"
