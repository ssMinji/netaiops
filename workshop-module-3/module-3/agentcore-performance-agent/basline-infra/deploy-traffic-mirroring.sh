#!/bin/bash

# ==============================================================================
# Traffic Mirroring - CloudFormation Deployment Script
# ==============================================================================
# This script deploys the traffic-mirroring.yaml CloudFormation template
# It references the existing sample-application stack for VPC and subnet info
# Part of the NetOps Agentic AI Workshop - AgentCore Performance Agent
# ==============================================================================

set -e  # Exit on any error

# ==============================================================================
# CONFIGURATION VARIABLES
# ==============================================================================

# Default configuration - modify these as needed
TRAFFIC_MIRROR_STACK_NAME="${TRAFFIC_MIRROR_STACK_NAME:-acme-traffic-mirroring}"
MAIN_STACK_NAME="${MAIN_STACK_NAME:-sample-app}"
AWS_REGION="${AWS_REGION:-us-east-1}"
TEMPLATE_FILE="traffic-mirroring.yaml"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_PATH="${SCRIPT_DIR}/${TEMPLATE_FILE}"

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
    echo "        Traffic Mirroring Deployment Script"
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
# MAIN STACK VERIFICATION
# ==============================================================================

verify_main_stack() {
    print_section "Verifying Main Stack"
    
    print_info "Main Stack Name: $MAIN_STACK_NAME"
    
    # Check if main stack exists
    if ! aws cloudformation describe-stacks --stack-name "$MAIN_STACK_NAME" --region "$AWS_REGION" &> /dev/null; then
        print_error "Main stack '$MAIN_STACK_NAME' does not exist"
        print_info "Please deploy the sample-application.yaml stack first using deploy.sh"
        print_info "Or specify the correct main stack name with -m option"
        exit 1
    fi
    
    # Get stack status
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$MAIN_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text)
    
    print_info "Main Stack Status: $STACK_STATUS"
    
    if [[ ! $STACK_STATUS =~ ^(CREATE_COMPLETE|UPDATE_COMPLETE)$ ]]; then
        print_error "Main stack is not in a complete state: $STACK_STATUS"
        print_info "Please ensure the main stack deployment is complete"
        exit 1
    fi
    
    print_success "Main stack is in a complete state"
    
    # Verify required exports exist
    print_info "Verifying required stack exports..."
    
    REQUIRED_EXPORTS=(
        "${MAIN_STACK_NAME}-App-VPC-ID"
        "${MAIN_STACK_NAME}-App-Private-Subnet2-ID"
    )
    
    for export_name in "${REQUIRED_EXPORTS[@]}"; do
        if aws cloudformation list-exports \
            --region "$AWS_REGION" \
            --query "Exports[?Name=='${export_name}'].Value" \
            --output text 2>/dev/null | grep -q .; then
            print_success "Export found: $export_name"
        else
            print_error "Required export not found: $export_name"
            print_info "The main stack must export this value for traffic mirroring to work"
            exit 1
        fi
    done
}

# ==============================================================================
# STACK MANAGEMENT FUNCTIONS
# ==============================================================================

check_stack_exists() {
    aws cloudformation describe-stacks --stack-name "$TRAFFIC_MIRROR_STACK_NAME" --region "$AWS_REGION" &> /dev/null
}

get_stack_status() {
    aws cloudformation describe-stacks \
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_EXISTS"
}

wait_for_stack_complete() {
    local operation=$1
    print_info "Waiting for stack $operation to complete..."
    print_warning "This may take 5-10 minutes as EC2 instances are being created..."
    
    aws cloudformation wait "stack-${operation}-complete" \
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
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
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'StackEvents[0:10].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
        --output table || true
}

show_stack_outputs() {
    print_section "Stack Outputs"
    
    aws cloudformation describe-stacks \
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}' \
        --output table
    
    echo
    print_info "Key Resources Created:"
    
    # Get S3 bucket name
    S3_BUCKET=$(aws cloudformation describe-stacks \
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`TrafficMirroringS3BucketName`].OutputValue' \
        --output text 2>/dev/null || echo "Not found")
    
    if [ "$S3_BUCKET" != "Not found" ] && [ "$S3_BUCKET" != "None" ]; then
        print_success "S3 Bucket: $S3_BUCKET"
    fi
    
    # Get target instance ID
    INSTANCE_ID=$(aws cloudformation describe-stacks \
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`TrafficMirroringTargetInstanceId`].OutputValue' \
        --output text 2>/dev/null || echo "Not found")
    
    if [ "$INSTANCE_ID" != "Not found" ] && [ "$INSTANCE_ID" != "None" ]; then
        print_success "Target Instance ID: $INSTANCE_ID"
    fi
    
    # Get dashboard URL
    DASHBOARD_URL=$(aws cloudformation describe-stacks \
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`TrafficMirroringDashboardURL`].OutputValue' \
        --output text 2>/dev/null || echo "Not found")
    
    if [ "$DASHBOARD_URL" != "Not found" ] && [ "$DASHBOARD_URL" != "None" ]; then
        print_info "CloudWatch Dashboard: $DASHBOARD_URL"
    fi
    
    echo
    print_warning "Next Steps:"
    echo "1. Configure traffic mirroring sessions to capture traffic from source ENIs"
    echo "2. Use the management script on the target instance: /opt/traffic-mirroring/manage_sessions.sh"
    echo "3. Monitor captured packets in S3 bucket: $S3_BUCKET"
    echo "4. View analysis results in CloudWatch Dashboard"
}

# ==============================================================================
# DEPLOYMENT FUNCTIONS
# ==============================================================================

deploy_stack() {
    print_section "Deploying Traffic Mirroring Stack"
    
    print_info "Traffic Mirror Stack Name: $TRAFFIC_MIRROR_STACK_NAME"
    print_info "Main Stack Name: $MAIN_STACK_NAME"
    print_info "Region: $AWS_REGION"
    
    echo
    print_warning "This deployment will create:"
    echo "  - S3 bucket for packet capture storage"
    echo "  - EC2 instance for traffic mirroring target (t3.medium)"
    echo "  - Lambda function for packet analysis"
    echo "  - SNS topic for alerts"
    echo "  - CloudWatch dashboard for monitoring"
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
        print_warning "Stack '$TRAFFIC_MIRROR_STACK_NAME' already exists with status: $CURRENT_STATUS"
        
        case $CURRENT_STATUS in
            *_IN_PROGRESS)
                print_error "Stack is currently in progress. Please wait for it to complete."
                exit 1
                ;;
            *_FAILED|ROLLBACK_COMPLETE)
                print_info "Stack is in a failed state. You may need to delete it first."
                echo "Run: aws cloudformation delete-stack --stack-name $TRAFFIC_MIRROR_STACK_NAME --region $AWS_REGION"
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
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
        --template-body file://"$TEMPLATE_PATH" \
        --parameters \
            ParameterKey=MainStackName,ParameterValue="$MAIN_STACK_NAME" \
        --capabilities CAPABILITY_IAM \
        --region "$AWS_REGION" \
        --tags \
            Key=Project,Value=NetOps-Agentic-AI \
            Key=Workshop,Value=AgentCore-Performance \
            Key=Environment,Value=Demo \
            Key=Component,Value=TrafficMirroring \
            Key=MainStack,Value="$MAIN_STACK_NAME" \
            Key=DeployedBy,Value="$(whoami)" \
            Key=DeployedAt,Value="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    
    wait_for_stack_complete "create"
}

update_stack() {
    print_info "Updating existing CloudFormation stack..."
    
    aws cloudformation update-stack \
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
        --template-body file://"$TEMPLATE_PATH" \
        --parameters \
            ParameterKey=MainStackName,ParameterValue="$MAIN_STACK_NAME" \
        --capabilities CAPABILITY_IAM \
        --region "$AWS_REGION" \
        --tags \
            Key=Project,Value=NetOps-Agentic-AI \
            Key=Workshop,Value=AgentCore-Performance \
            Key=Environment,Value=Demo \
            Key=Component,Value=TrafficMirroring \
            Key=MainStack,Value="$MAIN_STACK_NAME" \
            Key=UpdatedBy,Value="$(whoami)" \
            Key=UpdatedAt,Value="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    2>/dev/null || {
        # Check if no updates were required
        if aws cloudformation describe-stack-events \
            --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
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
    print_section "Deleting Traffic Mirroring Stack"
    
    if ! check_stack_exists; then
        print_warning "Stack '$TRAFFIC_MIRROR_STACK_NAME' does not exist"
        exit 0
    fi
    
    CURRENT_STATUS=$(get_stack_status)
    print_warning "Current stack status: $CURRENT_STATUS"
    
    echo
    print_warning "This will DELETE all traffic mirroring resources including:"
    echo "  - S3 bucket and all captured packets"
    echo "  - EC2 instance for traffic mirroring"
    echo "  - Lambda function and logs"
    echo "  - SNS topic and CloudWatch dashboard"
    print_warning "This action cannot be undone."
    echo
    read -p "Are you sure you want to delete the stack? Type 'DELETE' to confirm: " -r
    echo
    
    if [ "$REPLY" != "DELETE" ]; then
        print_info "Stack deletion cancelled"
        exit 0
    fi
    
    # Get S3 bucket name before deletion
    S3_BUCKET=$(aws cloudformation describe-stacks \
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`TrafficMirroringS3BucketName`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$S3_BUCKET" ] && [ "$S3_BUCKET" != "None" ]; then
        echo
        print_warning "S3 bucket '$S3_BUCKET' contains captured packets"
        read -p "Do you want to empty the S3 bucket before deletion? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "Emptying S3 bucket..."
            aws s3 rm "s3://${S3_BUCKET}" --recursive --region "$AWS_REGION" || true
            print_success "S3 bucket emptied"
        fi
    fi
    
    print_info "Deleting CloudFormation stack..."
    aws cloudformation delete-stack \
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
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
        print_warning "Stack '$TRAFFIC_MIRROR_STACK_NAME' does not exist"
        return 1
    fi
    
    # Show stack details
    aws cloudformation describe-stacks \
        --stack-name "$TRAFFIC_MIRROR_STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].{Name:StackName,Status:StackStatus,Created:CreationTime,Updated:LastUpdatedTime}' \
        --output table
    
    show_stack_outputs
}

show_usage() {
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo
    echo "Commands:"
    echo "  deploy    Deploy or update the Traffic Mirroring stack (default)"
    echo "  delete    Delete the Traffic Mirroring stack"
    echo "  info      Show stack information and outputs"
    echo "  status    Show current stack status"
    echo "  events    Show recent stack events"
    echo "  help      Show this help message"
    echo
    echo "Options:"
    echo "  -s, --stack-name STACK_NAME    Set traffic mirror stack name (default: acme-traffic-mirroring)"
    echo "  -m, --main-stack MAIN_STACK    Set main stack name (default: sample-app)"
    echo "  -r, --region REGION            Set AWS region (default: us-east-1)"
    echo "  -h, --help                     Show this help message"
    echo
    echo "Environment Variables:"
    echo "  TRAFFIC_MIRROR_STACK_NAME    Override default traffic mirror stack name"
    echo "  MAIN_STACK_NAME              Override default main stack name"
    echo "  AWS_REGION                   Override default AWS region"
    echo
    echo "Examples:"
    echo "  $0                                    # Deploy with defaults"
    echo "  $0 -s my-traffic-mirror -m my-app   # Deploy with custom stack names"
    echo "  $0 -r us-west-2                      # Deploy to specific region"
    echo "  $0 delete                            # Delete the traffic mirroring stack"
    echo "  $0 info                              # Show stack information"
    echo
    echo "Note: This script requires the main application stack to be deployed first."
    echo "      The main stack must export VPC and subnet information."
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
                TRAFFIC_MIRROR_STACK_NAME="$2"
                shift 2
                ;;
            -m|--main-stack)
                MAIN_STACK_NAME="$2"
                shift 2
                ;;
            -r|--region)
                AWS_REGION="$2"
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
            verify_main_stack
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
