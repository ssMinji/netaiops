#!/bin/bash

# Deploy EKS MCP Server as AgentCore Runtime
# Uses official awslabs.eks-mcp-server with Streamable HTTP transport
# Configures JWT authorizer using Runtime Cognito for Gateway→Runtime auth

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo -e "${BLUE}Deploying EKS MCP Server as AgentCore Runtime${NC}"
echo -e "${BLUE}Region: $REGION | Account: $ACCOUNT_ID${NC}"
echo "=================================================="

# Step 1: Read Runtime Cognito details from SSM
echo -e "${BLUE}Reading Runtime Cognito configuration from SSM...${NC}"

EKS_MCP_POOL_ID=$(aws ssm get-parameter \
    --name "/a2a/app/k8s/agentcore/eks_mcp_pool_id" \
    --query "Parameter.Value" --output text \
    --region "$REGION" 2>/dev/null || echo "")

EKS_MCP_CLIENT_ID=$(aws ssm get-parameter \
    --name "/a2a/app/k8s/agentcore/eks_mcp_client_id" \
    --query "Parameter.Value" --output text \
    --region "$REGION" 2>/dev/null || echo "")

EKS_MCP_DISCOVERY_URL=$(aws ssm get-parameter \
    --name "/a2a/app/k8s/agentcore/eks_mcp_discovery_url" \
    --query "Parameter.Value" --output text \
    --region "$REGION" 2>/dev/null || echo "")

if [ -z "$EKS_MCP_POOL_ID" ] || [ -z "$EKS_MCP_CLIENT_ID" ] || [ -z "$EKS_MCP_DISCOVERY_URL" ]; then
    echo -e "${RED}ERROR: Runtime Cognito SSM parameters not found.${NC}"
    echo "Deploy the CloudFormation stack first (Step 1 in DEPLOY_GUIDE.md)"
    exit 1
fi

echo -e "${GREEN}Runtime Cognito Pool: $EKS_MCP_POOL_ID${NC}"
echo -e "${GREEN}Runtime Client ID: $EKS_MCP_CLIENT_ID${NC}"
echo -e "${GREEN}Discovery URL: $EKS_MCP_DISCOVERY_URL${NC}"

# Step 2: Configure JWT authorizer in .bedrock_agentcore.yaml
echo -e "${BLUE}Configuring JWT authorizer...${NC}"

cd "$SCRIPT_DIR"

# Use Python to update the YAML with authorizer configuration
python3 -c "
import yaml

with open('.bedrock_agentcore.yaml', 'r') as f:
    config = yaml.safe_load(f)

agent = config['agents']['eks_mcp_server_runtime']
agent['authorizer_configuration'] = {
    'customJWTAuthorizer': {
        'allowedClients': ['${EKS_MCP_CLIENT_ID}'],
        'discoveryUrl': '${EKS_MCP_DISCOVERY_URL}'
    }
}

with open('.bedrock_agentcore.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

print('JWT authorizer configured successfully')
"

echo -e "${GREEN}Authorizer configured in .bedrock_agentcore.yaml${NC}"

# Step 3: Check if agentcore CLI is available
if ! command -v agentcore &> /dev/null; then
    echo -e "${YELLOW}agentcore CLI not found, checking alternatives...${NC}"
    if command -v bedrock-agentcore &> /dev/null; then
        AGENTCORE_CMD="bedrock-agentcore"
    else
        echo -e "${RED}No agentcore CLI found. Install: pip install bedrock-agentcore-starter-toolkit${NC}"
        exit 1
    fi
else
    AGENTCORE_CMD="agentcore"
fi

# Step 4: Deploy via AgentCore CLI
echo -e "${BLUE}Deploying eks-mcp-server runtime...${NC}"
$AGENTCORE_CMD deploy

echo ""

# Step 5: Get the runtime ARN from the updated YAML
echo -e "${BLUE}Retrieving runtime ARN...${NC}"

RUNTIME_ARN=$(python3 -c "
import yaml
with open('.bedrock_agentcore.yaml', 'r') as f:
    config = yaml.safe_load(f)
arn = config['agents']['eks_mcp_server_runtime']['bedrock_agentcore'].get('agent_arn', '')
print(arn or '')
")

if [ -n "$RUNTIME_ARN" ] && [ "$RUNTIME_ARN" != "None" ] && [ "$RUNTIME_ARN" != "" ]; then
    echo -e "${GREEN}Runtime ARN: $RUNTIME_ARN${NC}"

    # Save ARN to SSM
    aws ssm put-parameter \
        --name "/a2a/app/k8s/agentcore/eks_mcp_server_arn" \
        --value "$RUNTIME_ARN" \
        --type String \
        --overwrite \
        --region "$REGION"

    echo -e "${GREEN}Saved ARN to SSM: /a2a/app/k8s/agentcore/eks_mcp_server_arn${NC}"
else
    echo -e "${YELLOW}Could not find runtime ARN in YAML.${NC}"

    # Try from API
    RUNTIME_ARN=$(python3 -c "
import boto3
client = boto3.client('bedrock-agentcore-control', region_name='${REGION}')
runtimes = client.list_agent_runtimes()
for r in runtimes.get('items', []):
    if 'eks_mcp_server' in r.get('agentRuntimeName', ''):
        print(r['agentRuntimeArn'])
        break
" 2>/dev/null || echo "")

    if [ -n "$RUNTIME_ARN" ]; then
        echo -e "${GREEN}Runtime ARN (from API): $RUNTIME_ARN${NC}"
        aws ssm put-parameter \
            --name "/a2a/app/k8s/agentcore/eks_mcp_server_arn" \
            --value "$RUNTIME_ARN" \
            --type String \
            --overwrite \
            --region "$REGION"
    else
        echo -e "${YELLOW}Runtime not found. Check: agentcore status${NC}"
    fi
fi

echo ""
echo -e "${GREEN}EKS MCP Server deployment complete.${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "   1. Verify runtime status: cd $SCRIPT_DIR && agentcore status"
echo "   2. Create gateway: cd $PROJECT_DIR/scripts && python3 agentcore_gateway.py create --name k8s-gateway"
echo ""
