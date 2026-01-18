#!/bin/bash

# Fix VPC Endpoint Policy for Bedrock AgentCore
# This script fixes the 403 Forbidden error by updating the VPC endpoint policy

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

log_info "Starting VPC Endpoint Policy Fix for Bedrock AgentCore"
log_info "AWS Region: $AWS_REGION"

# Check if module3-config.json exists
if [ ! -f "$STAGE4_CONFIG" ]; then
    log_error "module3-config.json not found at $STAGE4_CONFIG"
    exit 1
fi

# Get VPC ID from config or use default
VPC_ID_FROM_CONFIG=$(jq -r '.vpc_id // empty' "$STAGE4_CONFIG")
if [ -n "$VPC_ID_FROM_CONFIG" ]; then
    if aws ec2 describe-vpcs --vpc-ids "$VPC_ID_FROM_CONFIG" &>/dev/null; then
        VPC_ID="$VPC_ID_FROM_CONFIG"
        log_info "Using VPC from config: $VPC_ID"
    else
        log_warning "VPC from config ($VPC_ID_FROM_CONFIG) does not exist, falling back to default VPC"
        VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
    fi
else
    VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
fi

log_info "Using VPC: $VPC_ID"

# Find the Bedrock AgentCore VPC endpoint
log_info "Finding Bedrock AgentCore VPC endpoint..."
BEDROCK_ENDPOINT_ID=$(aws ec2 describe-vpc-endpoints \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION.bedrock-agentcore" \
    --query "VpcEndpoints[0].VpcEndpointId" --output text 2>/dev/null)

if [ "$BEDROCK_ENDPOINT_ID" == "None" ] || [ -z "$BEDROCK_ENDPOINT_ID" ]; then
    log_error "No Bedrock AgentCore VPC endpoint found in VPC $VPC_ID"
    log_error "Please run the deployment script first to create the VPC endpoint"
    exit 1
fi

log_info "Found Bedrock AgentCore VPC endpoint: $BEDROCK_ENDPOINT_ID"

# Create the correct VPC endpoint policy
log_info "Creating corrected VPC endpoint policy..."

cat > bedrock-agentcore-vpc-endpoint-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": "*",
            "Action": [
                "bedrock-agentcore:InvokeAgentRuntime",
                "bedrock-agentcore:InvokeAgent",
                "bedrock:InvokeAgent",
                "bedrock:InvokeModel"
            ],
            "Resource": "*"
        }
    ]
}
EOF

# Update the VPC endpoint policy
log_info "Updating VPC endpoint policy..."
if aws ec2 modify-vpc-endpoint \
    --vpc-endpoint-id "$BEDROCK_ENDPOINT_ID" \
    --policy-document file://bedrock-agentcore-vpc-endpoint-policy.json; then
    log_success "VPC endpoint policy updated successfully"
else
    log_error "Failed to update VPC endpoint policy"
    exit 1
fi

# Wait for the policy to propagate
log_info "Waiting for policy changes to propagate (30 seconds)..."
sleep 30

# Verify the policy was applied
log_info "Verifying policy update..."
CURRENT_POLICY=$(aws ec2 describe-vpc-endpoints \
    --vpc-endpoint-ids "$BEDROCK_ENDPOINT_ID" \
    --query "VpcEndpoints[0].PolicyDocument" --output text 2>/dev/null)

if echo "$CURRENT_POLICY" | grep -q "bedrock-agentcore:InvokeAgentRuntime"; then
    log_success "Policy verification successful - bedrock-agentcore:InvokeAgentRuntime action is now allowed"
else
    log_warning "Policy verification inconclusive - please check manually"
fi

# Clean up temporary files
rm -f bedrock-agentcore-vpc-endpoint-policy.json

log_success "VPC endpoint policy fix completed!"
log_info "The Bedrock AgentCore VPC endpoint now allows the required actions"
log_info "You can now retry running your a2a-performance-agent"

# Restart the ECS service to pick up the changes
# Set SKIP_ECS_RESTART=true to skip this step
if [ "${SKIP_ECS_RESTART}" != "true" ]; then
    log_info "Restarting ECS service..."
    
    CLUSTER_NAME="a2a-agents-cluster"
    SERVICE_NAME="a2a-performance-agent-service"
    
    # Force new deployment
    if aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service "$SERVICE_NAME" \
        --force-new-deployment \
        --query "service.serviceArn" --output text >/dev/null 2>&1; then
        log_success "ECS service restart initiated"
        log_info "Monitor the service status in the ECS console"
    else
        log_warning "Failed to restart ECS service - you may need to restart it manually"
    fi
else
    log_info "Skipping ECS service restart (SKIP_ECS_RESTART=true)"
fi

log_success "Fix completed! The 403 Forbidden error should now be resolved."
