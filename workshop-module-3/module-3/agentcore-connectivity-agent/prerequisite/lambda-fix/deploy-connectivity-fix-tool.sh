#!/bin/bash

# Connectivity Fix Tool Lambda Deployment - Docker Container Approach
# Automatically fixes connectivity issues with least privilege security group rules
set -e

# Helper function for retry with fixed wait times
retry_with_backoff() {
    local max_attempts=$1
    shift
    local description=$1
    shift
    
    # Fixed wait times: 45s for 2nd attempt, 60s for 3rd attempt
    local wait_times=(0 45 60)
    
    for attempt in $(seq 1 $max_attempts); do
        echo "  🔄 Attempt $attempt of $max_attempts: $description"
        
        # Capture both stdout and stderr, preserve exit code
        local output
        local exit_code
        output=$(eval "$@" 2>&1) || exit_code=$?
        
        if [ -z "${exit_code:-}" ]; then
            echo "  ✅ $description succeeded"
            return 0
        fi
        
        # Parse error message
        echo "  ⚠️  Attempt $attempt failed with exit code: $exit_code"
        echo "  📝 Error details: ${output:0:500}"
        
        # Check for specific IAM errors that need retry
        if echo "$output" | grep -qE "(InvalidParameterValueException.*role|cannot be assumed|role.*not exist|AccessDenied|not authorized|Entity already exists|role.*not found)"; then
            if [ $attempt -lt $max_attempts ]; then
                local wait_time=${wait_times[$attempt]}
                echo "  🔐 Detected IAM propagation issue - will retry"
                echo "  ⏳ Waiting ${wait_time}s before retry..."
                sleep $wait_time
            else
                echo "  ❌ Max retries ($max_attempts) reached"
                echo "  💡 IAM role may need more time to propagate"
                return $exit_code
            fi
        else
            # Not an IAM error, fail immediately
            echo "  ❌ Non-IAM error detected - failing"
            return $exit_code
        fi
    done
    
    return 1
}

echo "🔧 Connectivity Fix Tool Deployment"
echo "=========================================="

# Configuration
REGION="us-east-1"
STACK_NAME="a2a-connectivity-fix-tool-lambda"
ECR_REPOSITORY="a2a-connectivity-fix-tool-repo"

# Get Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "📋 Account: $ACCOUNT_ID | Region: $REGION"

# Build Docker image with Strands packages (no size limits!)
echo "🐳 Building Docker image for Connectivity Fix Lambda (x86_64 architecture)..."
cd python
docker build --platform linux/amd64 -t a2a-connectivity-fix-lambda:latest .
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
docker tag a2a-connectivity-fix-lambda:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# Deploy Lambda function directly with AWS CLI
echo "🚀 Deploying Connectivity Fix Lambda function with AWS CLI..."

FUNCTION_NAME="a2a-connectivity-fix-tool"
ROLE_NAME="a2a-connectivity-fix-tool-role"

# Create Lambda execution role (idempotent)
echo "🔐 Creating/verifying Lambda execution role..."
if aws iam get-role --role-name ${ROLE_NAME} --region ${REGION} &>/dev/null; then
    echo "✅ Role ${ROLE_NAME} already exists"
else
    echo "🆕 Creating role ${ROLE_NAME}..."
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
        --region ${REGION}
    echo "✅ Role created"
fi

# Attach managed policies (idempotent)
echo "🔗 Attaching managed policies..."
if aws iam list-attached-role-policies --role-name ${ROLE_NAME} --region ${REGION} 2>/dev/null | grep -q "AWSLambdaBasicExecutionRole"; then
    echo "✅ AWSLambdaBasicExecutionRole already attached"
else
    aws iam attach-role-policy \
        --role-name ${ROLE_NAME} \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
        --region ${REGION}
    echo "✅ Attached AWSLambdaBasicExecutionRole"
fi

if aws iam list-attached-role-policies --role-name ${ROLE_NAME} --region ${REGION} 2>/dev/null | grep -q "ReadOnlyAccess"; then
    echo "✅ ReadOnlyAccess already attached"
else
    aws iam attach-role-policy \
        --role-name ${ROLE_NAME} \
        --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess \
        --region ${REGION}
    echo "✅ Attached ReadOnlyAccess"
fi

# Add Bedrock permissions (idempotent - put-role-policy creates or updates)
echo "📝 Adding/updating Bedrock permissions..."
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
    --region ${REGION}
echo "✅ Bedrock permissions configured"

# Add VPC Reachability Analyzer and Security Group management permissions (idempotent - put-role-policy creates or updates)
echo "📝 Adding/updating connectivity fix permissions..."
aws iam put-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-name ConnectivityFixPolicy \
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
    --region ${REGION}
echo "✅ Connectivity fix permissions configured"

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "✅ Role ARN: $ROLE_ARN"

# Create/update Lambda function from container image (idempotent with retry logic)
echo "⚡ Creating/updating Connectivity Fix Lambda function from container image..."

# Check if function exists
if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} &>/dev/null; then
    echo "✅ Function exists, updating code..."
    aws lambda update-function-code \
        --function-name ${FUNCTION_NAME} \
        --image-uri ${ECR_URI}:latest \
        --region ${REGION}
    echo "✅ Function code updated"
else
    echo "🆕 Function doesn't exist, creating with IAM retry logic..."
    
    # Initial wait for IAM role propagation
    echo "⏳ Waiting 30 seconds for IAM role propagation..."
    sleep 30
    
    # Use retry logic to create Lambda with automatic retry on IAM propagation errors (3 attempts)
    retry_with_backoff 3 "Creating Lambda function ${FUNCTION_NAME}" \
        aws lambda create-function \
        --function-name ${FUNCTION_NAME} \
        --package-type Image \
        --code ImageUri=${ECR_URI}:latest \
        --role ${ROLE_ARN} \
        --timeout 900 \
        --memory-size 3008 \
        --region ${REGION}
    
    if [ $? -eq 0 ]; then
        echo "✅ Lambda function created successfully"
    else
        echo "❌ Failed to create Lambda function after retries"
        exit 1
    fi
fi

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
    --name "/a2a/app/troubleshooting/agentcore/connectivity_fix_lambda_arn" \
    --value "$LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region $REGION

# Update gateway IAM role parameter (ensures consistency)
aws ssm put-parameter \
    --name "/a2a/app/performance/agentcore/gateway_iam_role" \
    --value "$GATEWAY_ROLE_ARN" \
    --type "String" \
    --overwrite \
    --region $REGION

echo ""
echo "✅ Connectivity Fix Tool Deployment Complete!"
echo "   Lambda ARN: $LAMBDA_ARN"
echo "   Gateway Role ARN: $GATEWAY_ROLE_ARN"
echo "   Container Image: ${ECR_URI}:latest"
echo ""
echo "🎯 This Lambda provides:"
echo "   - Least privilege security group rule fixes (/32 CIDRs)"
echo "   - Automatic connectivity validation"
echo "   - Integration with VPC Reachability Analyzer"
echo ""
echo "🔧 Next: Add this tool to your troubleshooting-gateway configuration"
