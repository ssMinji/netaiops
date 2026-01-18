#!/bin/bash

set -e

echo "🚀 Deploying Troubleshooting Agent Prerequisites"
echo "=============================================="

# Configuration
STACK_NAME="troubleshooting-agentcore-cognito"
REGION="us-east-1"

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE_FILE="$PROJECT_ROOT/prerequisite/cognito.yaml"

echo "📁 Script directory: $SCRIPT_DIR"
echo "📁 Project root: $PROJECT_ROOT"
echo "📁 Template file: $TEMPLATE_FILE"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "❌ AWS CLI not configured. Please run 'aws configure' first."
    exit 1
fi

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "📋 AWS Account ID: $ACCOUNT_ID"
echo "📋 Region: $REGION"

# Check if CloudFormation template exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    echo "❌ CloudFormation template not found: $TEMPLATE_FILE"
    echo "📁 Current working directory: $(pwd)"
    echo "📁 Looking for template at: $TEMPLATE_FILE"
    exit 1
fi

echo "📦 Deploying Cognito infrastructure..."

# Deploy or update CloudFormation stack
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" > /dev/null 2>&1; then
    echo "🔄 Stack exists, updating..."
    aws cloudformation update-stack \
        --stack-name "$STACK_NAME" \
        --template-body file://"$TEMPLATE_FILE" \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region "$REGION"
    
    echo "⏳ Waiting for stack update to complete..."
    aws cloudformation wait stack-update-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION"
else
    echo "🆕 Creating new stack..."
    aws cloudformation create-stack \
        --stack-name "$STACK_NAME" \
        --template-body file://"$TEMPLATE_FILE" \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region "$REGION"
    
    echo "⏳ Waiting for stack creation to complete..."
    aws cloudformation wait stack-create-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION"
fi

echo "✅ CloudFormation stack deployed successfully!"

# Get stack outputs
echo "📋 Stack Outputs:"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table

# Verify SSM parameters were created
echo "🔍 Verifying SSM parameters..."
PARAMETERS=(
    "/app/troubleshooting/agentcore/machine_client_id"
    "/app/troubleshooting/agentcore/web_client_id"
    "/app/troubleshooting/agentcore/cognito_provider"
    "/app/troubleshooting/agentcore/cognito_domain"
    "/app/troubleshooting/agentcore/cognito_token_url"
    "/app/troubleshooting/agentcore/cognito_discovery_url"
    "/app/troubleshooting/agentcore/cognito_auth_url"
    "/app/troubleshooting/agentcore/cognito_auth_scope"
    "/app/troubleshooting/agentcore/userpool_id"
    "/app/troubleshooting/agentcore/gateway_iam_role"
)

for param in "${PARAMETERS[@]}"; do
    if aws ssm get-parameter --name "$param" --region "$REGION" > /dev/null 2>&1; then
        VALUE=$(aws ssm get-parameter --name "$param" --region "$REGION" --query 'Parameter.Value' --output text)
        echo "  ✅ $param = $VALUE"
    else
        echo "  ❌ $param = NOT FOUND"
    fi
done

# Create test user
echo "👤 Creating test user..."
USER_POOL_ID=$(aws ssm get-parameter --name "/app/troubleshooting/agentcore/userpool_id" --region "$REGION" --query 'Parameter.Value' --output text)
TEST_EMAIL="test@example.com"

if aws cognito-idp admin-get-user --user-pool-id "$USER_POOL_ID" --username "$TEST_EMAIL" --region "$REGION" > /dev/null 2>&1; then
    echo "  ℹ️  Test user '$TEST_EMAIL' already exists"
else
    echo "  🆕 Creating test user '$TEST_EMAIL'..."
    aws cognito-idp admin-create-user \
        --user-pool-id "$USER_POOL_ID" \
        --username "$TEST_EMAIL" \
        --user-attributes Name=email,Value="$TEST_EMAIL" Name=email_verified,Value=true \
        --temporary-password "TempPassword123!" \
        --message-action SUPPRESS \
        --region "$REGION"
    
    # Set permanent password
    aws cognito-idp admin-set-user-password \
        --user-pool-id "$USER_POOL_ID" \
        --username "$TEST_EMAIL" \
        --password "TestPassword123!" \
        --permanent \
        --region "$REGION"
    
    echo "  ✅ Test user created with email: $TEST_EMAIL"
    echo "  ✅ Test password: TestPassword123!"
fi

echo ""
echo "🎉 Prerequisites deployment completed successfully!"
echo ""
echo "📋 Next steps:"
echo "   1. Deploy the agent runtime using the deployment scripts"
echo "   2. Test the agent using: python test/test_agent.py troubleshooting"
echo ""
