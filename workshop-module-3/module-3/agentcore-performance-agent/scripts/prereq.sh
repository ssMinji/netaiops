#!/bin/bash

# Don't exit on error - we handle errors explicitly
set +e

echo "🚀 Deploying Performance Agent Prerequisites"
echo "=============================================="

# Configuration - make region configurable
STACK_NAME="a2a-performance-agentcore-cognito"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
GATEWAY_ROLE_NAME="performance-gateway-execution-role"

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
STAGE_ROOT="$(dirname "$PROJECT_ROOT")"
TEMPLATE_FILE="$PROJECT_ROOT/prerequisite/cognito.yaml"

# Source IAM utilities for smart wait logic
IAM_UTILS_PATH="$SCRIPT_DIR/iam_utils.sh"
if [ -f "$IAM_UTILS_PATH" ]; then
    echo "📦 Loading IAM utilities..."
    source "$IAM_UTILS_PATH"
else
    echo "⚠️  Warning: IAM utilities not found at $IAM_UTILS_PATH"
    echo "   Falling back to simple wait logic"
fi

echo "📁 Script directory: $SCRIPT_DIR"
echo "📁 Project root: $PROJECT_ROOT"
echo "📁 Stage root: $STAGE_ROOT"
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

# Deploy or update CloudFormation stack (idempotent - handles "no updates" as success)
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" > /dev/null 2>&1; then
    echo "🔄 Stack exists, updating..."
    
    # Capture update-stack output and handle "No updates" gracefully
    UPDATE_OUTPUT=$(aws cloudformation update-stack \
        --stack-name "$STACK_NAME" \
        --template-body file://"$TEMPLATE_FILE" \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region "$REGION" 2>&1) || UPDATE_EXIT_CODE=$?
    
    # Check exit code and output
    if [ -z "$UPDATE_EXIT_CODE" ] || [ "$UPDATE_EXIT_CODE" -eq 0 ]; then
        # Update succeeded, wait for completion
        echo "⏳ Waiting for stack update to complete..."
        if ! aws cloudformation wait stack-update-complete \
            --stack-name "$STACK_NAME" \
            --region "$REGION"; then
            echo "❌ Stack update wait failed"
            exit 1
        fi
        echo "✅ Stack updated successfully"
    elif echo "$UPDATE_OUTPUT" | grep -qi "No updates are to be performed\|ValidationError.*No updates"; then
        # No updates needed - this is OK (idempotent)
        echo "✅ Stack already up-to-date, no changes needed"
    else
        # Real error occurred
        echo "❌ Stack update failed with exit code: ${UPDATE_EXIT_CODE:-unknown}"
        echo "❌ Error output: $UPDATE_OUTPUT"
        exit 1
    fi
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

# Wait for SSM parameters to propagate AND verify role creation (eventual consistency)
echo "⏳ Waiting for SSM parameters to propagate and verifying IAM role..."
echo "   Checking for role: $GATEWAY_ROLE_NAME"

# Check if IAM role exists with retry logic
check_role_with_retry() {
    local role_name=$1
    local max_attempts=12  # 12 attempts * 5 seconds = 60 seconds total
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if aws iam get-role --role-name "$role_name" --region "$REGION" &> /dev/null; then
            echo "  ✅ Role '$role_name' found!"
            return 0
        fi
        
        if [ $attempt -lt $max_attempts ]; then
            echo "  ⏳ Attempt $attempt/$max_attempts - Role not found yet, waiting 5 seconds..."
            sleep 5
            attempt=$((attempt + 1))
        else
            echo "  ⚠️  Role not found after $max_attempts attempts (60 seconds)"
            echo "  ℹ️  This is OK if the role will be created by a later step"
            return 1
        fi
    done
}

# Use smart wait if available, otherwise fallback
if type wait_for_iam_role_propagation &>/dev/null; then
    # Use IAM utilities with smart backoff
    ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${GATEWAY_ROLE_NAME}"
    wait_for_iam_role_propagation "$ROLE_ARN" 30
    
    # Additional verification
    check_role_with_retry "$GATEWAY_ROLE_NAME"
else
    # Fallback: simple check with retries
    check_role_with_retry "$GATEWAY_ROLE_NAME"
fi

echo "✅ Parameter propagation wait completed"

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
    "/a2a/app/performance/agentcore/machine_client_id"
    "/a2a/app/performance/agentcore/web_client_id"
    "/a2a/app/performance/agentcore/cognito_provider"
    "/a2a/app/performance/agentcore/cognito_domain"
    "/a2a/app/performance/agentcore/cognito_token_url"
    "/a2a/app/performance/agentcore/cognito_discovery_url"
    "/a2a/app/performance/agentcore/cognito_auth_url"
    "/a2a/app/performance/agentcore/cognito_auth_scope"
    "/a2a/app/performance/agentcore/userpool_id"
    "/a2a/app/performance/agentcore/gateway_iam_role"
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
USER_POOL_ID=$(aws ssm get-parameter --name "/a2a/app/performance/agentcore/userpool_id" --region "$REGION" --query 'Parameter.Value' --output text)
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

# Capture agentcore performance values and update module3-config.json
echo "📝 Capturing agentcore performance values..."

# Define the config file path (relative to stage root)
CONFIG_FILE="$STAGE_ROOT/module3-config.json"

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Config file not found: $CONFIG_FILE"
    exit 1
fi

# Create a backup of the original config file
cp "$CONFIG_FILE" "$CONFIG_FILE.backup"

# Capture the required SSM parameter values
MACHINE_CLIENT_ID=$(aws ssm get-parameter --name "/a2a/app/performance/agentcore/machine_client_id" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")
COGNITO_PROVIDER=$(aws ssm get-parameter --name "/a2a/app/performance/agentcore/cognito_provider" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")
COGNITO_AUTH_SCOPE=$(aws ssm get-parameter --name "/a2a/app/performance/agentcore/cognito_auth_scope" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")
COGNITO_DISCOVERY_URL=$(aws ssm get-parameter --name "/a2a/app/performance/agentcore/cognito_discovery_url" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")

echo "  📋 machine_client_id: $MACHINE_CLIENT_ID"
echo "  📋 cognito_provider: $COGNITO_PROVIDER"
echo "  📋 cognito_auth_scope: $COGNITO_AUTH_SCOPE"
echo "  📋 cognito_discovery_url: $COGNITO_DISCOVERY_URL"

# Update the config file using python (more reliable than jq)
python3 -c "
import json
import sys

config_file = '$CONFIG_FILE'
try:
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Add or update the agentcore_performance section
    config['agentcore_performance'] = {
        'machine_client_id': '$MACHINE_CLIENT_ID',
        'cognito_provider': '$COGNITO_PROVIDER',
        'cognito_auth_scope': '$COGNITO_AUTH_SCOPE',
        'cognito_discovery_url': '$COGNITO_DISCOVERY_URL'
    }
    
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print('  ✅ Updated config file using python')
except Exception as e:
    print(f'  ❌ Error updating config file: {e}')
    sys.exit(1)
"

# Verify the update was successful
if grep -q "agentcore_performance" "$CONFIG_FILE"; then
    echo "  ✅ Configuration update verified"
else
    echo "  ❌ Configuration update failed - agentcore_performance section not found"
    exit 1
fi

echo "  📁 Config file updated: $CONFIG_FILE"
echo "  📁 Backup created: $CONFIG_FILE.backup"

echo ""
echo "🎉 Prerequisites deployment completed successfully!"
echo ""
echo "📋 Next steps:"
echo "   1. Deploy the agent runtime using the deployment scripts"
echo "   2. Test the agent using: python test/test_agent.py performance"
echo "   3. Review updated configuration in: $CONFIG_FILE"
echo ""
echo "ℹ️  Note: Docker installation skipped (assuming Docker is already available locally)"
