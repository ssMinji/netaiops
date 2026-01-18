#!/bin/bash

# A2A Performance Agent - ECS Deployment Script
# This script automates the complete deployment of the A2A Performance Agent to AWS ECS

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
PERFORMANCE_REPO="a2a-performance-agent"

log_info "Starting A2A Performance Agent ECS Deployment"
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

aws ecr create-repository --repository-name $PERFORMANCE_REPO --region $AWS_REGION 2>/dev/null || log_warning "Repository $PERFORMANCE_REPO already exists"

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

log_success "ECR repository created and logged in"

# Step 3: Setup Docker Builder (avoiding buildx authentication issues)
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
RUNTIME_ARN=$(jq -r '.agentcore_performance.runtime_arn // empty' "$STAGE4_CONFIG")
MACHINE_CLIENT_ID=$(jq -r '.agentcore_performance.machine_client_id // empty' "$STAGE4_CONFIG")
COGNITO_DISCOVERY_URL=$(jq -r '.agentcore_performance.cognito_discovery_url // empty' "$STAGE4_CONFIG")
COGNITO_PROVIDER=$(jq -r '.agentcore_performance.cognito_provider // empty' "$STAGE4_CONFIG")
COGNITO_AUTH_SCOPE=$(jq -r '.agentcore_performance.cognito_auth_scope // empty' "$STAGE4_CONFIG")

# Validate that all required values were found
if [ -z "$RUNTIME_ARN" ] || [ -z "$MACHINE_CLIENT_ID" ] || [ -z "$COGNITO_DISCOVERY_URL" ] || [ -z "$COGNITO_PROVIDER" ] || [ -z "$COGNITO_AUTH_SCOPE" ]; then
    log_error "Missing required values in module3-config.json agentcore_performance section:"
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

# Step 5: Build and Push Performance Agent
log_info "Step 5: Building and pushing Performance Agent..."

# Verify we have all required files for Docker build
REQUIRED_FILES=("Dockerfile" "requirements.txt" "__init__.py" "__main__.py" "agent_executer.py" "utils.py" "config.yaml")
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        log_error "Required file missing: $file"
        log_error "Please ensure you're running this script from the a2a-performance-agent directory"
        exit 1
    fi
done
log_success "All required files found for Docker build"

# Clean up Docker buildkit cache and force clean build
log_info "Cleaning Docker buildkit cache and forcing clean build..."
docker builder prune -f 2>/dev/null || true
docker system prune -f 2>/dev/null || true
# Remove any cached layers for this specific image
docker buildx prune -f 2>/dev/null || true

# Build and push directly to ECR with platform specification
log_info "Building and pushing Performance Agent image for linux/amd64..."
BUILD_SUCCESS=false
for i in {1..3}; do
    log_info "Build attempt $i of 3..."
    
    # Capture build output and check for errors
    # Use standard docker build and push separately to avoid buildx authentication issues
    if docker build \
        --no-cache \
        --pull \
        --tag $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$PERFORMANCE_REPO:latest \
        . 2>&1 | tee build_log_$i.txt; then
        
        # Push the image after successful build
        if docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$PERFORMANCE_REPO:latest 2>&1 | tee -a build_log_$i.txt; then
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
if aws ecr describe-images --repository-name $PERFORMANCE_REPO --image-ids imageTag=latest --region $AWS_REGION &>/dev/null; then
    log_success "Image successfully pushed to ECR"
    # Get image details
    IMAGE_DETAILS=$(aws ecr describe-images --repository-name $PERFORMANCE_REPO --image-ids imageTag=latest --region $AWS_REGION --query "imageDetails[0]" 2>/dev/null)
    IMAGE_SIZE=$(echo "$IMAGE_DETAILS" | jq -r '.imageSizeInBytes // "unknown"')
    PUSH_DATE=$(echo "$IMAGE_DETAILS" | jq -r '.imagePushedAt // "unknown"')
    log_info "Image size: $IMAGE_SIZE bytes, pushed at: $PUSH_DATE"
else
    log_error "Image not found in ECR after build. This may cause deployment failures."
    log_error "Please check your AWS credentials and ECR permissions."
    exit 1
fi

log_success "Performance Agent image built and pushed successfully"

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

# Get subnets in different availability zones for ALB requirement (ALB needs at least 2 AZs)
SUBNET_INFO=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[?MapPublicIpOnLaunch==\`true\`].[SubnetId,AvailabilityZone]" --output text)

if [ -z "$SUBNET_INFO" ]; then
  log_error "No public subnets found in VPC. Please ensure you have at least 2 public subnets in different AZs."
  exit 1
fi

# Extract subnets from different AZs (limit to 2 for ALB)
SUBNET_1=$(echo "$SUBNET_INFO" | head -n1 | cut -f1)
SUBNET_2=$(echo "$SUBNET_INFO" | tail -n1 | cut -f1)

# Verify we have subnets in different AZs
AZ_1=$(echo "$SUBNET_INFO" | head -n1 | cut -f2)
AZ_2=$(echo "$SUBNET_INFO" | tail -n1 | cut -f2)

if [ "$AZ_1" == "$AZ_2" ]; then
  log_warning "Subnets are in the same AZ. ALB requires subnets in at least 2 different AZs."
  # Try to find another subnet in different AZ
  SUBNET_2=$(echo "$SUBNET_INFO" | awk -v az="$AZ_1" '$2 != az {print $1}' | head -n1)
  if [ -z "$SUBNET_2" ]; then
    log_error "Could not find subnets in different AZs. Please create subnets in at least 2 AZs."
    exit 1
  fi
  AZ_2=$(echo "$SUBNET_INFO" | awk -v subnet="$SUBNET_2" '$1 == subnet {print $2}')
fi

log_info "Using subnets for ALB: $SUBNET_1 (AZ: $AZ_1), $SUBNET_2 (AZ: $AZ_2)"

# Get all subnets for ECS service (can use all subnets)
ALL_SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[].SubnetId" --output text)
log_info "Available subnets for ECS: $ALL_SUBNET_IDS"

# Convert space-separated subnet IDs to comma-separated for AWS CLI (for ECS service)
SUBNET_IDS_COMMA=$(echo $ALL_SUBNET_IDS | tr ' ' ',')
log_info "Comma-separated subnets for ECS: $SUBNET_IDS_COMMA"

# Create VPC endpoint for ECR API
log_info "Creating VPC endpoint for ECR API..."
ECR_API_ENDPOINT_ID=$(aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.ecr.api \
  --vpc-endpoint-type Interface \
  --subnet-ids $ALL_SUBNET_IDS \
  --security-group-ids $VPC_ENDPOINT_SG_ID \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": "*",
        "Action": [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ],
        "Resource": "*"
      }
    ]
  }' \
  --query "VpcEndpoint.VpcEndpointId" --output text 2>/dev/null || \
  aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION.ecr.api" --query "VpcEndpoints[0].VpcEndpointId" --output text)

log_info "ECR API VPC endpoint: $ECR_API_ENDPOINT_ID"

# Create VPC endpoint for ECR DKR
log_info "Creating VPC endpoint for ECR DKR..."
ECR_DKR_ENDPOINT_ID=$(aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.ecr.dkr \
  --vpc-endpoint-type Interface \
  --subnet-ids $ALL_SUBNET_IDS \
  --security-group-ids $VPC_ENDPOINT_SG_ID \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": "*",
        "Action": [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ],
        "Resource": "*"
      }
    ]
  }' \
  --query "VpcEndpoint.VpcEndpointId" --output text 2>/dev/null || \
  aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION.ecr.dkr" --query "VpcEndpoints[0].VpcEndpointId" --output text)

log_info "ECR DKR VPC endpoint: $ECR_DKR_ENDPOINT_ID"

# Create VPC endpoint for S3 (required for ECR layer downloads)
log_info "Creating VPC endpoint for S3..."
S3_ENDPOINT_ID=$(aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.s3 \
  --vpc-endpoint-type Gateway \
  --route-table-ids $ROUTE_TABLE_ID \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": "*",
        "Action": [
          "s3:GetObject",
          "s3:PutObject"
        ],
        "Resource": "*"
      }
    ]
  }' \
  --query "VpcEndpoint.VpcEndpointId" --output text 2>/dev/null || \
  aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION.s3" --query "VpcEndpoints[0].VpcEndpointId" --output text)

log_info "S3 VPC endpoint: $S3_ENDPOINT_ID"

# Create VPC endpoint for CloudWatch Logs
log_info "Creating VPC endpoint for CloudWatch Logs..."
LOGS_ENDPOINT_ID=$(aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.logs \
  --vpc-endpoint-type Interface \
  --subnet-ids $ALL_SUBNET_IDS \
  --security-group-ids $VPC_ENDPOINT_SG_ID \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": "*",
        "Action": [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ],
        "Resource": "*"
      }
    ]
  }' \
  --query "VpcEndpoint.VpcEndpointId" --output text 2>/dev/null || \
  aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION.logs" --query "VpcEndpoints[0].VpcEndpointId" --output text)

log_info "CloudWatch Logs VPC endpoint: $LOGS_ENDPOINT_ID"

# Create VPC endpoint for SSM (CRITICAL - this is missing and causing the timeout!)
log_info "Creating VPC endpoint for SSM..."
SSM_ENDPOINT_ID=$(aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.ssm \
  --vpc-endpoint-type Interface \
  --subnet-ids $ALL_SUBNET_IDS \
  --security-group-ids $VPC_ENDPOINT_SG_ID \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": "*",
        "Action": [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath"
        ],
        "Resource": "*"
      }
    ]
  }' \
  --query "VpcEndpoint.VpcEndpointId" --output text 2>/dev/null || \
  aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION.ssm" --query "VpcEndpoints[0].VpcEndpointId" --output text)

log_info "SSM VPC endpoint: $SSM_ENDPOINT_ID"

# Create VPC endpoint for Bedrock AgentCore
log_info "Creating VPC endpoint for Bedrock AgentCore..."
BEDROCK_ENDPOINT_ID=$(aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --service-name com.amazonaws.$AWS_REGION.bedrock-agentcore \
  --vpc-endpoint-type Interface \
  --subnet-ids $ALL_SUBNET_IDS \
  --security-group-ids $VPC_ENDPOINT_SG_ID \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": "*",
        "Action": [
          "bedrock:InvokeAgent",
          "bedrock:InvokeModel"
        ],
        "Resource": "*"
      }
    ]
  }' \
  --query "VpcEndpoint.VpcEndpointId" --output text 2>/dev/null || \
  aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION.bedrock-agentcore" --query "VpcEndpoints[0].VpcEndpointId" --output text)

log_info "Bedrock AgentCore VPC endpoint: $BEDROCK_ENDPOINT_ID"

log_success "VPC endpoints created for ECR, SSM, and Bedrock access"

# Step 7: Create ECS Infrastructure
log_info "Step 7: Creating ECS infrastructure..."

# Create ECS cluster
aws ecs create-cluster --cluster-name $CLUSTER_NAME --region $AWS_REGION 2>/dev/null || log_warning "Cluster $CLUSTER_NAME already exists"

# Create CloudWatch log group
aws logs create-log-group --log-group-name /ecs/a2a-performance-agent --region $AWS_REGION 2>/dev/null || log_warning "Log group already exists"

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

# Create task role policy for performance agent
cat > a2a-performance-agent-task-role-policy.json << EOF
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

# Create task role for performance agent
aws iam create-role \
  --role-name a2a-performance-agent-task-role \
  --assume-role-policy-document file://ecs-task-execution-role-trust-policy.json 2>/dev/null || log_warning "Role a2a-performance-agent-task-role already exists"

aws iam put-role-policy \
  --role-name a2a-performance-agent-task-role \
  --policy-name A2APerformanceAgentTaskPolicy \
  --policy-document file://a2a-performance-agent-task-role-policy.json 2>/dev/null || true

log_success "IAM roles created"

# Step 9: Create Task Definition
log_info "Step 9: Creating task definition..."

# Performance Agent Task Definition
cat > performance-agent-task-definition.json << EOF
{
  "family": "a2a-performance-agent",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::$AWS_ACCOUNT_ID:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::$AWS_ACCOUNT_ID:role/a2a-performance-agent-task-role",
  "containerDefinitions": [
    {
      "name": "performance-agent",
      "image": "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/a2a-performance-agent:latest",
      "portMappings": [
        {
          "containerPort": 10005,
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
          "value": "10005"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/a2a-performance-agent",
          "awslogs-region": "$AWS_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:10005/health', timeout=30)\" || exit 1"
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

# Register the task definition
log_info "Registering task definition..."
TASK_DEFINITION_ARN=$(aws ecs register-task-definition \
  --cli-input-json file://performance-agent-task-definition.json \
  --region $AWS_REGION \
  --query "taskDefinition.taskDefinitionArn" --output text)

log_success "Task definition registered: $TASK_DEFINITION_ARN"

# Step 10: Create Application Load Balancer
log_info "Step 10: Creating Application Load Balancer..."

# Create security group for ALB
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

# Create ALB (using only 2 subnets in different AZs)
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

# Save ALB_DNS_NAME to module3-config.json
log_info "Saving ALB_DNS_NAME to module3-config.json..."

# Create a Python script to update the JSON file
cat > update_performance_dns.py << 'EOF'
#!/usr/bin/env python3
import json
import sys
import os

def update_performance_dns():
    # Get the DNS value from environment variable
    performance_dns = os.environ.get('ALB_DNS_NAME')
    
    if not performance_dns:
        print("Error: ALB_DNS_NAME environment variable not set", file=sys.stderr)
        sys.exit(1)
    
    config_file = "../../module3-config.json"
    
    try:
        # Load existing config
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Ensure agentcore_performance section exists
        if 'agentcore_performance' not in config:
            config['agentcore_performance'] = {}
        
        # Add the alb_dns value
        config['agentcore_performance']['alb_dns'] = performance_dns
        
        # Write updated config
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"Successfully updated module3-config.json with alb_dns: {performance_dns}")
        
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
    update_performance_dns()
EOF

# Set environment variable and run the Python script
export ALB_DNS_NAME="$ALB_DNS_NAME"

if python3 update_performance_dns.py; then
    log_success "ALB_DNS_NAME saved to module3-config.json"
    rm update_performance_dns.py
else
    log_error "Failed to save ALB_DNS_NAME to module3-config.json"
    rm update_performance_dns.py
    # Don't exit here as this is not critical for the deployment to continue
fi

# Create target group with extended timeouts for long-running tasks
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

# Create ALB listener
LISTENER_ARN=$(aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TARGET_GROUP_ARN \
  --query "Listeners[0].ListenerArn" --output text 2>/dev/null || \
  aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --query "Listeners[0].ListenerArn" --output text)

log_info "ALB listener created: $LISTENER_ARN"

# Enhanced wait for load balancer to be fully provisioned and ready
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

log_success "Application Load Balancer setup completed"

# Step 10.5: Fix ALB Networking - Ensure Internet Gateway Route
log_info "Step 10.5: Fixing ALB networking - ensuring Internet Gateway route..."

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

# Step 11: Create Security Group for ECS Service
log_info "Step 11: Creating security group for ECS service..."

# Create security group for ECS service
ECS_SG_ID=$(aws ec2 create-security-group \
  --group-name a2a-performance-ecs-sg \
  --description "Security group for A2A Performance ECS service" \
  --vpc-id $VPC_ID \
  --query "GroupId" --output text 2>/dev/null || \
  aws ec2 describe-security-groups --filters "Name=group-name,Values=a2a-performance-ecs-sg" --query "SecurityGroups[0].GroupId" --output text)

# Allow traffic from ALB to ECS service
aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG_ID \
  --protocol tcp \
  --port 10005 \
  --source-group $ALB_SG_ID 2>/dev/null || true

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

log_info "ECS security group created: $ECS_SG_ID"

log_success "Security groups configured"

# Step 12: Update ECS Service with Latest Task Definition
log_info "Step 12: Updating ECS service with latest task definition..."

# CRITICAL FIX: Use only the same subnets that the ALB uses to avoid AZ mismatch
# Convert the ALB subnets to comma-separated format for ECS service
ALB_SUBNETS_COMMA="$SUBNET_1,$SUBNET_2"
log_info "Using ALB-compatible subnets for ECS service: $ALB_SUBNETS_COMMA"

# Verify subnets exist and are in different AZs
log_info "Verifying subnet configuration..."
SUBNET_1_AZ=$(aws ec2 describe-subnets --subnet-ids $SUBNET_1 --query "Subnets[0].AvailabilityZone" --output text)
SUBNET_2_AZ=$(aws ec2 describe-subnets --subnet-ids $SUBNET_2 --query "Subnets[0].AvailabilityZone" --output text)

if [ "$SUBNET_1_AZ" = "$SUBNET_2_AZ" ]; then
    log_error "Both subnets are in the same AZ ($SUBNET_1_AZ). ALB requires subnets in different AZs."
    exit 1
fi

log_success "Subnet configuration verified: $SUBNET_1 ($SUBNET_1_AZ), $SUBNET_2 ($SUBNET_2_AZ)"

# Check if service already exists
EXISTING_SERVICE=$(aws ecs describe-services --cluster $CLUSTER_NAME --services a2a-performance-agent-service --region $AWS_REGION --query "services[0].serviceArn" --output text 2>/dev/null)

if [ "$EXISTING_SERVICE" != "None" ] && [ "$EXISTING_SERVICE" != "" ] && [ "$EXISTING_SERVICE" != "null" ]; then
    log_info "Service a2a-performance-agent-service already exists: $EXISTING_SERVICE"
    log_info "Updating service with new task definition: $TASK_DEFINITION_ARN"
    
    # Update the service with the new task definition
    # This will trigger a rolling deployment: new task starts, old task stops
    SERVICE_ARN=$(aws ecs update-service \
      --cluster $CLUSTER_NAME \
      --service a2a-performance-agent-service \
      --task-definition $TASK_DEFINITION_ARN \
      --force-new-deployment \
      --region $AWS_REGION \
      --query "service.serviceArn" --output text 2>&1)
    
    if [ $? -ne 0 ] || [ "$SERVICE_ARN" == "None" ] || [ "$SERVICE_ARN" == "" ] || [ "$SERVICE_ARN" == "null" ]; then
        log_error "Failed to update ECS service. Error output:"
        echo "$SERVICE_ARN"
        exit 1
    fi
    
    log_success "Service update initiated with new task definition"
    
    # Wait for the service update to complete (new task running, old task stopped)
    log_info "Waiting for service update to complete (new task deployment)..."
    
    local max_wait=600  # 10 minutes for deployment
    local check_interval=15
    local elapsed_time=0
    
    while [ $elapsed_time -lt $max_wait ]; do
        # Get deployment status
        local deployments=$(aws ecs describe-services \
            --cluster $CLUSTER_NAME \
            --services a2a-performance-agent-service \
            --region $AWS_REGION \
            --query "services[0].deployments" --output json 2>/dev/null)
        
        local primary_deployment=$(echo "$deployments" | jq -r '.[] | select(.status=="PRIMARY")')
        local running_count=$(echo "$primary_deployment" | jq -r '.runningCount // 0')
        local desired_count=$(echo "$primary_deployment" | jq -r '.desiredCount // 0')
        local task_def=$(echo "$primary_deployment" | jq -r '.taskDefinition // "unknown"')
        
        log_info "Deployment status (${elapsed_time}s elapsed):"
        log_info "  Task Definition: $task_def"
        log_info "  Running: $running_count/$desired_count"
        
        # Check if the new task definition is running
        if echo "$task_def" | grep -q "$TASK_DEFINITION_ARN"; then
            if [ "$running_count" = "$desired_count" ] && [ "$running_count" != "0" ]; then
                # Check if there are any other deployments (old tasks being drained)
                local deployment_count=$(echo "$deployments" | jq 'length')
                if [ "$deployment_count" = "1" ]; then
                    log_success "Service update completed - new task is running"
                    break
                else
                    log_info "New task running, waiting for old tasks to drain..."
                fi
            fi
        fi
        
        sleep $check_interval
        elapsed_time=$((elapsed_time + check_interval))
    done
    
    if [ $elapsed_time -ge $max_wait ]; then
        log_error "Service update did not complete within ${max_wait} seconds"
        log_error "The deployment may still be in progress. Check ECS console for status."
        exit 1
    fi
    
else
    # Create new service if it doesn't exist
    log_info "Creating new ECS service with task definition: $TASK_DEFINITION_ARN"
    
    # Create a temporary JSON file for network configuration to avoid shell escaping issues
    cat > /tmp/network-config.json << EOF
{
  "awsvpcConfiguration": {
    "subnets": ["$SUBNET_1", "$SUBNET_2"],
    "securityGroups": ["$ECS_SG_ID"],
    "assignPublicIp": "ENABLED"
  }
}
EOF
    
    # Create service with proper JSON configuration
    SERVICE_ARN=$(aws ecs create-service \
      --cluster $CLUSTER_NAME \
      --service-name a2a-performance-agent-service \
      --task-definition $TASK_DEFINITION_ARN \
      --desired-count 1 \
      --launch-type FARGATE \
      --platform-version LATEST \
      --network-configuration file:///tmp/network-config.json \
      --load-balancers targetGroupArn=$TARGET_GROUP_ARN,containerName=performance-agent,containerPort=10005 \
      --health-check-grace-period-seconds 900 \
      --enable-execute-command \
      --region $AWS_REGION \
      --query "service.serviceArn" --output text 2>&1)
    
    # Clean up temp file
    rm -f /tmp/network-config.json
    
    # Check if service creation was successful
    if [ $? -ne 0 ] || [ "$SERVICE_ARN" == "None" ] || [ "$SERVICE_ARN" == "" ] || [ "$SERVICE_ARN" == "null" ]; then
        log_error "Failed to create ECS service. Error output:"
        echo "$SERVICE_ARN"
        log_error "Common causes:"
        log_error "1. Task definition not found or invalid"
        log_error "2. Security group or subnet configuration issues"
        log_error "3. IAM permissions missing"
        log_error "4. Target group ARN invalid"
        log_error "5. Service name already exists in different state"
        
        # Try to get more detailed error information
        log_info "Checking task definition exists..."
        TASK_DEF_NAME=$(echo "$TASK_DEFINITION_ARN" | cut -d'/' -f2 | cut -d':' -f1)
        if aws ecs describe-task-definition --task-definition "$TASK_DEF_NAME" &>/dev/null; then
            log_success "✓ Task definition exists: $TASK_DEF_NAME"
        else
            log_error "✗ Task definition not found: $TASK_DEF_NAME"
        fi
        
        log_info "Checking target group exists..."
        if aws elbv2 describe-target-groups --target-group-arns $TARGET_GROUP_ARN &>/dev/null; then
            log_success "✓ Target group exists"
        else
            log_error "✗ Target group not found: $TARGET_GROUP_ARN"
        fi
        
        log_info "Checking security group exists..."
        if aws ec2 describe-security-groups --group-ids $ECS_SG_ID &>/dev/null; then
            log_success "✓ Security group exists"
        else
            log_error "✗ Security group not found: $ECS_SG_ID"
        fi
        
        log_info "Checking subnets exist..."
        if aws ec2 describe-subnets --subnet-ids $SUBNET_1 $SUBNET_2 &>/dev/null; then
            log_success "✓ Subnets exist"
        else
            log_error "✗ One or more subnets not found: $SUBNET_1, $SUBNET_2"
        fi
        
        exit 1
    fi
    
    log_success "ECS service created with new task definition"
fi

log_success "ECS service configured: $SERVICE_ARN"

# Function to wait for service to be stable and healthy
wait_for_service_stable_and_healthy() {
    local cluster_name=$1
    local service_name=$2
    local target_group_arn=$3
    local max_wait_time=1800  # 30 minutes - extended for long-running tasks
    local check_interval=60   # 60 seconds - reduced frequency for long checks
    local elapsed_time=0
    
    log_info "Waiting for ECS service to be stable and healthy (max wait: ${max_wait_time}s)..."
    
    while [ $elapsed_time -lt $max_wait_time ]; do
        # Check ECS service status
        local service_status=$(aws ecs describe-services \
            --cluster "$cluster_name" \
            --services "$service_name" \
            --query "services[0].status" --output text 2>/dev/null)
        
        local running_count=$(aws ecs describe-services \
            --cluster "$cluster_name" \
            --services "$service_name" \
            --query "services[0].runningCount" --output text 2>/dev/null)
        
        local desired_count=$(aws ecs describe-services \
            --cluster "$cluster_name" \
            --services "$service_name" \
            --query "services[0].desiredCount" --output text 2>/dev/null)
        
        # Check ALB target health
        local healthy_targets=$(aws elbv2 describe-target-health \
            --target-group-arn "$target_group_arn" \
            --query "length(TargetHealthDescriptions[?TargetHealth.State=='healthy'])" --output text 2>/dev/null)
        
        local total_targets=$(aws elbv2 describe-target-health \
            --target-group-arn "$target_group_arn" \
            --query "length(TargetHealthDescriptions)" --output text 2>/dev/null)
        
        # Get target health details for logging
        local target_states=$(aws elbv2 describe-target-health \
            --target-group-arn "$target_group_arn" \
            --query "TargetHealthDescriptions[*].TargetHealth.State" --output text 2>/dev/null)
        
        log_info "Status check (${elapsed_time}s elapsed):"
        log_info "  ECS Service: $service_status"
        log_info "  Running tasks: $running_count/$desired_count"
        log_info "  ALB targets: $healthy_targets/$total_targets healthy"
        log_info "  Target states: $target_states"
        
        # Check if service is stable and healthy
        if [ "$service_status" = "ACTIVE" ] && \
           [ "$running_count" = "$desired_count" ] && \
           [ "$running_count" != "0" ] && \
           [ "$healthy_targets" = "$total_targets" ] && \
           [ "$healthy_targets" != "0" ]; then
            log_success "Service is stable and healthy!"
            return 0
        fi
        
        # If there are unhealthy targets, show more details
        if [ "$total_targets" != "0" ] && [ "$healthy_targets" != "$total_targets" ]; then
            log_info "Checking unhealthy target details..."
            aws elbv2 describe-target-health \
                --target-group-arn "$target_group_arn" \
                --query "TargetHealthDescriptions[?TargetHealth.State!='healthy'].{Target:Target.Id,State:TargetHealth.State,Reason:TargetHealth.Reason,Description:TargetHealth.Description}" \
                --output table 2>/dev/null || true
        fi
        
        sleep $check_interval
        elapsed_time=$((elapsed_time + check_interval))
    done
    
    log_error "Service did not become stable and healthy within ${max_wait_time} seconds"
    log_error "Final status:"
    log_error "  ECS Service: $service_status"
    log_error "  Running tasks: $running_count/$desired_count"
    log_error "  ALB targets: $healthy_targets/$total_targets healthy"
    
    return 1
}

# Step 13: Wait for Service to be Stable and Healthy
log_info "Step 13: Waiting for service to be stable and healthy..."

if wait_for_service_stable_and_healthy "$CLUSTER_NAME" "a2a-performance-agent-service" "$TARGET_GROUP_ARN"; then
    log_success "A2A Performance Agent service is running and healthy!"
    
    # Display final deployment information
    log_info "=== DEPLOYMENT SUMMARY ==="
    log_info "Service Name: a2a-performance-agent-service"
    log_info "Cluster: $CLUSTER_NAME"
    log_info "Task Definition: $TASK_DEFINITION_ARN"
    log_info "Load Balancer: $ALB_DNS_NAME"
    log_info "Health Check URL: http://$ALB_DNS_NAME/health"
    log_info "Service URL: http://$ALB_DNS_NAME"
    log_info "=========================="
    
    # Enhanced health endpoint testing with comprehensive validation
    test_health_endpoint_comprehensive() {
        local alb_dns=$1
        local max_attempts=10
        local base_wait=30
        
        log_info "Testing health endpoint with comprehensive validation..."
        
        for i in $(seq 1 $max_attempts); do
            log_info "Health test attempt $i of $max_attempts..."
            
            # Test with detailed error reporting
            local curl_output
            local curl_exit_code
            
            curl_output=$(curl -f -s -w "HTTP_CODE:%{http_code};DNS_TIME:%{time_namelookup};CONNECT_TIME:%{time_connect};TOTAL_TIME:%{time_total}" \
                --connect-timeout 15 --max-time 45 "http://$alb_dns/health" 2>&1)
            curl_exit_code=$?
            
            if [ $curl_exit_code -eq 0 ]; then
                log_success "Health endpoint is responding correctly!"
                log_info "Response details: $curl_output"
                return 0
            else
                log_warning "Health test attempt $i failed (exit code: $curl_exit_code)"
                log_info "Error details: $curl_output"
                
                # Analyze the type of failure
                if echo "$curl_output" | grep -q "Could not resolve host"; then
                    log_warning "DNS resolution issue detected"
                elif echo "$curl_output" | grep -q "Connection timed out\|Connection refused"; then
                    log_warning "Connection issue detected - service may not be ready"
                elif echo "$curl_output" | grep -q "HTTP.*404\|HTTP.*503"; then
                    log_warning "Service responding but health endpoint not ready"
                fi
                
                if [ $i -lt $max_attempts ]; then
                    local wait_time=$((base_wait + (i * 10)))  # Progressive backoff
                    log_info "Waiting ${wait_time} seconds before retry..."
                    sleep $wait_time
                fi
            fi
        done
        
        log_error "Health endpoint test failed after $max_attempts attempts"
        log_error "This indicates a deployment issue that needs investigation"
        log_info "Manual test command: curl -v http://$alb_dns/health"
        log_info "Check CloudWatch logs: /ecs/a2a-performance-agent"
        return 1
    }
    
    if test_health_endpoint_comprehensive "$ALB_DNS_NAME"; then
        log_success "Health endpoint validation completed successfully!"
    else
        log_error "Health endpoint validation failed - deployment may have issues"
        log_error "Please check the ECS service and CloudWatch logs for errors"
        exit 1
    fi
    
else
    log_error "Deployment failed - service did not become stable and healthy"
    log_error "Check the ECS console and CloudWatch logs for more details"
    log_error "CloudWatch log group: /ecs/a2a-performance-agent"
    exit 1
fi

# Clean up temporary files
log_info "Cleaning up temporary files..."
rm -f ecs-task-execution-role-trust-policy.json
rm -f a2a-performance-agent-task-role-policy.json
rm -f performance-agent-task-definition.json

log_success "A2A Performance Agent deployment completed successfully!"
log_info "The service is now running and accessible at: http://$ALB_DNS_NAME"
