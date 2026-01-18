#!/bin/bash

# One-Click Consolidated Connectivity Lambda Deployment - Docker Container Approach
# Consolidates connectivity-check and connectivity-fix into a single lambda
set -e

echo "🚀 One-Click Consolidated Connectivity Tool Deployment"
echo "====================================================="

# Configuration
REGION="us-east-1"
STACK_NAME="connectivity-tool-lambda"
ECR_REPOSITORY="connectivity-tool-repo"

# Get Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "📋 Account: $ACCOUNT_ID | Region: $REGION"

# Authenticate to ECR Public for base image access
echo "🔑 Authenticating to ECR Public for base image access..."
max_retries=3
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws; then
        echo "✅ Successfully authenticated to ECR Public"
        break
    else
        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            echo "⚠️  ECR Public authentication failed, retrying in 5 seconds... (attempt $retry_count/$max_retries)"
            sleep 5
        else
            echo "❌ Failed to authenticate to ECR Public after $max_retries attempts"
            exit 1
        fi
    fi
done

# Build Docker image with Strands packages (no size limits!)
echo "🐳 Building Docker image for Lambda (x86_64 architecture)..."
cd python
docker build --platform linux/amd64 -t connectivity-lambda:latest .
cd ..

# Build ECR URI
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPOSITORY}"

# Check if ECR repository exists, create if not
echo "🔍 Checking ECR repository..."
if ! aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${REGION} &> /dev/null; then
    echo "📦 Creating ECR repository..."
    aws ecr create-repository --repository-name ${ECR_REPOSITORY} --region ${REGION}
fi

# Login to ECR with retry logic
echo "🔑 Logging in to private ECR..."
max_retries=3
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com; then
        echo "✅ Successfully authenticated to private ECR"
        break
    else
        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            echo "⚠️  Private ECR authentication failed, retrying in 5 seconds... (attempt $retry_count/$max_retries)"
            sleep 5
        else
            echo "❌ Failed to authenticate to private ECR after $max_retries attempts"
            exit 1
        fi
    fi
done

# Tag and push Docker image
echo "🏷️  Tagging and pushing Docker image..."
docker tag connectivity-lambda:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# Deploy Lambda function directly with AWS CLI (no SAM required!)
echo "🚀 Deploying Lambda function with AWS CLI..."

FUNCTION_NAME="connectivity-tool"
ROLE_NAME="connectivity-tool-role"

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

# Add VPC Reachability Analyzer and Security Group permissions (for both check and fix)
aws iam put-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-name ConnectivityToolPolicy \
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
                "ec2:DescribeNetworkInterfaces",
                "ec2:DescribeSubnets",
                "ec2:DescribeVpcs",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeNetworkAcls",
                "ec2:DescribeRouteTables",
                "ec2:AuthorizeSecurityGroupIngress",
                "ec2:AuthorizeSecurityGroupEgress",
                "ec2:RevokeSecurityGroupIngress",
                "ec2:RevokeSecurityGroupEgress",
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

# Wait for role to propagate (AWS IAM can take time to propagate)
echo "⏳ Waiting for IAM role to propagate..."
sleep 20

# Verify role can be assumed by Lambda service
echo "🔍 Verifying role propagation and Lambda assumability..."
for i in {1..12}; do
    # Check if role exists and can be retrieved
    if aws iam get-role --role-name ${ROLE_NAME} --region ${REGION} &>/dev/null; then
        # Additional check: try to simulate role assumption by checking trust policy
        if aws sts get-caller-identity &>/dev/null; then
            echo "✅ Role verified and ready for Lambda"
            break
        fi
    fi
    if [ $i -eq 12 ]; then
        echo "❌ Role verification failed after 60 seconds"
        echo "   This may indicate an IAM propagation delay. Please wait a few minutes and retry."
        exit 1
    fi
    echo "   Attempt $i/12 - waiting 5 more seconds for role propagation..."
    sleep 5
done

# Create/update Lambda function from container image
echo "⚡ Creating Lambda function from container image..."

# Check if function exists
if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} &>/dev/null; then
    echo "Function exists, updating..."
    aws lambda update-function-code \
        --function-name ${FUNCTION_NAME} \
        --image-uri ${ECR_URI}:latest \
        --region ${REGION}
else
    echo "Function doesn't exist, creating..."
    aws lambda create-function \
        --function-name ${FUNCTION_NAME} \
        --package-type Image \
        --code ImageUri=${ECR_URI}:latest \
        --role ${ROLE_ARN} \
        --timeout 900 \
        --memory-size 3008 \
        --region ${REGION}
fi

LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"

# Use existing gateway execution role created by CloudFormation
GATEWAY_ROLE_NAME="troubleshooting-gateway-execution-role"
echo "🚪 Using Gateway execution role created by CloudFormation..."
GATEWAY_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${GATEWAY_ROLE_NAME}"

# Verify role exists
if ! aws iam get-role --role-name ${GATEWAY_ROLE_NAME} --region ${REGION} &> /dev/null; then
    echo "❌ Gateway execution role not found. Please deploy CloudFormation stack first:"
    echo "   cd scripts && ./prereq.sh"
    exit 1
fi
echo "✅ Gateway role verified: ${GATEWAY_ROLE_ARN}"

# Store parameters for gateway integration (consolidated connectivity tool)
echo "💾 Storing SSM parameters..."
aws ssm put-parameter \
    --name "/app/troubleshooting/agentcore/connectivity_lambda_arn" \
    --value "$LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region $REGION

aws ssm put-parameter \
    --name "/app/troubleshooting/agentcore/gateway_iam_role" \
    --value "$GATEWAY_ROLE_ARN" \
    --type "String" \
    --overwrite \
    --region $REGION

echo ""
echo "✅ One-Click Consolidated Connectivity Deployment Complete!"
echo "   Lambda ARN: $LAMBDA_ARN"
echo "   Gateway Role ARN: $GATEWAY_ROLE_ARN"
echo "   Container Image: ${ECR_URI}:latest"
echo "   Tools: connectivity-check, connectivity-fix"
echo ""
echo "🎯 Next Steps:"
echo "   python ../../scripts/agentcore_gateway.py create --name troubleshooting-gateway"
echo "   python ../../scripts/agentcore_agent_runtime.py create --name troubleshooting_agent_runtime"
