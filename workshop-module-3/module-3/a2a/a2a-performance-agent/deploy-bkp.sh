#!/bin/bash

# A2A Performance Agent - Parent Deployment Script
# This script runs the three deployment scripts in the correct order:
# 1. deploy-docker-hub-auth.sh - Fixes Docker Hub authentication issues
# 2. deploy-to-ecs.sh - Deploys the agent to ECS with ALB
# 3. deploy-vpc-endpoint-policy.sh - Fixes VPC endpoint policies for Bedrock

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[PARENT]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PARENT]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[PARENT]${NC} $1"
}

log_error() {
    echo -e "${RED}[PARENT]${NC} $1"
}

log_milestone() {
    echo ""
    echo -e "${GREEN}[MILESTONE]${NC} $1"
    echo ""
}

# Function to run a script and capture its exit status
run_script() {
    local script_name=$1
    local description=$2
    local log_file="${script_name%.sh}.log"
    
    log_info "Starting: $description"
    log_info "Running: $script_name"
    log_info "Output will be logged to: $log_file"
    
    # Make script executable and run it, capturing all output
    if chmod +x "./$script_name" && "./$script_name" > "$log_file" 2>&1; then
        log_success "Completed: $description"
        return 0
    else
        local exit_code=$?
        log_error "Failed: $description (exit code: $exit_code)"
        log_error "Check log file for details: $log_file"
        
        # Show last few lines of the log for immediate context
        log_error "Last 10 lines of output:"
        tail -n 10 "$log_file" 2>/dev/null || echo "Could not read log file"
        
        return $exit_code
    fi
}

# Start deployment
log_milestone "Starting A2A Performance Agent Parent Deployment"
log_info "This script will run three deployment scripts in sequence:"
log_info "1. Docker Hub Authentication"
log_info "2. ECS Deployment with ALB"
log_info "3. VPC Endpoint Policy Updates"
echo ""

# Check if we're in the correct directory
if [ ! -f "deploy-docker-hub-auth.sh" ] || [ ! -f "deploy-to-ecs.sh" ] || [ ! -f "deploy-vpc-endpoint-policy.sh" ]; then
    log_error "Required deployment scripts not found in current directory"
    log_error "Please ensure you're running this script from the a2a-performance-agent directory"
    log_error "Expected files:"
    log_error "  - deploy-docker-hub-auth.sh"
    log_error "  - deploy-to-ecs.sh"
    log_error "  - deploy-vpc-endpoint-policy.sh"
    exit 1
fi

# Record start time
START_TIME=$(date +%s)
log_info "Deployment started at: $(date)"

# Step 1: Docker Hub Authentication Fix
log_milestone "STEP 1/3: Updating Docker Hub Authentication"
if run_script "deploy-docker-hub-auth.sh" "Docker Hub Authentication Update"; then
    log_milestone "✓ Docker Hub authentication resolved"
else
    log_error "Docker Hub authentication failed"
    exit 1
fi

# Step 2: ECS Deployment
log_milestone "STEP 2/3: Deploying A2A Performance Agent to ECS"
if run_script "deploy-to-ecs.sh" "ECS Deployment with Application Load Balancer"; then
    log_milestone "✓ A2A Performance Agent deployed to ECS successfully"
    log_success "Application Load Balancer configured and healthy"
else
    log_error "ECS deployment failed"
    exit 1
fi

# Step 3: VPC Endpoint Policy Update
log_milestone "STEP 3/3: Updating VPC Endpoint Policies for Bedrock"
if run_script "deploy-vpc-endpoint-policy.sh" "VPC Endpoint Policy Update for Bedrock AgentCore"; then
    log_milestone "✓ VPC endpoint policies updated for Bedrock access"
else
    log_error "VPC endpoint policy update failed"
    exit 1
fi

# Calculate total deployment time
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))
MINUTES=$((TOTAL_TIME / 60))
SECONDS=$((TOTAL_TIME % 60))

# Final success message
echo ""
echo "=========================================="
log_milestone "🎉 DEPLOYMENT COMPLETED SUCCESSFULLY! 🎉"
echo "=========================================="
echo ""
log_success "All three deployment steps completed successfully:"
log_success "✓ Docker Hub authentication updated"
log_success "✓ A2A Performance Agent deployed to ECS"
log_success "✓ VPC endpoint policies configured"
echo ""
log_info "Total deployment time: ${MINUTES}m ${SECONDS}s"
log_info "Deployment completed at: $(date)"
echo ""

# Extract and display key information from logs
log_info "=== DEPLOYMENT SUMMARY ==="

# Try to extract ALB DNS name from ECS deployment log
if [ -f "deploy-to-ecs.log" ]; then
    ALB_DNS=$(grep -o "ALB DNS Name: [^[:space:]]*" deploy-to-ecs.log | tail -1 | cut -d' ' -f4 2>/dev/null || echo "Not found in logs")
    if [ "$ALB_DNS" != "Not found in logs" ]; then
        log_success "Application Load Balancer: $ALB_DNS"
        log_success "Health Check URL: http://$ALB_DNS/health"
        log_success "Service URL: http://$ALB_DNS"
    fi
fi

# Try to extract cluster information
if [ -f "deploy-to-ecs.log" ]; then
    CLUSTER_NAME=$(grep -o "Cluster: [^[:space:]]*" deploy-to-ecs.log | tail -1 | cut -d' ' -f2 2>/dev/null || echo "a2a-agents-cluster")
    log_info "ECS Cluster: $CLUSTER_NAME"
    log_info "ECS Service: a2a-performance-agent-service"
fi

echo ""
log_info "=== LOG FILES ==="
log_info "Detailed logs available in:"
log_info "  - deploy-docker-hub-auth.log"
log_info "  - deploy-to-ecs.log"
log_info "  - deploy-vpc-endpoint-policy.log"
echo ""

log_info "=== NEXT STEPS ==="
log_info "1. Test the health endpoint to verify the service is running"
log_info "2. Check CloudWatch logs: /ecs/a2a-performance-agent"
log_info "3. Monitor the ECS service in the AWS Console"
log_info "4. The agent is now ready for A2A performance monitoring and troubleshooting"
echo ""

log_milestone "Deployment parent script completed successfully!"

# Additional post-deployment tasks
echo ""
log_milestone "STEP 4/4: Running Post-Deployment ALB Status Update and S3 Upload"

# Get AWS Account ID
log_info "Getting AWS Account ID..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$AWS_ACCOUNT_ID" ]; then
    log_error "Failed to get AWS Account ID. Please ensure AWS CLI is configured."
    exit 1
fi
log_info "AWS Account ID: $AWS_ACCOUNT_ID"

# Change to the a2a directory to run the Python script and S3 upload
log_info "Changing to a2a directory..."
cd ../../ || {
    log_error "Failed to change to a2a directory"
    exit 1
}

# Run update_alb_status.py script
log_info "Running ALB status update script..."
if python3 ./update_alb_status.py; then
    log_success "ALB status updated successfully"
else
    log_error "Failed to update ALB status"
    exit 1
fi

# Upload alb_access_guide.html to S3
log_info "Uploading ALB access guide to S3..."
S3_BUCKET="baseline-deploy-${AWS_ACCOUNT_ID}"
S3_KEY="module-3/alb_access_guide.html"
log_info "S3 destination: s3://${S3_BUCKET}/${S3_KEY}"

if aws s3 cp alb_access_guide.html "s3://${S3_BUCKET}/${S3_KEY}"; then
    log_success "ALB access guide uploaded to S3 successfully"
    log_success "S3 URL: https://s3.amazonaws.com/${S3_BUCKET}/${S3_KEY}"
else
    log_error "Failed to upload ALB access guide to S3"
    exit 1
fi

# Return to original directory
cd a2a-performance-agent/ || log_warning "Could not return to original directory"

log_milestone "✓ All post-deployment tasks completed successfully!"
