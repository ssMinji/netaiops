#!/bin/bash

# =============================================================================
# CloudWatch Alarms + SNS Setup for Incident Automation Pipeline
# 인시던트 자동화 파이프라인용 CloudWatch 알람 + SNS 설정
# =============================================================================
# Creates:
#   1. SNS Topic for alarm notifications
#   2. CloudWatch Alarms for EKS Container Insights metrics
#   3. SNS subscription to the alarm-trigger Lambda
#
# Prerequisites:
#   - deploy-incident-lambdas.sh must be run first
#   - Container Insights must be enabled on the EKS cluster
#
# Usage: ./setup-alarms.sh
# =============================================================================

set -e

PROFILE="netaiops-deploy"
ALARM_REGION="us-west-2"     # Container Insights metrics are in the EKS region
LAMBDA_REGION="us-east-1"    # Lambda functions are in us-east-1
CLUSTER_NAME="netaiops-eks-cluster"
SNS_TOPIC_NAME="netaiops-incident-alarm-topic"

echo "==========================================="
echo " CloudWatch Alarms + SNS Setup"
echo "==========================================="

# -----------------------------------------------
# 1. Get Account ID
# -----------------------------------------------
ACCOUNT_ID=$(aws sts get-caller-identity --profile ${PROFILE} --query Account --output text)
echo "Account: $ACCOUNT_ID"
echo "Alarm Region: $ALARM_REGION | Lambda Region: $LAMBDA_REGION"

# -----------------------------------------------
# 2. Create SNS Topic (in alarm region)
# -----------------------------------------------
echo ""
echo "Creating SNS Topic: ${SNS_TOPIC_NAME}..."
SNS_TOPIC_ARN=$(aws sns create-topic \
    --name ${SNS_TOPIC_NAME} \
    --region ${ALARM_REGION} \
    --profile ${PROFILE} \
    --query "TopicArn" \
    --output text)
echo "SNS Topic ARN: $SNS_TOPIC_ARN"

# -----------------------------------------------
# 3. Set SNS Topic Policy (allow CloudWatch Alarms to publish)
# -----------------------------------------------
echo ""
echo "Setting SNS topic policy..."
aws sns set-topic-attributes \
    --topic-arn ${SNS_TOPIC_ARN} \
    --attribute-name Policy \
    --attribute-value '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowCloudWatchAlarms",
                "Effect": "Allow",
                "Principal": {"Service": "cloudwatch.amazonaws.com"},
                "Action": "SNS:Publish",
                "Resource": "'"${SNS_TOPIC_ARN}"'",
                "Condition": {
                    "ArnLike": {
                        "aws:SourceArn": "arn:aws:cloudwatch:'"${ALARM_REGION}"':'"${ACCOUNT_ID}"':alarm:netaiops-*"
                    }
                }
            }
        ]
    }' \
    --region ${ALARM_REGION} \
    --profile ${PROFILE}

echo "Topic policy set"

# -----------------------------------------------
# 4. Subscribe alarm-trigger Lambda to SNS Topic
# -----------------------------------------------
ALARM_TRIGGER_LAMBDA_ARN="arn:aws:lambda:${LAMBDA_REGION}:${ACCOUNT_ID}:function:incident-alarm-trigger"

echo ""
echo "Subscribing Lambda to SNS topic..."
echo "Lambda ARN: $ALARM_TRIGGER_LAMBDA_ARN"

# Add SNS invoke permission to Lambda (cross-region)
echo "Adding SNS invoke permission to Lambda..."
aws lambda add-permission \
    --function-name incident-alarm-trigger \
    --statement-id sns-alarm-invoke \
    --action lambda:InvokeFunction \
    --principal sns.amazonaws.com \
    --source-arn ${SNS_TOPIC_ARN} \
    --region ${LAMBDA_REGION} \
    --profile ${PROFILE} 2>/dev/null || echo "Permission already exists"

# Create subscription
aws sns subscribe \
    --topic-arn ${SNS_TOPIC_ARN} \
    --protocol lambda \
    --notification-endpoint ${ALARM_TRIGGER_LAMBDA_ARN} \
    --region ${ALARM_REGION} \
    --profile ${PROFILE}

echo "Lambda subscribed to SNS topic"

# -----------------------------------------------
# 5. Create CloudWatch Alarms
# -----------------------------------------------
echo ""
echo "==========================================="
echo " Creating CloudWatch Alarms"
echo "==========================================="

# 5a. CPU Spike Alarm
echo ""
echo "Creating alarm: netaiops-cpu-spike..."
aws cloudwatch put-metric-alarm \
    --alarm-name "netaiops-cpu-spike" \
    --alarm-description "EKS pod CPU utilization exceeds 80% - possible CPU stress incident" \
    --namespace "ContainerInsights" \
    --metric-name "pod_cpu_utilization" \
    --dimensions Name=ClusterName,Value=${CLUSTER_NAME} \
    --statistic Average \
    --period 60 \
    --evaluation-periods 3 \
    --datapoints-to-alarm 2 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --alarm-actions ${SNS_TOPIC_ARN} \
    --ok-actions ${SNS_TOPIC_ARN} \
    --treat-missing-data notBreaching \
    --region ${ALARM_REGION} \
    --profile ${PROFILE}
echo "Created: netaiops-cpu-spike (pod CPU > 80%)"

# 5b. Pod Restarts Alarm
echo ""
echo "Creating alarm: netaiops-pod-restarts..."
aws cloudwatch put-metric-alarm \
    --alarm-name "netaiops-pod-restarts" \
    --alarm-description "EKS pod container restarts exceed 3 in 5 minutes - possible CrashLoopBackOff" \
    --namespace "ContainerInsights" \
    --metric-name "pod_number_of_container_restarts" \
    --dimensions Name=ClusterName,Value=${CLUSTER_NAME} \
    --statistic Sum \
    --period 300 \
    --evaluation-periods 1 \
    --datapoints-to-alarm 1 \
    --threshold 3 \
    --comparison-operator GreaterThanThreshold \
    --alarm-actions ${SNS_TOPIC_ARN} \
    --ok-actions ${SNS_TOPIC_ARN} \
    --treat-missing-data notBreaching \
    --region ${ALARM_REGION} \
    --profile ${PROFILE}
echo "Created: netaiops-pod-restarts (restarts > 3 in 5 min)"

# 5c. Node CPU High Alarm
echo ""
echo "Creating alarm: netaiops-node-cpu-high..."
aws cloudwatch put-metric-alarm \
    --alarm-name "netaiops-node-cpu-high" \
    --alarm-description "EKS node CPU utilization exceeds 85% - possible node-level resource pressure" \
    --namespace "ContainerInsights" \
    --metric-name "node_cpu_utilization" \
    --dimensions Name=ClusterName,Value=${CLUSTER_NAME} \
    --statistic Average \
    --period 60 \
    --evaluation-periods 3 \
    --datapoints-to-alarm 2 \
    --threshold 85 \
    --comparison-operator GreaterThanThreshold \
    --alarm-actions ${SNS_TOPIC_ARN} \
    --ok-actions ${SNS_TOPIC_ARN} \
    --treat-missing-data notBreaching \
    --region ${ALARM_REGION} \
    --profile ${PROFILE}
echo "Created: netaiops-node-cpu-high (node CPU > 85%)"

# -----------------------------------------------
# 6. Store SNS Topic ARN in SSM
# -----------------------------------------------
echo ""
echo "Storing SNS Topic ARN in SSM..."
aws ssm put-parameter \
    --name "/app/incident/agentcore/sns_topic_arn" \
    --value "$SNS_TOPIC_ARN" \
    --type "String" \
    --overwrite \
    --region ${LAMBDA_REGION} \
    --profile ${PROFILE}

# -----------------------------------------------
# 7. Summary
# -----------------------------------------------
echo ""
echo "==========================================="
echo " CloudWatch Alarms Setup Complete!"
echo "==========================================="
echo ""
echo "SNS Topic: $SNS_TOPIC_ARN"
echo ""
echo "CloudWatch Alarms (${ALARM_REGION}):"
echo "  netaiops-cpu-spike       → pod CPU > 80% (2 of 3 datapoints, period=60s)"
echo "  netaiops-pod-restarts    → container restarts > 3 (5 min window)"
echo "  netaiops-node-cpu-high   → node CPU > 85% (2 of 3 datapoints, period=60s)"
echo ""
echo "Lambda Subscription: $ALARM_TRIGGER_LAMBDA_ARN"
echo ""
echo "SSM Parameter: /app/incident/agentcore/sns_topic_arn"
echo ""
echo "To test, trigger a chaos scenario from the frontend or manually:"
echo "  aws lambda invoke --function-name incident-chaos-tools \\"
echo "    --payload '{\"name\":\"chaos-cpu-stress\",\"arguments\":{}}' \\"
echo "    --region ${LAMBDA_REGION} --profile ${PROFILE} /dev/stdout"
echo ""
