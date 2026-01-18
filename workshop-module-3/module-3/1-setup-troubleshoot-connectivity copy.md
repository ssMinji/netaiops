# Deployment Steps - Troubleshoot Connectivity

## Step 1: Switch to Root User and Navigate to Directory
Switch to root user and navigate to the agent-based-cloudops stage-4 directory:

```bash
sudo su - 
```

## Step 2: Navigate to the Connectivity Agent Directory
First, navigate to the connectivity agent directory from the workshop-module-3 folder:

```bash
cd agentcore-connectivity-agent
```

## Step 3: Setup Dependencies
Install all required Python dependencies and tools:

```bash
chmod +x scripts/setup-dependencies.sh
./scripts/setup-dependencies.sh
```


## Step 4: Activate Virtual Environment and Setup Authentication
Activate the Python virtual environment and configure authentication:

```bash
source .venv/bin/activate
```

```bash
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
```

## Step 5: Deploy DNS Resolution Tool
Deploy the Lambda function that handles DNS resolution for connectivity troubleshooting:

```bash
chmod +x prerequisite/lambda-dns/deploy-dns-tool.sh
cd prerequisite/lambda-dns && ./deploy-dns-tool.sh && cd ../..
```


## Step 9: Deploy Connectivity Analysis Tool
Deploy the Lambda function that analyzes network connectivity:

```bash
chmod +x prerequisite/lambda-check/deploy-check-tool.sh 
cd prerequisite/lambda-check && ./deploy-check-tool.sh && cd ../..
```


## Step 10: Deploy Connectivity Fix Tool
Deploy the Lambda function that can automatically fix common connectivity issues:

```bash
chmod +x prerequisite/lambda-fix/deploy-connectivity-fix-tool.sh 
cd prerequisite/lambda-fix && ./deploy-connectivity-fix-tool.sh && cd ../..
```


## Step 11: Setup Memory Configuration
Configure the agent's memory system for storing troubleshooting context:

```bash
chmod +x scripts/setup_memory.py && python3 scripts/setup_memory.py
```

**What this does:** Sets up the memory system that allows the agent to remember previous troubleshooting sessions and learn from past issues.

## Step 12: Create Gateway and Runtime
Create the AgentCore gateway and runtime that will host your connectivity agent:

```bash
python3 scripts/agentcore_gateway.py create --name a2a-troubleshooting-gateway
```

```bash
python3 scripts/agentcore_agent_runtime.py create --name a2a_troubleshooting_agent_runtime
```
