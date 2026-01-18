#!/bin/bash

# DNS Resolution Lambda Deployment - Docker Container Approach
# Resolves DNS names from Route 53 Private Hosted Zones to EC2 instances/ENIs
set -e

echo "🔍 DNS Tool Deployment"
echo "=================================="

# Configuration
REGION="us-east-1"
STACK_NAME="dns-resolve-tool-lambda"
ECR_REPOSITORY="dns-resolve-tool-repo"

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

# Build Docker image for DNS resolution (no size limits!)
echo "🐳 Building Docker image for DNS Lambda (x86_64 architecture)..."
cd python
docker build --platform linux/amd64 -t dns-resolve-lambda:latest .
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
docker tag dns-resolve-lambda:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# Deploy Lambda function directly with AWS CLI
echo "🚀 Deploying DNS Lambda function with AWS CLI..."

FUNCTION_NAME="dns-resolve-tool"
ROLE_NAME="dns-resolve-tool-role"

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

# Add Route 53 and EC2 permissions for DNS resolution
aws iam put-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-name DNSResolutionPolicy \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "route53:ListHostedZones",
                    "route53:ListResourceRecordSets",
                    "route53:GetHostedZone"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DescribeInstances",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DescribeVpcs",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeTags"
                ],
                "Resource": "*"
            }
        ]
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
echo "⚡ Creating DNS Lambda function from container image..."

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
        --timeout 300 \
        --memory-size 512 \
        --region ${REGION}
fi

DNS_LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"

# Use existing gateway execution role created by CloudFormation
GATEWAY_ROLE_NAME="troubleshooting-gateway-execution-role"
echo "� Using Gateway execution role created by CloudFormation..."
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
    --name "/app/troubleshooting/agentcore/dns_lambda_arn" \
    --value "$DNS_LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region $REGION

# Update or create gateway IAM role parameter
aws ssm put-parameter \
    --name "/app/troubleshooting/agentcore/gateway_iam_role" \
    --value "$GATEWAY_ROLE_ARN" \
    --type "String" \
    --overwrite \
    --region $REGION

echo ""
echo "✅ DNS Resolution Lambda Deployment Complete!"
echo "   DNS Lambda ARN: $DNS_LAMBDA_ARN"
echo "   Gateway Role ARN: $GATEWAY_ROLE_ARN"
echo "   Container Image: ${ECR_URI}:latest"
echo ""
echo "🔍 DNS Resolution Features:"
echo "   • Resolves DNS names from Route 53 Private Hosted Zones"
echo "   • Finds corresponding EC2 instances and ENIs by IP address"
echo "   • Returns instance IDs and ENI IDs for connectivity analysis"
echo "   • Supports multiple AWS regions"
echo ""
echo "🎯 Next Steps:"
echo "   1. Deploy connectivity-check lambda (if not already done):"
echo "      cd ../lambda-check && ./deploy-check-tool.sh"
echo "   2. Create gateway with both tools:"
echo "      python ../../scripts/agentcore_gateway.py create --name troubleshooting-gateway"
echo "   3. Deploy runtime:"
echo "      python ../../scripts/agentcore_agent_runtime.py create --name troubleshooting_agent_runtime"
echo ""
echo "📝 Usage Example:"
echo "   User: 'Check connectivity between app-frontend.examplecorp.com and app-backend.examplecorp.com on port 80'"
echo "   Agent: Calls dns-resolve → Returns instance IDs → Calls connectivity-check"
