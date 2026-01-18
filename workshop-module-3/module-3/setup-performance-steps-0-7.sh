#!/bin/bash

# Performance Agent Setup Script - Steps 0-7
# This script automates the deployment of the AgentCore Performance Agent

# Note: We don't use 'set -e' here because we want to handle specific errors gracefully

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Global variables for resource tracking
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID=""
RESOURCES_FILE="performance-agent-resources.yml"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Function to print colored output
print_step() {
    echo -e "${BLUE}[STEP $1]${NC} $2"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if we're in the right directory
check_directory() {
    if [[ ! -f "3-setup-performance.md" ]]; then
        print_error "This script should be run from the netops-agentic-ai directory"
        print_error "Please navigate to the directory containing 3-setup-performance.md"
        exit 1
    fi
}

# Function to initialize resources YAML file
init_resources_file() {
    cat > "$RESOURCES_FILE" << EOF
# Performance Agent Resources
# Generated on: $TIMESTAMP
# Account: $ACCOUNT_ID
# Region: $REGION

metadata:
  created_at: "$TIMESTAMP"
  account_id: "$ACCOUNT_ID"
  region: "$REGION"
  script_version: "setup-performance-steps-0-7.sh"

resources:
EOF
}

# Function to add resource to YAML file
add_resource() {
    local resource_type="$1"
    local resource_name="$2"
    local resource_arn="$3"
    local additional_info="$4"
    
    cat >> "$RESOURCES_FILE" << EOF
  - type: "$resource_type"
    name: "$resource_name"
    arn: "$resource_arn"
    region: "$REGION"
    created_at: "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    additional_info: "$additional_info"
EOF
}

# Function to get AWS account ID
get_account_id() {
    if command_exists aws; then
        ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
    else
        ACCOUNT_ID="unknown"
    fi
}

echo "=========================================="
echo "Performance Agent Setup - Steps 0-7"
echo "=========================================="

# Check if we're in the right directory
check_directory

# Get AWS account ID and initialize resources file
get_account_id
init_resources_file
print_success "Initialized resource tracking file: $RESOURCES_FILE"

# Step 0: Setup AWS credentials
print_step "0" "Setting up AWS credentials"
if command_exists ada; then
    ada cred update --account=104398007905 --provider=isengard --role=Admin --profile=default --once
    print_success "AWS credentials updated"
else
    print_warning "ada command not found. Please ensure AWS credentials are configured manually"
    print_warning "Run: ada cred update --account=104398007905 --provider=isengard --role=Admin --profile=default --once"
fi

# Step 1: Navigate to the Performance Agent Directory
print_step "1" "Navigating to the Performance Agent Directory"
if [[ -d "agentcore-performance-agent" ]]; then
    cd agentcore-performance-agent
    print_success "Changed to agentcore-performance-agent directory"
else
    print_error "agentcore-performance-agent directory not found"
    exit 1
fi

# Step 2: Setup Dependencies
print_step "2" "Setting up dependencies"
if [[ -f "./scripts/setup-dependencies.sh" ]]; then
    chmod +x ./scripts/setup-dependencies.sh
    ./scripts/setup-dependencies.sh
    print_success "Dependencies setup completed"
else
    print_error "setup-dependencies.sh script not found"
    exit 1
fi

# Step 3: Deploy Infrastructure
print_step "3" "Deploying infrastructure"
if [[ -f "./scripts/prereq.sh" ]]; then
    chmod +x ./scripts/prereq.sh
    # Run the prereq script and capture output
    if output=$(./scripts/prereq.sh 2>&1); then
        print_success "Infrastructure deployment completed"
    else
        # Check if the error is just "No updates are to be performed"
        if echo "$output" | grep -q "No updates are to be performed"; then
            print_warning "Stack already exists and is up to date - continuing"
            print_success "Infrastructure deployment completed (no updates needed)"
        else
            print_error "Infrastructure deployment failed"
            echo "$output"
            exit 1
        fi
    fi
    
    # Capture infrastructure resources
    STACK_NAME="a2a-performance-agentcore-cognito"
    STACK_ARN="arn:aws:cloudformation:${REGION}:${ACCOUNT_ID}:stack/${STACK_NAME}"
    add_resource "CloudFormation Stack" "$STACK_NAME" "$STACK_ARN" "Cognito infrastructure stack"
    
    # Capture Cognito User Pool
    USER_POOL_ID=$(aws ssm get-parameter --name "/a2a/app/performance/agentcore/userpool_id" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")
    if [[ -n "$USER_POOL_ID" ]]; then
        USER_POOL_ARN="arn:aws:cognito-idp:${REGION}:${ACCOUNT_ID}:userpool/${USER_POOL_ID}"
        add_resource "Cognito User Pool" "$USER_POOL_ID" "$USER_POOL_ARN" "Performance agent authentication"
    fi
    
    # Capture test user
    add_resource "Cognito User" "test@example.com" "N/A" "Test user for performance agent"
    
else
    print_error "prereq.sh script not found"
    exit 1
fi

# Step 4: Activate Virtual Environment and Setup Authentication
print_step "4" "Activating virtual environment and setting up authentication"

# Check if virtual environment exists
if [[ -d ".venv" ]]; then
    source .venv/bin/activate
    print_success "Virtual environment activated"
else
    print_error "Virtual environment not found. Dependencies setup may have failed."
    exit 1
fi

# Setup authentication
if [[ -f "scripts/cognito_credentials_provider.py" ]]; then
    if output=$(python3 scripts/cognito_credentials_provider.py create-provider 2>&1); then
        print_success "Authentication setup completed"
    else
        # Check if provider already exists
        if echo "$output" | grep -q -i "already exists\|already created"; then
            print_warning "Authentication provider already exists - continuing"
            print_success "Authentication setup completed (already exists)"
        else
            print_error "Authentication setup failed"
            echo "$output"
            exit 1
        fi
    fi
else
    print_error "cognito_credentials_provider.py not found"
    exit 1
fi

# Step 5: Deploy Performance Tools
print_step "5" "Deploying performance tools"
if [[ -f "./prerequisite/lambda-performance/deploy-performance-tools.sh" ]]; then
    chmod +x ./prerequisite/lambda-performance/deploy-performance-tools.sh
    
    print_warning "This step may take 10-30 minutes due to Docker operations..."
    print_warning "Please be patient while Docker builds and pushes the container image"
    
    # Run the deployment script with real-time output
    echo "Starting performance tools deployment..."
    if ./prerequisite/lambda-performance/deploy-performance-tools.sh; then
        print_success "Performance tools deployment completed"
    else
        exit_code=$?
        print_error "Performance tools deployment failed with exit code: $exit_code"
        print_error "You can try running the script manually for more detailed output:"
        print_error "cd agentcore-performance-agent && ./prerequisite/lambda-performance/deploy-performance-tools.sh"
        exit 1
    fi
    
    # Capture performance tools resources
    LAMBDA_FUNCTION_NAME="a2a-performance-tools"
    LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${LAMBDA_FUNCTION_NAME}"
    add_resource "Lambda Function" "$LAMBDA_FUNCTION_NAME" "$LAMBDA_ARN" "Performance tools container-based Lambda"
    
    # Capture ECR repository
    ECR_REPOSITORY="a2a-performance-tools-repo"
    ECR_ARN="arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/${ECR_REPOSITORY}"
    add_resource "ECR Repository" "$ECR_REPOSITORY" "$ECR_ARN" "Container images for performance tools"
    
    # Capture Lambda execution role
    LAMBDA_ROLE_NAME="a2a-performance-tools-role"
    LAMBDA_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}"
    add_resource "IAM Role" "$LAMBDA_ROLE_NAME" "$LAMBDA_ROLE_ARN" "Lambda execution role with performance tools permissions"
    
else
    print_error "deploy-performance-tools.sh script not found"
    exit 1
fi

# Step 6: Setup Memory Configuration
print_step "6" "Setting up memory configuration"
if [[ -f "scripts/setup_memory.py" ]]; then
    if output=$(python3 scripts/setup_memory.py --action create 2>&1); then
        print_success "Memory configuration setup completed"
    else
        # Check if memory already exists
        if echo "$output" | grep -q -i "already exists\|already created\|already configured"; then
            print_warning "Memory configuration already exists - continuing"
            print_success "Memory configuration setup completed (already exists)"
        else
            print_error "Memory configuration setup failed"
            echo "$output"
            exit 1
        fi
    fi
else
    print_error "setup_memory.py script not found"
    exit 1
fi

# Step 7: Create Gateway and Runtime
print_step "7" "Creating gateway and runtime"

# Create gateway
if [[ -f "scripts/agentcore_gateway.py" ]]; then
    if output=$(python3 scripts/agentcore_gateway.py create --name a2a-performance-gateway 2>&1); then
        print_success "Gateway created successfully"
    else
        # Check if gateway already exists
        if echo "$output" | grep -q -i "already exists\|already created"; then
            print_warning "Gateway already exists - continuing"
            print_success "Gateway created successfully (already exists)"
        else
            print_error "Gateway creation failed"
            echo "$output"
            exit 1
        fi
    fi
else
    print_error "agentcore_gateway.py script not found"
    exit 1
fi

# Create runtime
if [[ -f "scripts/agentcore_agent_runtime.py" ]]; then
    if output=$(python3 scripts/agentcore_agent_runtime.py create --name a2a_performance_agent_runtime 2>&1); then
        print_success "Runtime created successfully"
    else
        # Check if runtime already exists
        if echo "$output" | grep -q -i "already exists\|already created"; then
            print_warning "Runtime already exists - continuing"
            print_success "Runtime created successfully (already exists)"
        else
            print_error "Runtime creation failed"
            echo "$output"
            exit 1
        fi
    fi
else
    print_error "agentcore_agent_runtime.py script not found"
    exit 1
fi

# Capture gateway and runtime resources
GATEWAY_NAME="a2a-performance-gateway"
GATEWAY_ID=$(aws ssm get-parameter --name "/a2a/app/performance/agentcore/gateway_id" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")
if [[ -n "$GATEWAY_ID" ]]; then
    GATEWAY_ARN=$(aws ssm get-parameter --name "/a2a/app/performance/agentcore/gateway_arn" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")
    add_resource "Bedrock Agent Gateway" "$GATEWAY_NAME" "$GATEWAY_ARN" "AgentCore gateway for performance agent"
fi

RUNTIME_NAME="a2a_performance_agent_runtime"
RUNTIME_ARN="arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:agent-runtime/${RUNTIME_NAME}"
add_resource "Bedrock Agent Runtime" "$RUNTIME_NAME" "$RUNTIME_ARN" "AgentCore runtime for performance agent"

# Capture memory configuration
add_resource "Agent Memory" "performance-agent-memory" "N/A" "Memory configuration for performance agent"

# Step 8: Generate Final Resource Summary
print_step "8" "Generating final resource summary"

# Add SSM parameters to the resources file
cat >> "$RESOURCES_FILE" << EOF

ssm_parameters:
EOF

# List of SSM parameters created during setup
SSM_PARAMETERS=(
    "/a2a/app/performance/agentcore/machine_client_id"
    "/a2a/app/performance/agentcore/web_client_id"
    "/a2a/app/performance/agentcore/cognito_provider"
    "/a2a/app/performance/agentcore/cognito_domain"
    "/a2a/app/performance/agentcore/cognito_token_url"
    "/a2a/app/performance/agentcore/cognito_discovery_url"
    "/a2a/app/performance/agentcore/cognito_auth_url"
    "/a2a/app/performance/agentcore/cognito_auth_scope"
    "/a2a/app/performance/agentcore/userpool_id"
    "/a2a/app/performance/agentcore/gateway_iam_role"
    "/a2a/app/performance/agentcore/lambda_arn"
    "/a2a/app/performance/agentcore/gateway_id"
    "/a2a/app/performance/agentcore/gateway_name"
    "/a2a/app/performance/agentcore/gateway_arn"
    "/a2a/app/performance/agentcore/gateway_url"
)

for param in "${SSM_PARAMETERS[@]}"; do
    if VALUE=$(aws ssm get-parameter --name "$param" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null); then
        cat >> "$RESOURCES_FILE" << EOF
  - name: "$param"
    value: "$VALUE"
    region: "$REGION"
EOF
    fi
done

# Add cleanup instructions
cat >> "$RESOURCES_FILE" << EOF

cleanup_instructions:
  script: "../cleanup-performance-agent.sh"
  description: "Run this script to clean up all resources created by this setup"
  warning: "This will permanently delete all resources and cannot be undone"

tools_and_capabilities:
  - name: "analyze_vpc_flow_metrics"
    description: "Analyze VPC flow monitoring data for performance issues"
  - name: "create_subnet_flow_monitor"
    description: "Create subnet-level VPC Flow Logs monitoring"
  - name: "setup_traffic_mirroring"
    description: "Configure VPC Traffic Mirroring for packet analysis"
  - name: "analyze_tcp_performance"
    description: "Analyze TCP performance between IP addresses"
  - name: "install_network_flow_monitor_agent"
    description: "Install network monitoring agent via SSM"

local_files:
  - name: "Virtual Environment"
    path: ".venv/"
    description: "Python virtual environment with dependencies"
  - name: "Configuration Backup"
    path: "../stage4-config.json.backup"
    description: "Backup of original configuration file"
EOF

# Move the resources file to the parent directory (netops-agentic-ai)
mv "$RESOURCES_FILE" "../$RESOURCES_FILE"
print_success "Resource summary saved to: ../$RESOURCES_FILE"

echo ""
echo "=========================================="
print_success "All steps (0-7) completed successfully!"
echo "=========================================="
echo ""
echo "Your Performance Agent is now ready!"
echo ""
echo "Available capabilities:"
echo "- Analyze VPC Flow Metrics"
echo "- Create Subnet Flow Monitors"
echo "- Setup Traffic Mirroring"
echo "- Analyze TCP Performance"
echo "- Install Network Flow Monitor Agent"
echo ""
echo "📋 Resource Summary:"
echo "   All created resources have been documented in: ../$RESOURCES_FILE"
echo "   This file contains ARNs, names, and details of all AWS resources created"
echo "   Use this file with the cleanup script to ensure complete resource removal"
echo ""
echo "You can now test your performance agent using the examples in the documentation."
echo ""
print_warning "Note: Make sure to keep the virtual environment activated when working with the agent"
print_warning "To reactivate later, run: source .venv/bin/activate"
