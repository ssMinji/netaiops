#!/bin/bash

#############################################################################
# CloudFormation Stack Deployment Script
# 
# This script deploys Network Flow Monitor and Traffic Mirroring stacks
# to a single AWS account in us-east-1 region using existing credentials.
#
# Usage:
#   ./deploy-stackset.sh <command> [options]
#
# Commands:
#   deploy-all                Deploy both Network Flow Monitor and Traffic Mirroring stacks
#   deploy-network-monitor    Deploy only Network Flow Monitor stack
#   deploy-traffic-mirror     Deploy only Traffic Mirroring stack
#   update-network-monitor    Update Network Flow Monitor stack
#   update-traffic-mirror     Update Traffic Mirroring stack
#   delete-all                Delete both stacks
#   delete-network-monitor    Delete Network Flow Monitor stack
#   delete-traffic-mirror     Delete Traffic Mirroring stack
#   list-stacks               List all stacks
#   describe-stack            Describe a specific stack
#
#############################################################################

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
REGION="us-east-1"
NETWORK_FLOW_MONITOR_STACK_NAME="acme-network-flow-monitor"
TRAFFIC_MIRRORING_STACK_NAME="acme-traffic-mirroring"
MAIN_STACK_NAME="acme-image-gallery-perf"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

#############################################################################
# Helper Functions
#############################################################################

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

#############################################################################
# Validation Functions
#############################################################################

validate_prerequisites() {
    print_header "Validating Prerequisites"
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed"
        exit 1
    fi
    print_success "AWS CLI is installed"
    
    # Check AWS credentials
    if ! aws sts get-caller-identity --region "$REGION" &> /dev/null; then
        print_error "AWS credentials are not configured"
        exit 1
    fi
    
    local account_id=$(aws sts get-caller-identity --region "$REGION" --query 'Account' --output text)
    print_success "AWS credentials are configured (Account: $account_id)"
    
    # Check if templates exist
    if [[ ! -f "$SCRIPT_DIR/network-flow-monitor-vpc.yaml" ]]; then
        print_error "network-flow-monitor-vpc.yaml not found"
        exit 1
    fi
    print_success "network-flow-monitor-vpc.yaml found"
    
    if [[ ! -f "$SCRIPT_DIR/traffic-mirroring.yaml" ]]; then
        print_error "traffic-mirroring.yaml not found"
        exit 1
    fi
    print_success "traffic-mirroring.yaml found"
    
    echo ""
}

get_vpc_ids_from_base_stack() {
    local stack_name=$1
    
    print_info "Retrieving VPC IDs from base stack: $stack_name" >&2
    
    # Try to get VPC IDs from stack outputs first
    local app_vpc_id=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`AppVPCId`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    local reporting_vpc_id=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`ReportingVPCId`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    # If not found in outputs, try to get from resources
    if [[ -z "$app_vpc_id" ]]; then
        app_vpc_id=$(aws cloudformation describe-stack-resources \
            --stack-name "$stack_name" \
            --region "$REGION" \
            --query 'StackResources[?LogicalResourceId==`AppVPC`].PhysicalResourceId' \
            --output text 2>/dev/null || echo "")
    fi
    
    if [[ -z "$reporting_vpc_id" ]]; then
        reporting_vpc_id=$(aws cloudformation describe-stack-resources \
            --stack-name "$stack_name" \
            --region "$REGION" \
            --query 'StackResources[?LogicalResourceId==`ReportingVPC`].PhysicalResourceId' \
            --output text 2>/dev/null || echo "")
    fi
    
    if [[ -z "$app_vpc_id" ]] || [[ -z "$reporting_vpc_id" ]]; then
        print_error "Could not retrieve VPC IDs from base stack" >&2
        return 1
    fi
    
    print_success "App VPC ID: $app_vpc_id" >&2
    print_success "Reporting VPC ID: $reporting_vpc_id" >&2
    
    echo "$app_vpc_id|$reporting_vpc_id"
}

get_instance_ids_from_base_stack() {
    local stack_name=$1
    
    print_info "Retrieving Instance IDs from base stack: $stack_name" >&2
    
    # Get Bastion Instance ID
    local bastion_instance_id=$(aws cloudformation describe-stack-resources \
        --stack-name "$stack_name" \
        --region "$REGION" \
        --query 'StackResources[?LogicalResourceId==`BastionEC2Instance`].PhysicalResourceId' \
        --output text 2>/dev/null || echo "")
    
    # Get Reporting Instance ID
    local reporting_instance_id=$(aws cloudformation describe-stack-resources \
        --stack-name "$stack_name" \
        --region "$REGION" \
        --query 'StackResources[?LogicalResourceId==`ReportingEC2Instance`].PhysicalResourceId' \
        --output text 2>/dev/null || echo "")
    
    if [[ -z "$bastion_instance_id" ]] || [[ -z "$reporting_instance_id" ]]; then
        print_error "Could not retrieve Instance IDs from base stack" >&2
        return 1
    fi
    
    print_success "Bastion Instance ID: $bastion_instance_id" >&2
    print_success "Reporting Instance ID: $reporting_instance_id" >&2
    
    echo "$bastion_instance_id|$reporting_instance_id"
}

get_private_subnet_from_vpc() {
    local vpc_id=$1
    
    print_info "Retrieving private subnet from VPC: $vpc_id" >&2
    
    # Get the first private subnet (assuming it has "Private" in the name tag)
    local subnet_id=$(aws ec2 describe-subnets \
        --region "$REGION" \
        --filters "Name=vpc-id,Values=$vpc_id" "Name=tag:Name,Values=*Private*" \
        --query 'Subnets[0].SubnetId' \
        --output text 2>/dev/null || echo "")
    
    # If not found by name tag, try to get any subnet from the VPC
    if [[ -z "$subnet_id" ]] || [[ "$subnet_id" == "None" ]]; then
        subnet_id=$(aws ec2 describe-subnets \
            --region "$REGION" \
            --filters "Name=vpc-id,Values=$vpc_id" \
            --query 'Subnets[0].SubnetId' \
            --output text 2>/dev/null || echo "")
    fi
    
    if [[ -z "$subnet_id" ]] || [[ "$subnet_id" == "None" ]]; then
        print_error "Could not retrieve subnet from VPC: $vpc_id" >&2
        return 1
    fi
    
    print_success "Target Subnet ID: $subnet_id" >&2
    
    echo "$subnet_id"
}

#############################################################################
# Stack Operations
#############################################################################

deploy_network_flow_monitor() {
    print_header "Deploying Network Flow Monitor Stack"
    
    # Get VPC IDs from base stack
    local vpc_ids=$(get_vpc_ids_from_base_stack "$MAIN_STACK_NAME")
    
    if [[ $? -ne 0 ]]; then
        print_error "Failed to retrieve VPC IDs"
        return 1
    fi
    
    local app_vpc_id=$(echo "$vpc_ids" | cut -d'|' -f1)
    local reporting_vpc_id=$(echo "$vpc_ids" | cut -d'|' -f2)
    
    # Get Instance IDs from base stack
    local instance_ids=$(get_instance_ids_from_base_stack "$MAIN_STACK_NAME")
    
    if [[ $? -ne 0 ]]; then
        print_error "Failed to retrieve Instance IDs"
        return 1
    fi
    
    local bastion_instance_id=$(echo "$instance_ids" | cut -d'|' -f1)
    local reporting_instance_id=$(echo "$instance_ids" | cut -d'|' -f2)
    
    print_info "Stack Name: $NETWORK_FLOW_MONITOR_STACK_NAME"
    print_info "Region: $REGION"
    print_info "Template: network-flow-monitor-vpc.yaml"
    print_info "App VPC: $app_vpc_id"
    print_info "Reporting VPC: $reporting_vpc_id"
    print_info "Bastion Instance: $bastion_instance_id"
    print_info "Reporting Instance: $reporting_instance_id"
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name "$NETWORK_FLOW_MONITOR_STACK_NAME" --region "$REGION" &> /dev/null; then
        print_warning "Stack already exists. Updating stack..."
        
        # Update stack
        aws cloudformation update-stack \
            --stack-name "$NETWORK_FLOW_MONITOR_STACK_NAME" \
            --template-body "file://$SCRIPT_DIR/network-flow-monitor-vpc.yaml" \
            --parameters \
                ParameterKey=AppVPCId,ParameterValue="$app_vpc_id" \
                ParameterKey=ReportingVPCId,ParameterValue="$reporting_vpc_id" \
                ParameterKey=MonitorName,ParameterValue="acme-vpc-network-monitor" \
                ParameterKey=BastionInstanceId,ParameterValue="$bastion_instance_id" \
                ParameterKey=ReportingServerInstanceId,ParameterValue="$reporting_instance_id" \
            --capabilities CAPABILITY_IAM \
            --tags Key=ManagedBy,Value=CloudFormation Key=Purpose,Value=NetworkMonitoring \
            --region "$REGION"
        
        print_success "Stack update initiated: $NETWORK_FLOW_MONITOR_STACK_NAME"
        
        # Wait for stack update to complete
        print_info "Waiting for stack update to complete..."
        aws cloudformation wait stack-update-complete \
            --stack-name "$NETWORK_FLOW_MONITOR_STACK_NAME" \
            --region "$REGION"
        
        print_success "Network Flow Monitor stack updated successfully"
    else
        # Create stack
        aws cloudformation create-stack \
            --stack-name "$NETWORK_FLOW_MONITOR_STACK_NAME" \
            --template-body "file://$SCRIPT_DIR/network-flow-monitor-vpc.yaml" \
            --parameters \
                ParameterKey=AppVPCId,ParameterValue="$app_vpc_id" \
                ParameterKey=ReportingVPCId,ParameterValue="$reporting_vpc_id" \
                ParameterKey=MonitorName,ParameterValue="acme-vpc-network-monitor" \
                ParameterKey=BastionInstanceId,ParameterValue="$bastion_instance_id" \
                ParameterKey=ReportingServerInstanceId,ParameterValue="$reporting_instance_id" \
            --capabilities CAPABILITY_IAM \
            --tags Key=ManagedBy,Value=CloudFormation Key=Purpose,Value=NetworkMonitoring \
            --region "$REGION"
        
        print_success "Stack creation initiated: $NETWORK_FLOW_MONITOR_STACK_NAME"
        
        # Wait for stack creation to complete
        print_info "Waiting for stack creation to complete..."
        aws cloudformation wait stack-create-complete \
            --stack-name "$NETWORK_FLOW_MONITOR_STACK_NAME" \
            --region "$REGION"
        
        print_success "Network Flow Monitor stack deployed successfully"
    fi
    echo ""
}

deploy_traffic_mirroring() {
    print_header "Deploying Traffic Mirroring Stack"
    
    # Get VPC IDs from base stack
    local vpc_ids=$(get_vpc_ids_from_base_stack "$MAIN_STACK_NAME")
    
    if [[ $? -ne 0 ]]; then
        print_error "Failed to retrieve VPC IDs"
        return 1
    fi
    
    local app_vpc_id=$(echo "$vpc_ids" | cut -d'|' -f1)
    
    # Get Instance IDs from base stack
    local instance_ids=$(get_instance_ids_from_base_stack "$MAIN_STACK_NAME")
    
    if [[ $? -ne 0 ]]; then
        print_error "Failed to retrieve Instance IDs"
        return 1
    fi
    
    local bastion_instance_id=$(echo "$instance_ids" | cut -d'|' -f1)
    local reporting_instance_id=$(echo "$instance_ids" | cut -d'|' -f2)
    
    # Get a private subnet from the App VPC for the Traffic Mirroring Target
    local target_subnet_id=$(get_private_subnet_from_vpc "$app_vpc_id")
    
    if [[ $? -ne 0 ]]; then
        print_error "Failed to retrieve target subnet"
        return 1
    fi
    
    print_info "Stack Name: $TRAFFIC_MIRRORING_STACK_NAME"
    print_info "Region: $REGION"
    print_info "Template: traffic-mirroring.yaml"
    print_info "Main Stack: $MAIN_STACK_NAME"
    print_info "Bastion Instance: $bastion_instance_id"
    print_info "Reporting Instance: $reporting_instance_id"
    print_info "Target Subnet: $target_subnet_id"
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name "$TRAFFIC_MIRRORING_STACK_NAME" --region "$REGION" &> /dev/null; then
        print_warning "Stack already exists. Updating stack..."
        
        # Update stack
        aws cloudformation update-stack \
            --stack-name "$TRAFFIC_MIRRORING_STACK_NAME" \
            --template-body "file://$SCRIPT_DIR/traffic-mirroring.yaml" \
            --parameters \
                ParameterKey=MainStackName,ParameterValue="$MAIN_STACK_NAME" \
                ParameterKey=BastionInstanceId,ParameterValue="$bastion_instance_id" \
                ParameterKey=ReportingInstanceId,ParameterValue="$reporting_instance_id" \
                ParameterKey=TargetSubnetId,ParameterValue="$target_subnet_id" \
            --capabilities CAPABILITY_IAM \
            --tags Key=ManagedBy,Value=CloudFormation Key=Purpose,Value=TrafficAnalysis \
            --region "$REGION"
        
        print_success "Stack update initiated: $TRAFFIC_MIRRORING_STACK_NAME"
        
        # Wait for stack update to complete
        print_info "Waiting for stack update to complete..."
        aws cloudformation wait stack-update-complete \
            --stack-name "$TRAFFIC_MIRRORING_STACK_NAME" \
            --region "$REGION"
        
        print_success "Traffic Mirroring stack updated successfully"
    else
        # Create stack
        aws cloudformation create-stack \
            --stack-name "$TRAFFIC_MIRRORING_STACK_NAME" \
            --template-body "file://$SCRIPT_DIR/traffic-mirroring.yaml" \
            --parameters \
                ParameterKey=MainStackName,ParameterValue="$MAIN_STACK_NAME" \
                ParameterKey=BastionInstanceId,ParameterValue="$bastion_instance_id" \
                ParameterKey=ReportingInstanceId,ParameterValue="$reporting_instance_id" \
                ParameterKey=TargetSubnetId,ParameterValue="$target_subnet_id" \
            --capabilities CAPABILITY_IAM \
            --tags Key=ManagedBy,Value=CloudFormation Key=Purpose,Value=TrafficAnalysis \
            --region "$REGION"
        
        print_success "Stack creation initiated: $TRAFFIC_MIRRORING_STACK_NAME"
        
        # Wait for stack creation to complete
        print_info "Waiting for stack creation to complete..."
        aws cloudformation wait stack-create-complete \
            --stack-name "$TRAFFIC_MIRRORING_STACK_NAME" \
            --region "$REGION"
        
        print_success "Traffic Mirroring stack deployed successfully"
    fi
    echo ""
}

update_network_flow_monitor() {
    print_header "Updating Network Flow Monitor Stack"
    
    print_info "Stack Name: $NETWORK_FLOW_MONITOR_STACK_NAME"
    print_info "Template: network-flow-monitor-vpc.yaml"
    
    aws cloudformation update-stack \
        --stack-name "$NETWORK_FLOW_MONITOR_STACK_NAME" \
        --template-body "file://$SCRIPT_DIR/network-flow-monitor-vpc.yaml" \
        --capabilities CAPABILITY_IAM \
        --region "$REGION"
    
    print_success "Stack update initiated"
    
    # Wait for update to complete
    print_info "Waiting for stack update to complete..."
    aws cloudformation wait stack-update-complete \
        --stack-name "$NETWORK_FLOW_MONITOR_STACK_NAME" \
        --region "$REGION"
    
    print_success "Network Flow Monitor stack updated successfully"
    echo ""
}

update_traffic_mirroring() {
    print_header "Updating Traffic Mirroring Stack"
    
    print_info "Stack Name: $TRAFFIC_MIRRORING_STACK_NAME"
    print_info "Template: traffic-mirroring.yaml"
    
    aws cloudformation update-stack \
        --stack-name "$TRAFFIC_MIRRORING_STACK_NAME" \
        --template-body "file://$SCRIPT_DIR/traffic-mirroring.yaml" \
        --capabilities CAPABILITY_IAM \
        --region "$REGION"
    
    print_success "Stack update initiated"
    
    # Wait for update to complete
    print_info "Waiting for stack update to complete..."
    aws cloudformation wait stack-update-complete \
        --stack-name "$TRAFFIC_MIRRORING_STACK_NAME" \
        --region "$REGION"
    
    print_success "Traffic Mirroring stack updated successfully"
    echo ""
}

delete_stack() {
    local stack_name=$1
    
    print_header "Deleting Stack: $stack_name"
    
    print_warning "This will delete the stack and all its resources"
    
    read -p "Are you sure you want to proceed? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        print_info "Operation cancelled"
        return 0
    fi
    
    aws cloudformation delete-stack \
        --stack-name "$stack_name" \
        --region "$REGION"
    
    print_success "Stack deletion initiated: $stack_name"
    
    # Wait for deletion to complete
    print_info "Waiting for stack deletion to complete..."
    aws cloudformation wait stack-delete-complete \
        --stack-name "$stack_name" \
        --region "$REGION"
    
    print_success "Stack deleted successfully: $stack_name"
    echo ""
}

list_stacks() {
    print_header "Listing CloudFormation Stacks"
    
    aws cloudformation list-stacks \
        --region "$REGION" \
        --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
        --output table \
        --query 'StackSummaries[*].[StackName,StackStatus,CreationTime]'
    
    echo ""
}

describe_stack() {
    local stack_name=$1
    
    print_header "Describing Stack: $stack_name"
    
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$REGION" \
        --output table
    
    echo ""
}

#############################################################################
# Main Script Logic
#############################################################################

show_usage() {
    cat << EOF
CloudFormation Stack Deployment Script

Usage: $0 <command>

Commands:
  deploy-all                Deploy both Network Flow Monitor and Traffic Mirroring stacks
  deploy-network-monitor    Deploy only Network Flow Monitor stack
  deploy-traffic-mirror     Deploy only Traffic Mirroring stack
  update-network-monitor    Update Network Flow Monitor stack
  update-traffic-mirror     Update Traffic Mirroring stack
  delete-all                Delete both stacks
  delete-network-monitor    Delete Network Flow Monitor stack
  delete-traffic-mirror     Delete Traffic Mirroring stack
  list-stacks               List all stacks
  describe-network-monitor  Describe Network Flow Monitor stack
  describe-traffic-mirror   Describe Traffic Mirroring stack

Examples:
  # Deploy both stacks
  $0 deploy-all
  
  # Deploy only Network Flow Monitor
  $0 deploy-network-monitor
  
  # Update Traffic Mirroring stack
  $0 update-traffic-mirror
  
  # List all stacks
  $0 list-stacks
  
  # Delete both stacks
  $0 delete-all

Configuration:
  Region: $REGION
  Main Stack: $MAIN_STACK_NAME
  Network Flow Monitor Stack: $NETWORK_FLOW_MONITOR_STACK_NAME
  Traffic Mirroring Stack: $TRAFFIC_MIRRORING_STACK_NAME

EOF
}

# Main command processing
case "${1:-}" in
    deploy-all)
        validate_prerequisites
        
        print_info "Deploying stacks in order: 1) Network Flow Monitor, 2) Traffic Mirroring"
        echo ""
        
        # Deploy Network Flow Monitor first
        deploy_network_flow_monitor
        
        print_info "Network Flow Monitor deployment complete. Proceeding with Traffic Mirroring..."
        echo ""
        
        # Deploy Traffic Mirroring second
        deploy_traffic_mirroring
        
        print_success "All stacks deployed successfully"
        ;;
        
    deploy-network-monitor)
        validate_prerequisites
        deploy_network_flow_monitor
        ;;
        
    deploy-traffic-mirror)
        validate_prerequisites
        deploy_traffic_mirroring
        ;;
        
    update-network-monitor)
        validate_prerequisites
        update_network_flow_monitor
        ;;
        
    update-traffic-mirror)
        validate_prerequisites
        update_traffic_mirroring
        ;;
        
    delete-all)
        print_info "Deleting stacks in reverse order: 1) Traffic Mirroring, 2) Network Flow Monitor"
        echo ""
        
        # Delete Traffic Mirroring first
        delete_stack "$TRAFFIC_MIRRORING_STACK_NAME"
        
        # Delete Network Flow Monitor second
        delete_stack "$NETWORK_FLOW_MONITOR_STACK_NAME"
        
        print_success "All stacks deleted successfully"
        ;;
        
    delete-network-monitor)
        delete_stack "$NETWORK_FLOW_MONITOR_STACK_NAME"
        ;;
        
    delete-traffic-mirror)
        delete_stack "$TRAFFIC_MIRRORING_STACK_NAME"
        ;;
        
    list-stacks)
        list_stacks
        ;;
        
    describe-network-monitor)
        describe_stack "$NETWORK_FLOW_MONITOR_STACK_NAME"
        ;;
        
    describe-traffic-mirror)
        describe_stack "$TRAFFIC_MIRRORING_STACK_NAME"
        ;;
        
    *)
        show_usage
        exit 1
        ;;
esac

print_success "Operation completed successfully"
