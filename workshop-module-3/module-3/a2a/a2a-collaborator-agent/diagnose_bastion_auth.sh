#!/bin/bash
# Diagnostic script to check authentication setup on bastion

echo "=== Checking AWS Credentials ==="
aws sts get-caller-identity

echo -e "\n=== Checking IAM Role Permissions ==="
ROLE_NAME=$(aws sts get-caller-identity --query 'Arn' --output text | grep -oP 'assumed-role/\K[^/]+')
echo "Role Name: $ROLE_NAME"

if [ -n "$ROLE_NAME" ]; then
    echo -e "\nChecking inline policies..."
    aws iam list-role-policies --role-name "$ROLE_NAME" 2>/dev/null || echo "Could not list inline policies"
    
    echo -e "\nChecking attached policies..."
    aws iam list-attached-role-policies --role-name "$ROLE_NAME" 2>/dev/null || echo "Could not list attached policies"
fi

echo -e "\n=== Checking SSM Parameters ==="
aws ssm get-parameter --name "/a2a/app/performance/agentcore/cognito_provider" --query 'Parameter.Value' --output text 2>/dev/null || echo "Could not read cognito_provider parameter"

echo -e "\n=== Checking Resource Credential Provider ==="
PROVIDER_NAME=$(aws ssm get-parameter --name "/a2a/app/performance/agentcore/cognito_provider" --query 'Parameter.Value' --output text 2>/dev/null)
if [ -n "$PROVIDER_NAME" ]; then
    echo "Provider Name: $PROVIDER_NAME"
    PROVIDER_ARN="arn:aws:bedrock-agentcore:us-east-1:211351096897:token-vault/default/oauth2credentialprovider/$PROVIDER_NAME"
    echo "Provider ARN: $PROVIDER_ARN"
    
    echo -e "\nTrying to describe the provider..."
    aws bedrock-agentcore get-resource-oauth2-credential-provider --resource-arn "$PROVIDER_ARN" 2>&1 || echo "Could not describe provider"
fi

echo -e "\n=== Checking Python Environment ==="
python3 --version
pip3 list | grep -i bedrock || echo "No bedrock packages found"

echo -e "\n=== Checking for .agentcore.json ==="
if [ -f ".agentcore.json" ]; then
    echo "Found .agentcore.json:"
    cat .agentcore.json
else
    echo "No .agentcore.json file found"
fi

echo -e "\n=== Testing bedrock-agentcore API Access ==="
python3 << 'PYEOF'
import boto3
import json

try:
    client = boto3.client('bedrock-agentcore', region_name='us-east-1')
    print("✓ bedrock-agentcore client created successfully")
    
    # Try to create a workload identity
    try:
        response = client.create_workload_identity()
        print(f"✓ CreateWorkloadIdentity succeeded: {response['workloadIdentityId']}")
    except Exception as e:
        print(f"✗ CreateWorkloadIdentity failed: {e}")
        
except Exception as e:
    print(f"✗ Failed to create bedrock-agentcore client: {e}")
PYEOF

