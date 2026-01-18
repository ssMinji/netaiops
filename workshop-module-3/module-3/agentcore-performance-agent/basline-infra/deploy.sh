#!/bin/bash

# ==============================================================================
# ACME Image Gallery - CloudFormation Deployment Script
# ==============================================================================
# This script deploys the sample-application.yaml CloudFormation template to AWS
# Part of the NetOps Agentic AI Workshop - AgentCore Performance Agent
# ==============================================================================

set -e  # Exit on any error

# ==============================================================================
# CONFIGURATION VARIABLES
# ==============================================================================

# Default configuration - modify these as needed
STACK_NAME="${STACK_NAME:-acme-image-gallery-perf}"
AWS_REGION="${AWS_REGION:-us-east-1}"
TEMPLATE_FILE="sample-application.yaml"

# S3 configuration for template storage
S3_BUCKET_PREFIX="${S3_BUCKET_PREFIX:-cf-templates-netops-workshop}"
S3_TEMPLATE_KEY="${S3_TEMPLATE_KEY:-agentcore-performance-agent/sample-application.yaml}"

# Database parameters
DB_USERNAME="${DB_USERNAME:-admin}"
DB_PASSWORD="${DB_PASSWORD:-SapConcurWorkshop25}"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_PATH="${SCRIPT_DIR}/${TEMPLATE_FILE}"

# S3 variables (will be set during execution)
S3_BUCKET=""
S3_TEMPLATE_URL=""

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
    echo "           ACME Image Gallery Deployment Script"
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
# S3 TEMPLATE MANAGEMENT
# ==============================================================================

create_or_get_s3_bucket() {
    print_section "Setting up S3 Bucket for Template Storage"
    
    # Get account ID for unique bucket naming
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    S3_BUCKET="${S3_BUCKET_PREFIX}-${ACCOUNT_ID}-${AWS_REGION}"
    
    print_info "S3 Bucket: $S3_BUCKET"
    
    # Check if bucket exists
    if aws s3api head-bucket --bucket "$S3_BUCKET" --region "$AWS_REGION" 2>/dev/null; then
        print_success "S3 bucket already exists"
    else
        print_info "Creating S3 bucket for template storage..."
        
        # Create bucket with appropriate location constraint
        if [ "$AWS_REGION" = "us-east-1" ]; then
            # us-east-1 doesn't need LocationConstraint
            aws s3api create-bucket \
                --bucket "$S3_BUCKET" \
                --region "$AWS_REGION"
        else
            # Other regions need LocationConstraint
            aws s3api create-bucket \
                --bucket "$S3_BUCKET" \
                --region "$AWS_REGION" \
                --create-bucket-configuration LocationConstraint="$AWS_REGION"
        fi
        
        if [ $? -eq 0 ]; then
            print_success "S3 bucket created successfully"
        else
            print_error "Failed to create S3 bucket"
            exit 1
        fi
        
        # Enable versioning for better template management
        print_info "Enabling versioning on S3 bucket..."
        aws s3api put-bucket-versioning \
            --bucket "$S3_BUCKET" \
            --versioning-configuration Status=Enabled \
            --region "$AWS_REGION"
        
        # Add bucket policy for secure access
        print_info "Applying bucket policy for secure access..."
        BUCKET_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DenyInsecureConnections",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:*",
            "Resource": [
                "arn:aws:s3:::${S3_BUCKET}",
                "arn:aws:s3:::${S3_BUCKET}/*"
            ],
            "Condition": {
                "Bool": {
                    "aws:SecureTransport": "false"
                }
            }
        }
    ]
}
EOF
)
        echo "$BUCKET_POLICY" | aws s3api put-bucket-policy \
            --bucket "$S3_BUCKET" \
            --policy file:///dev/stdin \
            --region "$AWS_REGION"
    fi
    
    # Set the S3 template URL
    S3_TEMPLATE_URL="https://s3.amazonaws.com/${S3_BUCKET}/${S3_TEMPLATE_KEY}"
    if [ "$AWS_REGION" != "us-east-1" ]; then
        S3_TEMPLATE_URL="https://s3-${AWS_REGION}.amazonaws.com/${S3_BUCKET}/${S3_TEMPLATE_KEY}"
    fi
}

upload_template_to_s3() {
    print_section "Uploading Template to S3"
    
    print_info "Uploading CloudFormation template to S3..."
    print_info "Source: $TEMPLATE_PATH"
    print_info "Destination: s3://${S3_BUCKET}/${S3_TEMPLATE_KEY}"
    
    # Upload template with versioning and metadata
    aws s3 cp "$TEMPLATE_PATH" "s3://${S3_BUCKET}/${S3_TEMPLATE_KEY}" \
        --region "$AWS_REGION" \
        --metadata "uploaded-by=$(whoami),uploaded-at=$(date -u +%Y-%m-%dT%H:%M:%SZ),stack-name=${STACK_NAME}"
    
    if [ $? -eq 0 ]; then
        print_success "Template uploaded successfully"
        print_info "Template URL: $S3_TEMPLATE_URL"
        
        # Get and display the version ID
        VERSION_ID=$(aws s3api list-object-versions \
            --bucket "$S3_BUCKET" \
            --prefix "$S3_TEMPLATE_KEY" \
            --region "$AWS_REGION" \
            --query 'Versions[0].VersionId' \
            --output text)
        
        if [ "$VERSION_ID" != "None" ] && [ "$VERSION_ID" != "null" ]; then
            print_info "Template Version ID: $VERSION_ID"
        fi
    else
        print_error "Failed to upload template to S3"
        exit 1
    fi
}

validate_template_from_s3() {
    print_info "Validating CloudFormation template from S3..."
    if aws cloudformation validate-template --template-url "$S3_TEMPLATE_URL" --region "$AWS_REGION" &> /dev/null; then
        print_success "CloudFormation template from S3 is valid"
    else
        print_error "CloudFormation template validation failed from S3"
        aws cloudformation validate-template --template-url "$S3_TEMPLATE_URL" --region "$AWS_REGION"
        exit 1
    fi
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
    
    # Check if jq is installed (helpful for JSON parsing)
    if ! command -v jq &> /dev/null; then
        print_warning "jq is not installed. Some output formatting may be limited."
        print_info "Install with: sudo apt-get install jq (Ubuntu/Debian) or brew install jq (macOS)"
    else
        print_success "jq is available for JSON parsing"
    fi
    
    # Check template size first
    TEMPLATE_SIZE=$(wc -c < "$TEMPLATE_PATH")
    MAX_DIRECT_SIZE=51200  # AWS CloudFormation limit for direct template body
    
    print_info "Template size: $TEMPLATE_SIZE bytes"
    
    if [ $TEMPLATE_SIZE -gt $MAX_DIRECT_SIZE ]; then
        print_warning "Template exceeds direct validation size limit (${MAX_DIRECT_SIZE} bytes)"
        print_info "Will upload to S3 first, then validate from S3 URL"
        
        # Setup S3 bucket and upload template first for large templates
        create_or_get_s3_bucket
        upload_template_to_s3
        validate_template_from_s3
    else
        # Validate local template first for smaller templates
        print_info "Validating CloudFormation template locally..."
        if aws cloudformation validate-template --template-body file://"$TEMPLATE_PATH" --region "$AWS_REGION" &> /dev/null; then
            print_success "CloudFormation template is valid"
            
            # Setup S3 bucket and upload template
            create_or_get_s3_bucket
            upload_template_to_s3
            validate_template_from_s3
        else
            print_error "CloudFormation template validation failed"
            print_info "Attempting to get detailed validation error..."
            aws cloudformation validate-template --template-body file://"$TEMPLATE_PATH" --region "$AWS_REGION"
            exit 1
        fi
    fi
}

# ==============================================================================
# STACK MANAGEMENT FUNCTIONS
# ==============================================================================

check_stack_exists() {
    aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" &> /dev/null
}

get_stack_status() {
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_EXISTS"
}

wait_for_stack_complete() {
    local operation=$1
    print_info "Waiting for stack $operation to complete..."
    
    aws cloudformation wait "stack-${operation}-complete" \
        --stack-name "$STACK_NAME" \
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
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'StackEvents[0:10].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
        --output table || true
}

show_stack_outputs() {
    print_section "Stack Outputs"
    
    if command -v jq &> /dev/null; then
        # Use jq for better formatting if available
        aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$AWS_REGION" \
            --query 'Stacks[0].Outputs' \
            --output json | jq -r '.[] | "\(.OutputKey): \(.OutputValue)"' || \
        aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$AWS_REGION" \
            --query 'Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}' \
            --output table
    else
        # Fallback to table format
        aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$AWS_REGION" \
            --query 'Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}' \
            --output table
    fi
    
    # Get and highlight the ALB DNS name
    ALB_DNS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
        --output text 2>/dev/null || echo "Not found")
    
    if [ "$ALB_DNS" != "Not found" ] && [ "$ALB_DNS" != "None" ]; then
        echo
        print_success "Application URL: http://${ALB_DNS}"
        print_info "You can access the ACME Image Gallery at the URL above"
    fi
}

# ==============================================================================
# DEPLOYMENT FUNCTIONS
# ==============================================================================

deploy_stack() {
    print_section "Deploying CloudFormation Stack"
    
    print_info "Stack Name: $STACK_NAME"
    print_info "Region: $AWS_REGION"
    print_info "Template: $S3_TEMPLATE_URL"
    print_info "S3 Bucket: $S3_BUCKET"
    print_info "DB Username: $DB_USERNAME"
    print_info "DB Password: [HIDDEN]"
    
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
        print_warning "Stack '$STACK_NAME' already exists with status: $CURRENT_STATUS"
        
        case $CURRENT_STATUS in
            *_IN_PROGRESS)
                print_error "Stack is currently in progress. Please wait for it to complete."
                exit 1
                ;;
            *_FAILED|ROLLBACK_COMPLETE)
                print_info "Stack is in a failed state. You may need to delete it first."
                echo "Run: aws cloudformation delete-stack --stack-name $STACK_NAME --region $AWS_REGION"
                exit 1
                ;;
            *)
                print_info "Proceeding with stack update..."
                update_stack
                return
                ;;
        esac
    fi
    
    # Create new stack
    print_info "Creating new CloudFormation stack from S3 template..."
    
    aws cloudformation create-stack \
        --stack-name "$STACK_NAME" \
        --template-url "$S3_TEMPLATE_URL" \
        --parameters \
            ParameterKey=DBUsername,ParameterValue="$DB_USERNAME" \
            ParameterKey=DBPassword,ParameterValue="$DB_PASSWORD" \
        --capabilities CAPABILITY_IAM \
        --region "$AWS_REGION" \
        --tags \
            Key=Project,Value=NetOps-Agentic-AI \
            Key=Workshop,Value=AgentCore-Performance \
            Key=Environment,Value=Demo \
            Key=DeployedBy,Value="$(whoami)" \
            Key=DeployedAt,Value="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            Key=TemplateS3Bucket,Value="$S3_BUCKET" \
            Key=TemplateS3Key,Value="$S3_TEMPLATE_KEY"
    
    wait_for_stack_complete "create"
}

update_stack() {
    print_info "Updating existing CloudFormation stack from S3 template..."
    
    aws cloudformation update-stack \
        --stack-name "$STACK_NAME" \
        --template-url "$S3_TEMPLATE_URL" \
        --parameters \
            ParameterKey=DBUsername,ParameterValue="$DB_USERNAME" \
            ParameterKey=DBPassword,ParameterValue="$DB_PASSWORD" \
        --capabilities CAPABILITY_IAM \
        --region "$AWS_REGION" \
        --tags \
            Key=Project,Value=NetOps-Agentic-AI \
            Key=Workshop,Value=AgentCore-Performance \
            Key=Environment,Value=Demo \
            Key=UpdatedBy,Value="$(whoami)" \
            Key=UpdatedAt,Value="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            Key=TemplateS3Bucket,Value="$S3_BUCKET" \
            Key=TemplateS3Key,Value="$S3_TEMPLATE_KEY" \
    2>/dev/null || {
        # Check if no updates were required
        if aws cloudformation describe-stack-events \
            --stack-name "$STACK_NAME" \
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
    print_section "Deleting CloudFormation Stack"
    
    if ! check_stack_exists; then
        print_warning "Stack '$STACK_NAME' does not exist"
        exit 0
    fi
    
    CURRENT_STATUS=$(get_stack_status)
    print_warning "Current stack status: $CURRENT_STATUS"
    
    echo
    print_warning "This will DELETE all resources created by the stack!"
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
        --stack-name "$STACK_NAME" \
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
        print_warning "Stack '$STACK_NAME' does not exist"
        return 1
    fi
    
    # Show stack details
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].{Name:StackName,Status:StackStatus,Created:CreationTime,Updated:LastUpdatedTime}' \
        --output table
    
    show_stack_outputs
}

show_usage() {
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo
    echo "Commands:"
    echo "  deploy    Deploy or update the CloudFormation stack (default)"
    echo "  delete    Delete the CloudFormation stack"
    echo "  info      Show stack information and outputs"
    echo "  status    Show current stack status"
    echo "  events    Show recent stack events"
    echo "  help      Show this help message"
    echo
    echo "Options:"
    echo "  -s, --stack-name STACK_NAME    Set stack name (default: acme-image-gallery)"
    echo "  -r, --region REGION            Set AWS region (default: us-east-1)"
    echo "  -u, --db-username USERNAME     Set database username (default: admin)"
    echo "  -p, --db-password PASSWORD     Set database password"
    echo "  -b, --s3-bucket-prefix PREFIX  Set S3 bucket prefix (default: cf-templates-netops-workshop)"
    echo "  -k, --s3-template-key KEY      Set S3 template key (default: agentcore-performance-agent/sample-application.yaml)"
    echo "  -h, --help                     Show this help message"
    echo
    echo "Environment Variables:"
    echo "  STACK_NAME           Override default stack name"
    echo "  AWS_REGION           Override default AWS region"
    echo "  DB_USERNAME          Override default database username"
    echo "  DB_PASSWORD          Override default database password"
    echo "  S3_BUCKET_PREFIX     Override default S3 bucket prefix"
    echo "  S3_TEMPLATE_KEY      Override default S3 template key"
    echo
    echo "S3 Template Storage:"
    echo "  The script automatically creates an S3 bucket with the pattern:"
    echo "  {S3_BUCKET_PREFIX}-{ACCOUNT_ID}-{REGION}"
    echo "  Templates are uploaded with versioning enabled for change tracking."
    echo
    echo "Examples:"
    echo "  $0                                 # Deploy with defaults"
    echo "  $0 -s my-stack -r us-west-2      # Deploy to specific stack and region"
    echo "  $0 -b my-templates                # Use custom S3 bucket prefix"
    echo "  $0 delete                         # Delete the stack"
    echo "  $0 info                           # Show stack information"
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
                STACK_NAME="$2"
                shift 2
                ;;
            -r|--region)
                AWS_REGION="$2"
                shift 2
                ;;
            -u|--db-username)
                DB_USERNAME="$2"
                shift 2
                ;;
            -p|--db-password)
                DB_PASSWORD="$2"
                shift 2
                ;;
            -b|--s3-bucket-prefix)
                S3_BUCKET_PREFIX="$2"
                shift 2
                ;;
            -k|--s3-template-key)
                S3_TEMPLATE_KEY="$2"
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
    
    # Validate password length
    if [ ${#DB_PASSWORD} -lt 8 ]; then
        print_error "Database password must be at least 8 characters long"
        exit 1
    fi
    
    # Execute command
    case $COMMAND in
        deploy)
            check_prerequisites
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
