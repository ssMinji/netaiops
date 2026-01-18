#!/bin/bash

# deploy-postprovision.sh
# Script to run the a2a performance agent post-provisioning scripts in sequence
# Author: Auto-generated deployment script
# Date: $(date)

set -e  # Exit on any error
set -u  # Exit on undefined variables

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✓${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ✗${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠${NC} $1"
}

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Define the scripts/commands to run in sequence
TASKS=(
    "script:03-connect-service-to-alb.sh"
    "python:update_alb_status.py"
)

# Function to run a script with error handling
run_script() {
    local script_name="$1"
    local script_path="$SCRIPT_DIR/$script_name"
    
    log "Starting execution of: $script_name"
    
    # Check if script exists
    if [[ ! -f "$script_path" ]]; then
        log_error "Script not found: $script_path"
        return 1
    fi
    
    # Check if script is executable
    if [[ ! -x "$script_path" ]]; then
        log_warning "Making script executable: $script_name"
        chmod +x "$script_path"
    fi
    
    # Execute the script
    if "$script_path"; then
        log_success "Successfully completed: $script_name"
        return 0
    else
        log_error "Failed to execute: $script_name"
        return 1
    fi
}

# Function to run a Python script with error handling
run_python_script() {
    local script_name="$1"
    local script_path="$BASE_DIR/$script_name"
    
    log "Starting execution of Python script: $script_name"
    
    # Check if script exists
    if [[ ! -f "$script_path" ]]; then
        log_error "Python script not found: $script_path"
        return 1
    fi
    
    # Execute the Python script
    if python3 "$script_path"; then
        log_success "Successfully completed Python script: $script_name"
        return 0
    else
        log_error "Failed to execute Python script: $script_name"
        return 1
    fi
}

# Function to execute a task based on its type
execute_task() {
    local task="$1"
    local task_type="${task%%:*}"
    local task_name="${task##*:}"
    
    case "$task_type" in
        "script")
            run_script "$task_name"
            ;;
        "python")
            run_python_script "$task_name"
            ;;
        *)
            log_error "Unknown task type: $task_type"
            return 1
            ;;
    esac
}

# Main execution
main() {
    log "Starting A2A Performance Agent Post-provisioning Deployment"
    log "Script directory: $SCRIPT_DIR"
    log "Base directory: $BASE_DIR"
    echo
    
    local failed_tasks=()
    local success_count=0
    
    # Run each task in sequence
    for task in "${TASKS[@]}"; do
        echo -e "${BLUE}===========================================${NC}"
        if execute_task "$task"; then
            ((success_count++))
        else
            failed_tasks+=("$task")
            log_error "Stopping deployment due to failure in: $task"
            break
        fi
        echo
    done
    
    # Summary
    echo -e "${BLUE}===========================================${NC}"
    log "Deployment Summary:"
    log "Total tasks: ${#TASKS[@]}"
    log "Successfully executed: $success_count"
    log "Failed: ${#failed_tasks[@]}"
    
    if [[ ${#failed_tasks[@]} -eq 0 ]]; then
        log_success "All post-provisioning tasks completed successfully!"
        return 0
    else
        log_error "The following tasks failed:"
        for failed in "${failed_tasks[@]}"; do
            echo -e "  ${RED}• $failed${NC}"
        done
        return 1
    fi
}

# Check for Python3 availability
check_prerequisites() {
    if ! command -v python3 &> /dev/null; then
        log_error "python3 is required but not installed or not in PATH"
        exit 1
    fi
    log "Prerequisites check passed"
}

# Trap to handle script interruption
trap 'log_error "Deployment interrupted by user"; exit 130' INT TERM

# Function to upload files to S3
upload_to_s3() {
    log "Starting S3 upload process..."
    
    # Get AWS Account ID
    log "Getting AWS Account ID..."
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
    if [ $? -ne 0 ] || [ -z "$AWS_ACCOUNT_ID" ]; then
        log_error "Failed to get AWS Account ID. Please ensure AWS CLI is configured."
        return 1
    fi
    log "AWS Account ID: $AWS_ACCOUNT_ID"
    
    # Define S3 bucket and key
    S3_BUCKET="baseline-deploy-${AWS_ACCOUNT_ID}"
    S3_KEY="module-3/alb_access_guide.html"
    S3_URL="s3://${S3_BUCKET}/${S3_KEY}"
    
    log "S3 destination: $S3_URL"
    
    # Check if the file exists
    ALB_GUIDE_FILE="$BASE_DIR/alb_access_guide.html"
    if [[ ! -f "$ALB_GUIDE_FILE" ]]; then
        log_error "ALB access guide file not found: $ALB_GUIDE_FILE"
        return 1
    fi
    
    # Upload to S3
    log "Uploading ALB access guide to S3..."
    if aws s3 cp "$ALB_GUIDE_FILE" "$S3_URL"; then
        log_success "ALB access guide uploaded to S3 successfully"
        log_success "S3 URL: https://s3.amazonaws.com/${S3_BUCKET}/${S3_KEY}"
        log_success "Public URL (if bucket allows): https://${S3_BUCKET}.s3.amazonaws.com/${S3_KEY}"
        return 0
    else
        log_error "Failed to upload ALB access guide to S3"
        return 1
    fi
}

# Run prerequisite check and main function, then handle S3 upload
check_prerequisites

# Run main deployment tasks
if main "$@"; then
    echo
    log "=== POST-DEPLOYMENT S3 UPLOAD ==="
    
    # Upload files to S3
    if upload_to_s3; then
        log_success "All post-deployment tasks completed successfully!"
    else
        log_error "S3 upload failed, but main deployment completed successfully"
        exit 1
    fi
else
    log_error "Main deployment failed"
    exit 1
fi
