#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

AWS_REGION=us-east-1
CLUSTER_NAME="a2a-agents-cluster"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

log_info "Force creating ECS service for a2a-connectivity-agent"

# Get required resources
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
log_info "VPC ID: $VPC_ID"

# Get subnets in different AZs
SUBNET_INFO=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[?MapPublicIpOnLaunch==\`true\`].[SubnetId,AvailabilityZone]" --output text)
SUBNET_1=$(echo "$SUBNET_INFO" | head -n1 | cut -f1)
SUBNET_2=$(echo "$SUBNET_INFO" | tail -n1 | cut -f1)
log_info "Subnets: $SUBNET_1, $SUBNET_2"

# Get security group
ECS_SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=a2a-connectivity-ecs-sg" --query "SecurityGroups[0].GroupId" --output text)
log_info "Security Group: $ECS_SG_ID"

# Get target group
TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups --names a2a-connectivity-tg --query "TargetGroups[0].TargetGroupArn" --output text)
log_info "Target Group: $TARGET_GROUP_ARN"

# Get latest task definition
TASK_DEF_ARN=$(aws ecs describe-task-definition --task-definition a2a-connectivity-agent --query "taskDefinition.taskDefinitionArn" --output text)
log_info "Task Definition: $TASK_DEF_ARN"

# Delete any existing service (force)
log_info "Deleting any existing service..."
aws ecs delete-service --cluster $CLUSTER_NAME --service a2a-connectivity-agent-service --region $AWS_REGION --force 2>/dev/null || true
sleep 10

# Wait for service to be fully deleted
log_info "Waiting for service deletion to complete..."
for i in {1..30}; do
    STATUS=$(aws ecs describe-services --cluster $CLUSTER_NAME --services a2a-connectivity-agent-service --region $AWS_REGION --query "services[0].status" --output text 2>/dev/null || echo "DELETED")
    if [ "$STATUS" = "DELETED" ] || [ "$STATUS" = "None" ] || [ "$STATUS" = "" ]; then
        log_success "Service deleted"
        break
    fi
    log_info "Waiting... (attempt $i/30)"
    sleep 5
done

# Create service
log_info "Creating new ECS service..."

aws ecs create-service \
  --cluster $CLUSTER_NAME \
  --service-name a2a-connectivity-agent-service \
  --task-definition $TASK_DEF_ARN \
  --desired-count 1 \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1,$SUBNET_2],securityGroups=[$ECS_SG_ID],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=$TARGET_GROUP_ARN,containerName=connectivity-agent,containerPort=10003" \
  --health-check-grace-period-seconds 300 \
  --enable-execute-command \
  --region $AWS_REGION

if [ $? -eq 0 ]; then
    log_success "Service created successfully!"
    log_info "Waiting for service to stabilize..."
    
    # Wait for service to be running
    for i in {1..60}; do
        RUNNING=$(aws ecs describe-services --cluster $CLUSTER_NAME --services a2a-connectivity-agent-service --region $AWS_REGION --query "services[0].runningCount" --output text)
        DESIRED=$(aws ecs describe-services --cluster $CLUSTER_NAME --services a2a-connectivity-agent-service --region $AWS_REGION --query "services[0].desiredCount" --output text)
        log_info "Running: $RUNNING/$DESIRED (attempt $i/60)"
        
        if [ "$RUNNING" = "$DESIRED" ] && [ "$RUNNING" != "0" ]; then
            log_success "Service is running!"
            break
        fi
        sleep 10
    done
else
    log_error "Failed to create service"
    exit 1
fi

log_success "Service creation complete!"
