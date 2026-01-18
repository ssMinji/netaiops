#!/bin/bash

# 00-generate-module3-config.sh
# Generates module3-config.json for performance agent from SSM parameters and AWS resources

set -e

REGION="${AWS_REGION:-us-east-1}"
CONFIG_FILE="/home/ec2-user/workshop-module-3/module3-config.json"

echo "🔧 Generating module3-config.json for performance agent..."
echo "📍 Region: $REGION"

# Get performance agent ARN
echo "🔍 Fetching performance agent ARN..."
RUNTIME_ARN=$(aws bedrock-agentcore-control list-agent-runtimes \
    --region "$REGION" \
    --query 'agentRuntimes[?agentRuntimeName==`a2a_performance_agent_runtime`].agentRuntimeArn' \
    --output text)

if [ -z "$RUNTIME_ARN" ]; then
    echo "❌ Error: a2a_performance_agent_runtime not found"
    exit 1
fi

echo "✅ Runtime ARN: $RUNTIME_ARN"

# Get SSM parameters
echo "🔍 Fetching SSM parameters..."
MACHINE_CLIENT_ID=$(aws ssm get-parameter \
    --name "/a2a/app/performance/agentcore/machine_client_id" \
    --region "$REGION" \
    --query 'Parameter.Value' \
    --output text)

COGNITO_DISCOVERY_URL=$(aws ssm get-parameter \
    --name "/a2a/app/performance/agentcore/cognito_discovery_url" \
    --region "$REGION" \
    --query 'Parameter.Value' \
    --output text)

COGNITO_PROVIDER=$(aws ssm get-parameter \
    --name "/a2a/app/performance/agentcore/cognito_provider" \
    --region "$REGION" \
    --query 'Parameter.Value' \
    --output text)

COGNITO_AUTH_SCOPE=$(aws ssm get-parameter \
    --name "/a2a/app/performance/agentcore/cognito_auth_scope" \
    --region "$REGION" \
    --query 'Parameter.Value' \
    --output text)

echo "✅ SSM parameters retrieved"

# Generate JSON config
cat > "$CONFIG_FILE" <<EOF
{
  "agentcore_performance": {
    "runtime_arn": "$RUNTIME_ARN",
    "machine_client_id": "$MACHINE_CLIENT_ID",
    "cognito_discovery_url": "$COGNITO_DISCOVERY_URL",
    "cognito_provider": "$COGNITO_PROVIDER",
    "cognito_auth_scope": "$COGNITO_AUTH_SCOPE"
  }
}
EOF

echo "✅ Configuration file created: $CONFIG_FILE"
echo ""
echo "📋 Configuration:"
cat "$CONFIG_FILE"
