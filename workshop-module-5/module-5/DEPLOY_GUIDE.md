# Module 5 Deploy Guide - Fresh AWS Account

This guide deploys the K8s Diagnostics Agent on a **new AWS account** with no existing NetAIOps infrastructure.

## Prerequisites

| Requirement | Check |
|-------------|-------|
| AWS CLI v2 | `aws --version` |
| Python 3.10+ | `python3 --version` |
| Docker | `docker --version` |
| AWS Profile configured | `aws sts get-caller-identity --profile <PROFILE>` |
| Bedrock model access | Claude Opus 4.6 enabled in target region |

## Architecture

```
Cognito (OAuth2) ──────────────────────────────────────┐
                                                       │ auth
IAM Role (EKS + AgentCore + CW permissions)            │
                                                       v
[test_agent.py] ──PKCE──> K8s Agent Runtime ──MCP──> Gateway ──mcpServer──> eks-mcp-server Runtime
                              │                                                    │
                              │ Claude Opus 4.6                                    │ boto3
                              │ + Memory                                           v
                              v                                              EKS / CloudWatch / IAM
                          SSM Parameters
```

## Deployment Steps

### Step 0: Set Environment

```bash
export AWS_PROFILE=netaiops-deploy
export AWS_DEFAULT_REGION=us-east-1

# Verify
aws sts get-caller-identity
```

---

### Step 1: Deploy Cognito + IAM + SSM (CloudFormation)

This single stack creates everything the agent needs: Cognito User Pool, OAuth2 clients, IAM execution role with EKS permissions, and all SSM parameters.

```bash
cd workshop-module-5/module-5/agentcore-k8s-agent

aws cloudformation deploy \
    --template-file prerequisite/k8s-agentcore-cognito.yaml \
    --stack-name k8s-agentcore-cognito \
    --capabilities CAPABILITY_NAMED_IAM \
    --region us-east-1
```

**Wait for completion (~2-3 min):**
```bash
aws cloudformation wait stack-create-complete \
    --stack-name k8s-agentcore-cognito \
    --region us-east-1
```

**Verify SSM parameters were created:**
```bash
aws ssm get-parameters-by-path \
    --path "/a2a/app/k8s/agentcore" \
    --recursive \
    --query "Parameters[].Name" \
    --region us-east-1
```

Expected output: 11 parameters including `machine_client_id`, `gateway_iam_role`, `cognito_token_url`, etc.

---

### Step 2: Create Cognito Test User

```bash
# Get the User Pool ID
USER_POOL_ID=$(aws ssm get-parameter \
    --name "/a2a/app/k8s/agentcore/userpool_id" \
    --query "Parameter.Value" --output text \
    --region us-east-1)

# Create a test user
aws cognito-idp admin-create-user \
    --user-pool-id $USER_POOL_ID \
    --username testuser@example.com \
    --user-attributes Name=email,Value=testuser@example.com Name=email_verified,Value=true \
    --temporary-password "TempPass1!" \
    --region us-east-1

# Set permanent password
aws cognito-idp admin-set-user-password \
    --user-pool-id $USER_POOL_ID \
    --username testuser@example.com \
    --password "TestPass123!" \
    --permanent \
    --region us-east-1
```

---

### Step 3: Setup Python Dependencies

```bash
cd workshop-module-5/module-5/agentcore-k8s-agent

chmod +x ./scripts/setup-dependencies.sh
./scripts/setup-dependencies.sh
```

---

### Step 4: Deploy EKS MCP Server

```bash
chmod +x ./prerequisite/eks-mcp-server/deploy-eks-mcp-server.sh
./prerequisite/eks-mcp-server/deploy-eks-mcp-server.sh
```

This deploys the official `awslabs.eks-mcp-server` as an AgentCore Runtime with Streamable HTTP transport. The endpoint URL is saved to SSM at `/a2a/app/k8s/agentcore/eks_mcp_server_endpoint`.

**If `bedrock-agentcore deploy` is not available**, deploy manually:
```bash
cd prerequisite/eks-mcp-server
source ../../.venv/bin/activate
bedrock-agentcore deploy
cd ../..
```

---

### Step 5: Create MCP Gateway

```bash
source .venv/bin/activate
cd scripts
python3 agentcore_gateway.py create --name k8s-gateway
cd ..
```

This creates the Gateway with a `mcpServer` target pointing to the eks-mcp-server endpoint. The Gateway URL is saved to SSM at `/a2a/app/k8s/agentcore/gateway_url`.

---

### Step 6: Setup Agent Memory

```bash
source .venv/bin/activate

# Create OAuth2 credential provider for the agent
python3 scripts/cognito_credentials_provider.py create-provider

# Setup memory
python3 scripts/setup_memory.py
```

> **Note:** If `cognito_credentials_provider.py` or `setup_memory.py` don't exist yet, the memory and OAuth provider will be auto-created on first `bedrock-agentcore deploy`.

---

### Step 7: Deploy K8s Agent Runtime

```bash
source .venv/bin/activate
bedrock-agentcore deploy
```

This builds the Docker container, pushes to ECR, and deploys the K8s Agent as a managed AgentCore Runtime.

---

### Step 8: Launch Chat UI

```bash
cd ../k8s-chat-frontend
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501` in your browser. The app automatically:
- Discovers the agent ARN from `.bedrock_agentcore.yaml`
- Acquires a JWT token via M2M `client_credentials` flow
- No region selector needed — the agent dynamically switches AWS regions based on your queries

**Example queries:**
```
Check the Virginia region EKS clusters
List all pods in the default namespace
Show me CloudWatch metrics for my Oregon cluster
Search the troubleshooting guide for CrashLoopBackOff
```

**Alternative: CLI test (PKCE auth)**
```bash
cd ../agentcore-k8s-agent
source .venv/bin/activate
python3 test/test_agent.py a2a_k8s_agent_runtime --interactive
```

---

## Verification Checklist

```bash
# 1. CloudFormation stack
aws cloudformation describe-stacks \
    --stack-name k8s-agentcore-cognito \
    --query "Stacks[0].StackStatus" \
    --region us-east-1

# 2. SSM parameters (should be 11+)
aws ssm get-parameters-by-path \
    --path "/a2a/app/k8s/agentcore" \
    --recursive --query "Parameters[].Name" \
    --region us-east-1

# 3. Gateway status
GATEWAY_ID=$(aws ssm get-parameter \
    --name "/a2a/app/k8s/agentcore/gateway_id" \
    --query "Parameter.Value" --output text \
    --region us-east-1)
aws bedrock-agentcore-control get-gateway \
    --gateway-identifier $GATEWAY_ID \
    --query "status" \
    --region us-east-1

# 4. Agent runtime status
bedrock-agentcore status
```

---

## Cleanup

```bash
# 1. Delete agent runtime
bedrock-agentcore destroy

# 2. Delete gateway
source .venv/bin/activate
cd scripts
python3 agentcore_gateway.py delete --confirm
cd ..

# 3. Delete CloudFormation stack (Cognito + IAM + SSM)
aws cloudformation delete-stack \
    --stack-name k8s-agentcore-cognito \
    --region us-east-1
```

---

## Troubleshooting

### "bedrock-agentcore: command not found"
```bash
source .venv/bin/activate
pip install bedrock-agentcore bedrock-agentcore-starter-toolkit
```

### "Model access denied"
Request model access in Bedrock console:
- Go to Amazon Bedrock > Model access > Request access
- Enable Claude Opus 4.6 (or the model specified in `.bedrock_agentcore.yaml`)

### "EKS cluster not found"
The agent needs an actual EKS cluster to diagnose. If you don't have one, the eks-mcp-server's `manage_eks_stacks` tool can create one, or you can create one manually:
```bash
eksctl create cluster --name sample-eks-cluster --region us-east-1 --nodes 2
```

### SSM parameter not found
Verify the CloudFormation stack completed:
```bash
aws cloudformation describe-stacks --stack-name k8s-agentcore-cognito --region us-east-1
```
If the stack failed, check events:
```bash
aws cloudformation describe-stack-events --stack-name k8s-agentcore-cognito --region us-east-1 \
    --query "StackEvents[?ResourceStatus=='CREATE_FAILED'].[LogicalResourceId,ResourceStatusReason]"
```
