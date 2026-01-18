#!/bin/bash

# Get the values that would be used in the script
AWS_REGION=us-east-1
CLUSTER_NAME="a2a-agents-cluster"
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)

echo "VPC_ID: $VPC_ID"

# Get subnets
SUBNET_INFO=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[?MapPublicIpOnLaunch==\`true\`].[SubnetId,AvailabilityZone]" --output text)
SUBNET_1=$(echo "$SUBNET_INFO" | head -n1 | cut -f1)
SUBNET_2=$(echo "$SUBNET_INFO" | tail -n1 | cut -f1)

echo "SUBNET_1: $SUBNET_1"
echo "SUBNET_2: $SUBNET_2"

ALB_SUBNETS_COMMA="$SUBNET_1,$SUBNET_2"
echo "ALB_SUBNETS_COMMA: $ALB_SUBNETS_COMMA"

# Get security group
ECS_SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=a2a-performance-ecs-sg" --query "SecurityGroups[0].GroupId" --output text)
echo "ECS_SG_ID: $ECS_SG_ID"

# Get target group
TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups --names a2a-performance-tg --query "TargetGroups[0].TargetGroupArn" --output text 2>/dev/null)
echo "TARGET_GROUP_ARN: $TARGET_GROUP_ARN"

# Get task definition
TASK_DEFINITION_ARN=$(aws ecs describe-task-definition --task-definition a2a-performance-agent --query "taskDefinition.taskDefinitionArn" --output text)
echo "TASK_DEFINITION_ARN: $TASK_DEFINITION_ARN"

echo ""
echo "Testing service creation with proper network configuration..."
echo ""

# Test the actual command that should work
aws ecs create-service \
  --cluster $CLUSTER_NAME \
  --service-name a2a-performance-agent-service \
  --task-definition $TASK_DEFINITION_ARN \
  --desired-count 1 \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "awsvpcConfiguration={subnets=[$ALB_SUBNETS_COMMA],securityGroups=[$ECS_SG_ID],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=$TARGET_GROUP_ARN,containerName=performance-agent,containerPort=10005 \
  --health-check-grace-period-seconds 300 \
  --enable-execute-command \
  --region $AWS_REGION
