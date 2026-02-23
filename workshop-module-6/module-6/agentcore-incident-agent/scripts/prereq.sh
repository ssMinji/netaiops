#!/bin/bash

set -e

echo "Deploying Incident Analysis Agent Prerequisites"
echo "================================================"

# Configuration
STACK_NAME="incident-agentcore-cognito"
REGION="us-east-1"
AWS_PROFILE="netaiops-deploy"
export AWS_PROFILE

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
# cognito.yaml is in the prerequisite directory alongside the lambda dirs
TEMPLATE_FILE="$PROJECT_ROOT/../prerequisite/cognito.yaml"

echo "Script directory: $SCRIPT_DIR"
echo "Project root: $PROJECT_ROOT"
echo "Template file: $TEMPLATE_FILE"
echo "AWS Profile: $AWS_PROFILE"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity --profile "$AWS_PROFILE" > /dev/null 2>&1; then
    echo "ERROR: AWS CLI not configured for profile '$AWS_PROFILE'. Please run 'aws configure --profile $AWS_PROFILE' first."
    exit 1
fi

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)
echo "AWS Account ID: $ACCOUNT_ID"
echo "Region: $REGION"

# Check if CloudFormation template exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    echo "ERROR: CloudFormation template not found: $TEMPLATE_FILE"
    echo "Current working directory: $(pwd)"
    echo "Looking for template at: $TEMPLATE_FILE"
    exit 1
fi

echo ""
echo "Step 1: Deploying Cognito infrastructure..."
echo "---------------------------------------------"

# Deploy or update CloudFormation stack
if aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --profile "$AWS_PROFILE" > /dev/null 2>&1; then
    echo "Stack exists, updating..."
    aws cloudformation update-stack \
        --stack-name "$STACK_NAME" \
        --template-body file://"$TEMPLATE_FILE" \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region "$REGION" \
        --profile "$AWS_PROFILE" 2>&1 || {
        # If no updates are needed, that's okay
        if [[ $? -eq 254 ]] || aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$REGION" \
            --profile "$AWS_PROFILE" \
            --query 'Stacks[0].StackStatus' \
            --output text | grep -q "COMPLETE"; then
            echo "Stack is already up to date."
        else
            echo "ERROR: Stack update failed"
            exit 1
        fi
    }

    echo "Waiting for stack update to complete..."
    aws cloudformation wait stack-update-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --profile "$AWS_PROFILE" 2>/dev/null || true
else
    echo "Creating new stack..."
    aws cloudformation create-stack \
        --stack-name "$STACK_NAME" \
        --template-body file://"$TEMPLATE_FILE" \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region "$REGION" \
        --profile "$AWS_PROFILE"

    echo "Waiting for stack creation to complete..."
    aws cloudformation wait stack-create-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --profile "$AWS_PROFILE"
fi

echo "CloudFormation stack deployed successfully!"

# Get stack outputs
echo ""
echo "Stack Outputs:"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --profile "$AWS_PROFILE" \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table

# Verify SSM parameters were created
echo ""
echo "Step 2: Verifying SSM parameters..."
echo "------------------------------------"
PARAMETERS=(
    "/app/incident/agentcore/machine_client_id"
    "/app/incident/agentcore/web_client_id"
    "/app/incident/agentcore/cognito_provider"
    "/app/incident/agentcore/cognito_domain"
    "/app/incident/agentcore/cognito_token_url"
    "/app/incident/agentcore/cognito_discovery_url"
    "/app/incident/agentcore/cognito_auth_url"
    "/app/incident/agentcore/cognito_auth_scope"
    "/app/incident/agentcore/userpool_id"
    "/app/incident/agentcore/gateway_iam_role"
)

for param in "${PARAMETERS[@]}"; do
    if aws ssm get-parameter \
        --name "$param" \
        --region "$REGION" \
        --profile "$AWS_PROFILE" > /dev/null 2>&1; then
        VALUE=$(aws ssm get-parameter \
            --name "$param" \
            --region "$REGION" \
            --profile "$AWS_PROFILE" \
            --query 'Parameter.Value' \
            --output text)
        echo "  OK: $param = $VALUE"
    else
        echo "  MISSING: $param = NOT FOUND"
    fi
done

# Create test user
echo ""
echo "Step 3: Creating test user..."
echo "------------------------------"
USER_POOL_ID=$(aws ssm get-parameter \
    --name "/app/incident/agentcore/userpool_id" \
    --region "$REGION" \
    --profile "$AWS_PROFILE" \
    --query 'Parameter.Value' \
    --output text)
TEST_EMAIL="test@example.com"

if aws cognito-idp admin-get-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$TEST_EMAIL" \
    --region "$REGION" \
    --profile "$AWS_PROFILE" > /dev/null 2>&1; then
    echo "  Test user '$TEST_EMAIL' already exists"
else
    echo "  Creating test user '$TEST_EMAIL'..."
    aws cognito-idp admin-create-user \
        --user-pool-id "$USER_POOL_ID" \
        --username "$TEST_EMAIL" \
        --user-attributes Name=email,Value="$TEST_EMAIL" Name=email_verified,Value=true \
        --temporary-password "TempPassword123!" \
        --message-action SUPPRESS \
        --region "$REGION" \
        --profile "$AWS_PROFILE"

    # Set permanent password
    aws cognito-idp admin-set-user-password \
        --user-pool-id "$USER_POOL_ID" \
        --username "$TEST_EMAIL" \
        --password "TestPassword123!" \
        --permanent \
        --region "$REGION" \
        --profile "$AWS_PROFILE"

    echo "  Test user created with email: $TEST_EMAIL"
    echo "  Test password: TestPassword123!"
fi

echo ""
echo "================================================"
echo "Prerequisites deployment completed successfully!"
echo "================================================"
echo ""
echo "Next steps:"
echo "   1. Deploy the Lambda tools:"
echo "      - lambda-datadog (Datadog integration)"
echo "      - lambda-opensearch (OpenSearch log search)"
echo "      - lambda-container-insight (EKS Container Insights)"
echo ""
echo "   2. Create the AgentCore gateway:"
echo "      cd scripts/"
echo "      python agentcore_gateway.py create --name incident-analysis-gateway"
echo ""
echo "   3. Deploy the agent runtime:"
echo "      Follow the runtime deployment instructions in the workshop guide."
echo ""
