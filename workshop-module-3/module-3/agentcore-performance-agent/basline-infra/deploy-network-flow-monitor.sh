#!/bin/bash

# ==============================================================================
# Network Flow Monitor - CloudFormation Deployment Script
# ==============================================================================
# This script deploys the network-flow-monitor-vpc.yaml CloudFormation template
# It retrieves VPC IDs from the existing sample-application stack
# Part of the NetOps Agentic AI Workshop - AgentCore Performance Agent
# ==============================================================================

set -e  # Exit on any error

# ==============================================================================
# CONFIGURATION VARIABLES
# ==============================================================================

# Default configuration - modify these as needed
MONITOR_STACK_NAME="${MONITOR_STACK_NAME:-acme-network-flow-monitor}"
BASE_STACK_NAME="${BASE_STACK_NAME:-acme-image-gallery}"
AWS_REGION="${AWS_REGION:-us-east-1}"
TEMPLATE_FILE="network-flow-monitor-vpc.yaml"
MONITOR_NAME="${MONITOR_NAME:-acme-vpc-network-monitor}"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_PATH="${SCRIPT_DIR}/${TEMPLATE_FILE}"

# VPC IDs (will be retrieved from base stack)
APP_VPC_ID=""
REPORTING_VPC_ID=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

print_banner() {
    echo -e "${BLUE}"
    echo "=================================================================="
    echo "        Network Flow Monitor Deployment Script"
    echo "          NetOps Agentic AI Workshop Infrastructure"
    echo "=================================================================="
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

print_section() {
    echo
    echo -e "${BLUE}==== $1 ====${NC}"
}

# ==============================================================================
# PREREQUISITE CHECKS
# ==============================================================================

check_prerequisites() {
    print_section "Checking Prerequisites"
    
    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed. Please install it first."
        echo "Installation guide: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        exit 1
    fi
    print_success "AWS CLI is installed"
    
    # Check AWS CLI configuration
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS CLI is not configured or credentials are invalid."
        echo "Run 'aws configure' to set up your credentials."
        exit 1
    fi
    
    # Get and display AWS account info
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    CURRENT_USER=$(aws sts get-caller-identity --query Arn --output text)
    print_success "AWS credentials configured"
    print_info "Account ID: ${ACCOUNT_ID}"
    print_info "User/Role: ${CURRENT_USER}"
    
    # Check if template file exists
    if [ ! -f "$TEMPLATE_PATH" ]; then
        print_error "Template file not found: $TEMPLATE_PATH"
        exit 1
    fi
    print_success "CloudFormation template found"
    
    # Validate template
    print_info "Validating CloudFormation template..."
    if aws cloudformation validate-template --template-body file://"$TEMPLATE_PATH" --region "$AWS_REGION" &> /dev/null; then
        print_success "CloudFormation template is valid"
    else
        print_error "CloudFormation template validation failed"
        aws cloudformation validate-template --template-body file://"$TEMPLATE_PATH" --region "$AWS_REGION"
        exit 1
    fi
}

# ==============================================================================
# VPC ID RETRIEVAL
# ==============================================================================

get_vpc_ids_from_base_stack() {
    print_section "Retrieving VPC IDs from Base Stack"
    
    print_info "Base Stack Name: $BASE_STACK_NAME"
    
    # Check if base stack exists
    if ! aws cloudformation describe-stacks --stack-name "$BASE_STACK_NAME" --region "$AWS_REGION" &> /dev/null; then
        print_error "Base stack '$BASE_STACK_NAME' does not exist"
        print_info "Please deploy the sample-application.yaml stack first using deploy.sh"
        exit 1
    fi
    
    # Get stack status
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$BASE_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text)
    
    print_info "Base Stack Status: $STACK_STATUS"
    
    if [[ ! $STACK_STATUS =~ ^(CREATE_COMPLETE|UPDATE_COMPLETE)$ ]]; then
        print_error "Base stack is not in a complete state: $STACK_STATUS"
        print_info "Please ensure the base stack deployment is complete"
        exit 1
    fi
    
    print_success "Base stack is in a complete state"
    
    # Retrieve App VPC ID
    print_info "Retrieving App VPC ID..."
    APP_VPC_ID=$(aws cloudformation describe-stacks \
        --stack-name "$BASE_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`AppVPCId`].OutputValue' \
        --output text 2>/dev/null)
    
    if [ -z "$APP_VPC_ID" ] || [ "$APP_VPC_ID" == "None" ]; then
        print_error "Failed to retrieve App VPC ID from base stack"
        print_info "Checking stack resources directly..."
        
        APP_VPC_ID=$(aws cloudformation describe-stack-resources \
            --stack-name "$BASE_STACK_NAME" \
            --region "$AWS_REGION" \
            --query 'StackResources[?LogicalResourceId==`AppVPC`].PhysicalResourceId' \
            --output text 2>/dev/null)
        
        if [ -z "$APP_VPC_ID" ] || [ "$APP_VPC_ID" == "None" ]; then
            print_error "Could not find App VPC in base stack"
            exit 1
        fi
    fi
    
    print_success "App VPC ID: $APP_VPC_ID"
    
    # Retrieve Reporting VPC ID
    print_info "Retrieving Reporting VPC ID..."
    REPORTING_VPC_ID=$(aws cloudformation describe-stacks \
        --stack-name "$BASE_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`ReportingVPCId`].OutputValue' \
        --output text 2>/dev/null)
    
    if [ -z "$REPORTING_VPC_ID" ] || [ "$REPORTING_VPC_ID" == "None" ]; then
        print_error "Failed to retrieve Reporting VPC ID from base stack"
        print_info "Checking stack resources directly..."
        
        REPORTING_VPC_ID=$(aws cloudformation describe-stack-resources \
            --stack-name "$BASE_STACK_NAME" \
            --region "$AWS_REGION" \
            --query 'StackResources[?LogicalResourceId==`ReportingVPC`].PhysicalResourceId' \
            --output text 2>/dev/null)
        
        if [ -z "$REPORTING_VPC_ID" ] || [ "$REPORTING_VPC_ID" == "None" ]; then
            print_error "Could not find Reporting VPC in base stack"
            exit 1
        fi
    fi
    
    print_success "Reporting VPC ID: $REPORTING_VPC_ID"
    
    # Verify VPCs exist
    print_info "Verifying VPCs exist in AWS..."
    
    if aws ec2 describe-vpcs --vpc-ids "$APP_VPC_ID" --region "$AWS_REGION" &> /dev/null; then
        print_success "App VPC verified"
    else
        print_error "App VPC $APP_VPC_ID does not exist in AWS"
        exit 1
    fi
    
    if aws ec2 describe-vpcs --vpc-ids "$REPORTING_VPC_ID" --region "$AWS_REGION" &> /dev/null; then
        print_success "Reporting VPC verified"
    else
        print_error "Reporting VPC $REPORTING_VPC_ID does not exist in AWS"
        exit 1
    fi
}

# ==============================================================================
# STACK MANAGEMENT FUNCTIONS
# ==============================================================================

check_stack_exists() {
    aws cloudformation describe-stacks --stack-name "$MONITOR_STACK_NAME" --region "$AWS_REGION" &> /dev/null
}

get_stack_status() {
    aws cloudformation describe-stacks \
        --stack-name "$MONITOR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_EXISTS"
}

wait_for_stack_complete() {
    local operation=$1
    print_info "Waiting for stack $operation to complete..."
    
    aws cloudformation wait "stack-${operation}-complete" \
        --stack-name "$MONITOR_STACK_NAME" \
        --region "$AWS_REGION"
    
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        print_success "Stack $operation completed successfully"
    else
        print_error "Stack $operation failed or timed out"
        show_stack_events
        exit 1
    fi
}

show_stack_events() {
    print_section "Recent Stack Events"
    aws cloudformation describe-stack-events \
        --stack-name "$MONITOR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'StackEvents[0:10].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
        --output table || true
}

show_stack_outputs() {
    print_section "Stack Outputs"
    
    aws cloudformation describe-stacks \
        --stack-name "$MONITOR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}' \
        --output table
    
    # Get and highlight the monitor ARN
    MONITOR_ARN=$(aws cloudformation describe-stacks \
        --stack-name "$MONITOR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`NetworkFlowMonitorArn`].OutputValue' \
        --output text 2>/dev/null || echo "Not found")
    
    if [ "$MONITOR_ARN" != "Not found" ] && [ "$MONITOR_ARN" != "None" ]; then
        echo
        print_success "Network Flow Monitor ARN: $MONITOR_ARN"
    fi
    
    # Get dashboard URL
    DASHBOARD_URL=$(aws cloudformation describe-stacks \
        --stack-name "$MONITOR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DashboardURL`].OutputValue' \
        --output text 2>/dev/null || echo "Not found")
    
    if [ "$DASHBOARD_URL" != "Not found" ] && [ "$DASHBOARD_URL" != "None" ]; then
        print_info "CloudWatch Dashboard: $DASHBOARD_URL"
    fi
    
    # Get monitor console URL
    MONITOR_URL=$(aws cloudformation describe-stacks \
        --stack-name "$MONITOR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`MonitorConsoleURL`].OutputValue' \
        --output text 2>/dev/null || echo "Not found")
    
    if [ "$MONITOR_URL" != "Not found" ] && [ "$MONITOR_URL" != "None" ]; then
        print_info "Network Flow Monitor Console: $MONITOR_URL"
    fi
}

# ==============================================================================
# DEPLOYMENT FUNCTIONS
# ==============================================================================

deploy_stack() {
    print_section "Deploying Network Flow Monitor Stack"
    
    print_info "Monitor Stack Name: $MONITOR_STACK_NAME"
    print_info "Base Stack Name: $BASE_STACK_NAME"
    print_info "Region: $AWS_REGION"
    print_info "Monitor Name: $MONITOR_NAME"
    print_info "App VPC ID: $APP_VPC_ID"
    print_info "Reporting VPC ID: $REPORTING_VPC_ID"
    
    echo
    read -p "Do you want to proceed with deployment? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Deployment cancelled by user"
        exit 0
    fi
    
    # Check if stack exists
    if check_stack_exists; then
        CURRENT_STATUS=$(get_stack_status)
        print_warning "Stack '$MONITOR_STACK_NAME' already exists with status: $CURRENT_STATUS"
        
        case $CURRENT_STATUS in
            *_IN_PROGRESS)
                print_error "Stack is currently in progress. Please wait for it to complete."
                exit 1
                ;;
            *_FAILED|ROLLBACK_COMPLETE)
                print_info "Stack is in a failed state. You may need to delete it first."
                echo "Run: aws cloudformation delete-stack --stack-name $MONITOR_STACK_NAME --region $AWS_REGION"
                exit 1
                ;;
            *)
                echo
                read -p "Do you want to update the existing stack? (y/N): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    update_stack
                    return
                else
                    print_info "Deployment cancelled"
                    exit 0
                fi
                ;;
        esac
    fi
    
    # Create new stack
    print_info "Creating new CloudFormation stack..."
    
    aws cloudformation create-stack \
        --stack-name "$MONITOR_STACK_NAME" \
        --template-body file://"$TEMPLATE_PATH" \
        --parameters \
            ParameterKey=AppVPCId,ParameterValue="$APP_VPC_ID" \
            ParameterKey=ReportingVPCId,ParameterValue="$REPORTING_VPC_ID" \
            ParameterKey=MonitorName,ParameterValue="$MONITOR_NAME" \
        --region "$AWS_REGION" \
        --tags \
            Key=Project,Value=NetOps-Agentic-AI \
            Key=Workshop,Value=AgentCore-Performance \
            Key=Environment,Value=Demo \
            Key=Component,Value=NetworkFlowMonitor \
            Key=BaseStack,Value="$BASE_STACK_NAME" \
            Key=DeployedBy,Value="$(whoami)" \
            Key=DeployedAt,Value="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    
    wait_for_stack_complete "create"
}

update_stack() {
    print_info "Updating existing CloudFormation stack..."
    
    aws cloudformation update-stack \
        --stack-name "$MONITOR_STACK_NAME" \
        --template-body file://"$TEMPLATE_PATH" \
        --parameters \
            ParameterKey=AppVPCId,ParameterValue="$APP_VPC_ID" \
            ParameterKey=ReportingVPCId,ParameterValue="$REPORTING_VPC_ID" \
            ParameterKey=MonitorName,ParameterValue="$MONITOR_NAME" \
        --region "$AWS_REGION" \
        --tags \
            Key=Project,Value=NetOps-Agentic-AI \
            Key=Workshop,Value=AgentCore-Performance \
            Key=Environment,Value=Demo \
            Key=Component,Value=NetworkFlowMonitor \
            Key=BaseStack,Value="$BASE_STACK_NAME" \
            Key=UpdatedBy,Value="$(whoami)" \
            Key=UpdatedAt,Value="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    2>/dev/null || {
        # Check if no updates were required
        if aws cloudformation describe-stack-events \
            --stack-name "$MONITOR_STACK_NAME" \
            --region "$AWS_REGION" \
            --query 'StackEvents[0].ResourceStatusReason' \
            --output text 2>/dev/null | grep -q "No updates"; then
            print_info "No updates are required for the stack"
        else
            print_error "Failed to update stack"
            exit 1
        fi
    }
    
    # Only wait if update was actually initiated
    CURRENT_STATUS=$(get_stack_status)
    if [[ $CURRENT_STATUS == *"_IN_PROGRESS"* ]]; then
        wait_for_stack_complete "update"
    fi
}

# ==============================================================================
# CLEANUP FUNCTIONS
# ==============================================================================

delete_stack() {
    print_section "Deleting Network Flow Monitor Stack"
    
    if ! check_stack_exists; then
        print_warning "Stack '$MONITOR_STACK_NAME' does not exist"
        exit 0
    fi
    
    CURRENT_STATUS=$(get_stack_status)
    print_warning "Current stack status: $CURRENT_STATUS"
    
    echo
    print_warning "This will DELETE the Network Flow Monitor!"
    print_warning "This action cannot be undone."
    echo
    read -p "Are you sure you want to delete the stack? Type 'DELETE' to confirm: " -r
    echo
    
    if [ "$REPLY" != "DELETE" ]; then
        print_info "Stack deletion cancelled"
        exit 0
    fi
    
    print_info "Deleting CloudFormation stack..."
    aws cloudformation delete-stack \
        --stack-name "$MONITOR_STACK_NAME" \
        --region "$AWS_REGION"
    
    wait_for_stack_complete "delete"
    print_success "Stack deleted successfully"
}

# ==============================================================================
# INFORMATION FUNCTIONS
# ==============================================================================

show_stack_info() {
    print_section "Stack Information"
    
    if ! check_stack_exists; then
        print_warning "Stack '$MONITOR_STACK_NAME' does not exist"
        return 1
    fi
    
    # Show stack details
    aws cloudformation describe-stacks \
        --stack-name "$MONITOR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].{Name:StackName,Status:StackStatus,Created:CreationTime,Updated:LastUpdatedTime}' \
        --output table
    
    show_stack_outputs
}

show_usage() {
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo
    echo "Commands:"
    echo "  deploy    Deploy or update the Network Flow Monitor stack (default)"
    echo "  delete    Delete the Network Flow Monitor stack"
    echo "  info      Show stack information and outputs"
    echo "  status    Show current stack status"
    echo "  events    Show recent stack events"
    echo "  help      Show this help message"
    echo
    echo "Options:"
    echo "  -s, --stack-name STACK_NAME        Set monitor stack name (default: acme-network-flow-monitor)"
    echo "  -b, --base-stack BASE_STACK        Set base stack name (default: acme-image-gallery)"
    echo "  -r, --region REGION                Set AWS region (default: us-east-1)"
    echo "  -m, --monitor-name MONITOR_NAME    Set monitor name (default: acme-vpc-network-monitor)"
    echo "  -h, --help                         Show this help message"
    echo
    echo "Environment Variables:"
    echo "  MONITOR_STACK_NAME    Override default monitor stack name"
    echo "  BASE_STACK_NAME       Override default base stack name"
    echo "  AWS_REGION            Override default AWS region"
    echo "  MONITOR_NAME          Override default monitor name"
    echo
    echo "Examples:"
    echo "  $0                                    # Deploy with defaults"
    echo "  $0 -s my-monitor -b my-base-stack   # Deploy with custom stack names"
    echo "  $0 -r us-west-2                      # Deploy to specific region"
    echo "  $0 delete                            # Delete the monitor stack"
    echo "  $0 info                              # Show stack information"
    echo
    echo "Note: This script retrieves VPC IDs from the base stack (sample-application.yaml)"
    echo "      Ensure the base stack is deployed before running this script."
}

# ==============================================================================
# MAIN SCRIPT LOGIC
# ==============================================================================

main() {
    # Parse command line arguments
    COMMAND="deploy"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -s|--stack-name)
                MONITOR_STACK_NAME="$2"
                shift 2
                ;;
            -b|--base-stack)
                BASE_STACK_NAME="$2"
                shift 2
                ;;
            -r|--region)
                AWS_REGION="$2"
                shift 2
                ;;
            -m|--monitor-name)
                MONITOR_NAME="$2"
                shift 2
                ;;
            -h|--help|help)
                show_usage
                exit 0
                ;;
            deploy|delete|info|status|events)
                COMMAND="$1"
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Show banner
    print_banner
    
    # Execute command
    case $COMMAND in
        deploy)
            check_prerequisites
            get_vpc_ids_from_base_stack
            deploy_stack
            show_stack_outputs
            ;;
        delete)
            delete_stack
            ;;
        info)
            show_stack_info
            ;;
        status)
            if check_stack_exists; then
                STATUS=$(get_stack_status)
                print_info "Stack Status: $STATUS"
            else
                print_warning "Stack does not exist"
            fi
            ;;
        events)
            if check_stack_exists; then
                show_stack_events
            else
                print_warning "Stack does not exist"
            fi
            ;;
        *)
            print_error "Unknown command: $COMMAND"
            show_usage
            exit 1
            ;;
    esac
    
    print_success "Operation completed successfully!"
}

# ==============================================================================
# SCRIPT EXECUTION
# ==============================================================================

# Ensure we're in the correct directory
cd "$SCRIPT_DIR"

# Run main function with all arguments
main "$@"
