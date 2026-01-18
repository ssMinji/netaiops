# Deployment Steps - Performance Agent

This guide will help you deploy the AgentCore Performance Agent that provides comprehensive network performance analysis, monitoring, and troubleshooting capabilities.

## Prerequisites
- You have setup troubleshoot connectivity agent and log analytics agent
- Make sure you are in test EC2 instance
- You are in stage-4 directory

## Step 0: Setup AWS credentials
```bash
ada cred update --account=104398007905 --provider=isengard --role=Admin --profile=default --once
```

## Step 1: Navigate to the Performance Agent Directory
Navigate to the performance agent directory from the stage-4 folder:

```bash
cd ../agentcore-performance-agent
```

**Note:** If you're starting fresh (not coming from the log analytics agent deployment), use:
```bash
cd agentcore-performance-agent
```

## Step 2: Setup Dependencies
Install all required Python dependencies and tools:

```bash
chmod +x ./scripts/setup-dependencies.sh
./scripts/setup-dependencies.sh
```

**What this does:** This script installs Python virtual environment, required packages, and the AgentCore CLI tools needed for performance monitoring deployment.

**Expected output:** You should see messages about Python packages being installed and virtual environment being created.

## Step 3: Deploy Infrastructure
Deploy the required AWS infrastructure including Cognito user pools and IAM roles:

```bash
chmod +x ./scripts/prereq.sh
./scripts/prereq.sh
```

**What this does:** Creates Cognito user pools for authentication, IAM roles for the performance agent, and sets up necessary AWS permissions for accessing VPC Flow Logs, CloudWatch metrics, EC2 instances, and traffic mirroring capabilities.

**Expected output:** Confirmation messages about Cognito pools, IAM roles, and performance monitoring permissions being created successfully.

## Step 4: Activate Virtual Environment and Setup Authentication
Activate the Python virtual environment and configure authentication:

```bash
source .venv/bin/activate
```

```bash
python3 scripts/cognito_credentials_provider.py create-provider
```

**What this does:** 
- Activates the Python virtual environment for this agent
- Creates authentication providers specifically for the performance agent

**Expected output:** Confirmation that the Cognito credentials provider has been created.

## Step 5: Deploy Performance Tools
Deploy the Lambda function that provides comprehensive network performance analysis:

```bash
chmod +x ./prerequisite/lambda-performance/deploy-performance-tools.sh
./prerequisite/lambda-performance/deploy-performance-tools.sh
```


## Step 6: Setup Memory Configuration
Configure the agent's memory system for application performance tracking and historical analysis:

```bash
# Create the memory system for application performance tracking
python3 scripts/setup_memory.py --action create
```

## Step 7: Create Gateway and Runtime
Create the AgentCore gateway and runtime that will host your performance agent:

```bash
python3 scripts/agentcore_gateway.py create --name a2a-performance-gateway
```

```bash
python3 scripts/agentcore_agent_runtime.py create --name a2a_performance_agent_runtime
```

## Testing Your Performance Agent

python3 test/test_agent_m2m.py a2a_performance_agent_runtime --prompt "Hello" --interactive

python3 test/test_agent.py a2a_performance_agent_runtime --prompt "Hello" --interactive
