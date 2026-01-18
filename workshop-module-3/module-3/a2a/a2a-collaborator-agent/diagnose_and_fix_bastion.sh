#!/bin/bash
# Comprehensive diagnostic and fix script for bastion authentication issue

set -e

echo "=== A2A Collaborator Agent - Bastion Authentication Diagnostic ==="
echo ""

# AWS credentials should be set via environment variables or AWS CLI configuration
# Do NOT hardcode credentials here
# export AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY_ID"
# export AWS_SECRET_ACCESS_KEY="YOUR_SECRET_ACCESS_KEY"
# export AWS_SESSION_TOKEN="YOUR_SESSION_TOKEN"
#
# Use one of these methods instead:
# 1. aws configure
# 2. Export environment variables before running this script
# 3. Use IAM roles for EC2 instances

echo "Step 1: Checking AWS Identity"
aws sts get-caller-identity

echo ""
echo "Step 2: Checking Python environment"
python3 --version
pip3 list | grep -i bedrock

echo ""
echo "Step 3: Checking for existing .agentcore.json"
if [ -f ".agentcore.json" ]; then
    echo "Found .agentcore.json - removing it to force fresh authentication"
    rm -f .agentcore.json
else
    echo "No .agentcore.json found"
fi

echo ""
echo "Step 4: Testing bedrock-agentcore API access"
python3 << 'PYEOF'
import boto3
import json

try:
    client = boto3.client('bedrock-agentcore', region_name='us-east-1')
    print("✓ bedrock-agentcore client created")
    
    # Try to create a workload identity
    try:
        response = client.create_workload_identity()
        print(f"✓ CreateWorkloadIdentity succeeded: {response['workloadIdentityId']}")
        
        # Clean up
        try:
            client.delete_workload_identity(workloadIdentityId=response['workloadIdentityId'])
            print(f"✓ Cleaned up test workload identity")
        except:
            pass
            
    except Exception as e:
        print(f"✗ CreateWorkloadIdentity failed: {e}")
        print(f"   This indicates IAM permission issues")
        
except Exception as e:
    print(f"✗ Failed to create bedrock-agentcore client: {e}")
PYEOF

echo ""
echo "Step 5: Running the test"
echo "========================================"
python3 test_a2a_collaborator_agent.py --aws-account-id 211351096897 --agentcore-runtime-id a2a_collaborator_agent_runtime-zF6jNyFmyU

echo ""
echo "========================================"
echo "Diagnostic complete"
