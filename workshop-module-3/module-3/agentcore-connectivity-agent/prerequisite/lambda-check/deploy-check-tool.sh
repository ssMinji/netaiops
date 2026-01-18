#!/bin/bash

# One-Click Connectivity Check Lambda Deployment - Docker Container Approach
# Fixes 70MB layer limit by using containers (up to 10GB)
set -e

echo "🚀 One-Click Connectivity Check Tool Deployment"
echo "=============================================="

# Configuration
REGION="us-east-1"
STACK_NAME="a2a-connectivity-check-tool-lambda"
ECR_REPOSITORY="a2a-connectivity-check-tool-repo"

# Get Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "📋 Account: $ACCOUNT_ID | Region: $REGION"

# Build Docker image with Strands packages (no size limits!)
echo "🐳 Building Docker image for Lambda (x86_64 architecture)..."
cd python
docker build --platform linux/amd64 -t a2a-connectivity-check-lambda:latest .
cd ..

# Build ECR URI
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPOSITORY}"

# Check if ECR repository exists, create if not
echo "🔍 Checking ECR repository..."
if ! aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${REGION} &> /dev/null; then
    echo "📦 Creating ECR repository..."
    aws ecr create-repository --repository-name ${ECR_REPOSITORY} --region ${REGION}
fi

# Login to ECR
echo "🔑 Logging in to ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Tag and push Docker image
echo "🏷️  Tagging and pushing Docker image..."
docker tag a2a-connectivity-check-lambda:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# Deploy Lambda function directly with AWS CLI (no SAM required!)
echo "🚀 Deploying Lambda function with AWS CLI..."

FUNCTION_NAME="a2a-connectivity-check-tool"
ROLE_NAME="a2a-connectivity-check-tool-role"

# Create Lambda execution role
echo "🔐 Creating Lambda execution role..."
aws iam create-role \
    --role-name ${ROLE_NAME} \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            },
            {
                "Effect": "Allow", 
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }' \
    --region ${REGION} 2>/dev/null || echo "Role exists"

# Attach managed policies
aws iam attach-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    --region ${REGION} 2>/dev/null || true

aws iam attach-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess \
    --region ${REGION} 2>/dev/null || true

# Add Bedrock permissions
aws iam put-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-name BedrockInvokePolicy \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            "Resource": "*"
        }]
    }' \
    --region ${REGION} 2>/dev/null || true

# Add VPC Reachability Analyzer permissions
aws iam put-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-name VPCReachabilityAnalyzerPolicy \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "ec2:CreateNetworkInsightsPath",
                "ec2:StartNetworkInsightsAnalysis",
                "ec2:DescribeNetworkInsightsAnalyses",
                "ec2:DescribeNetworkInsightsPaths",
                "ec2:DeleteNetworkInsightsPath",
                "ec2:DeleteNetworkInsightsAnalysis",
                "ec2:DescribeInstances",
                "ec2:DescribeSubnets",
                "ec2:DescribeVpcs",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeNetworkAcls",
                "ec2:DescribeRouteTables",
                "tiros:CreateQuery",
                "tiros:GetQueryAnswer",
                "tiros:GetQueryExplanation"
            ],
            "Resource": "*"
        }]
    }' \
    --region ${REGION} 2>/dev/null || true

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "✅ Role created: $ROLE_ARN"

# Wait a moment for role to propagate
sleep 5

# Additional wait before creating lambda
echo "⏳ Waiting 15 seconds before creating lambda..."
sleep 15

# Create/update Lambda function from container image
echo "⚡ Creating Lambda function from container image..."
aws lambda create-function \
    --function-name ${FUNCTION_NAME} \
    --package-type Image \
    --code ImageUri=${ECR_URI}:latest \
    --role ${ROLE_ARN} \
    --timeout 900 \
    --memory-size 3008 \
    --region ${REGION} 2>/dev/null || \
aws lambda update-function-code \
    --function-name ${FUNCTION_NAME} \
    --image-uri ${ECR_URI}:latest \
    --region ${REGION}

LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"

# Use existing gateway execution role created by CloudFormation
GATEWAY_ROLE_NAME="performance-gateway-execution-role"
echo "🚪 Using Gateway execution role created by CloudFormation..."
GATEWAY_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${GATEWAY_ROLE_NAME}"

# Verify role exists
if ! aws iam get-role --role-name ${GATEWAY_ROLE_NAME} --region ${REGION} &> /dev/null; then
    echo "❌ Gateway execution role not found. Please deploy CloudFormation stack first:"
    echo "   cd scripts && ./prereq.sh"
    exit 1
fi
echo "✅ Gateway role verified: ${GATEWAY_ROLE_ARN}"

# Store parameters for gateway integration
echo "💾 Storing SSM parameters..."
aws ssm put-parameter \
    --name "/a2a/app/troubleshooting/agentcore/lambda_arn" \
    --value "$LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region $REGION

aws ssm put-parameter \
    --name "/a2a/app/performance/agentcore/gateway_iam_role" \
    --value "$GATEWAY_ROLE_ARN" \
    --type "String" \
    --overwrite \
    --region $REGION

echo ""
echo "✅ One-Click Deployment Complete!"
echo "   Lambda ARN: $LAMBDA_ARN"
echo "   Gateway Role ARN: $GATEWAY_ROLE_ARN"
echo "   Container Image: ${ECR_URI}:latest"
echo ""
echo "🎯 Next Steps:"
echo "   python ../../scripts/agentcore_gateway.py create --name troubleshooting-gateway"
echo "   python ../../scripts/agentcore_agent_runtime.py create --name troubleshooting_agent_runtime"
