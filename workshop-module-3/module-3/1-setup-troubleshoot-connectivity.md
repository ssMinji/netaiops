# Deployment Steps - Troubleshoot Connectivity

This guide will help you deploy the AgentCore Connectivity Agent that can troubleshoot network connectivity issues in your AWS environment.

## Step 1: Connect to EC2 Instance
Navigate to the EC2 console and select Baseline Instance on the left pane. Click Connect. Select Session Manager tab and click Connect.

## Step 2: Switch to Root User and Navigate to Directory
Switch to root user and navigate to the agent-based-cloudops stage-4 directory:

```bash
sudo su
```

```bash
cd ../../agent-based-cloudops/
mkdir stage-4
```

## Step 3: Download and Extract Assets
Download the required assets and extract them:

```bash
# Download the asset  
curl https://ws-assets-prod-iad-r-iad-ed304a55c2ca1aee.s3.us-east-1.amazonaws.com/d22e17c5-15e8-4aca-9e38-96453f5be673/agent-based-cloudops/stage-1.zip --output stage-4.zip

# Unzip the zip file
unzip -j stage-4.zip
```

## Step 4: Navigate to the Connectivity Agent Directory
First, navigate to the connectivity agent directory from the stage-4 folder:

```bash
cd agentcore-connectivity-agent
```

## Step 5: Setup Dependencies
Install all required Python dependencies and tools:

```bash
chmod +x scripts/setup-dependencies.sh
./scripts/setup-dependencies.sh
```

**What this does:** This script installs Python virtual environment, required packages, and the AgentCore CLI tools needed for deployment.

## Step 6: Deploy Infrastructure
Deploy the required AWS infrastructure including Cognito user pools and IAM roles:

```bash
chmod +x scripts/prereq.sh
./scripts/prereq.sh
```

**What this does:** Creates Cognito user pools for authentication, IAM roles for the agent, and sets up necessary AWS permissions.

**Expected output:** You should see confirmation messages about Cognito pools and IAM roles being created successfully.

## Step 7: Activate Virtual Environment and Setup Authentication
Activate the Python virtual environment and configure authentication:

```bash
source .venv/bin/activate
```

```bash
python3 scripts/cognito_credentials_provider.py create-provider
```

```bash
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
```

**What this does:** 
- Activates the Python virtual environment
- Creates authentication providers for the agent
- Logs into AWS ECR to pull Docker images

## Step 8: Deploy DNS Resolution Tool
Deploy the Lambda function that handles DNS resolution for connectivity troubleshooting:

```bash
chmod +x prerequisite/lambda-dns/deploy-dns-tool.sh
cd prerequisite/lambda-dns && ./deploy-dns-tool.sh && cd ../..
```

**What this does:** Creates a Lambda function that can resolve DNS queries and check DNS connectivity issues.

**Expected output:** Confirmation that the DNS tool Lambda function has been deployed successfully.

## Step 9: Deploy Connectivity Analysis Tool
Deploy the Lambda function that analyzes network connectivity:

```bash
chmod +x prerequisite/lambda-check/deploy-check-tool.sh 
cd prerequisite/lambda-check && ./deploy-check-tool.sh && cd ../..
```

**What this does:** Creates a Lambda function that can check network connectivity between resources and diagnose connection issues.

**Expected output:** Confirmation that the connectivity check tool has been deployed.

## Step 10: Deploy Connectivity Fix Tool
Deploy the Lambda function that can automatically fix common connectivity issues:

```bash
chmod +x prerequisite/lambda-fix/deploy-connectivity-fix-tool.sh 
cd prerequisite/lambda-fix && ./deploy-connectivity-fix-tool.sh && cd ../..
```

**What this does:** Creates a Lambda function that can automatically remediate common network connectivity problems.

**Expected output:** Confirmation that the connectivity fix tool has been deployed.

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

**What this does:** 
- Creates an AgentCore gateway that provides API access to your agent
- Creates the runtime environment where your connectivity agent will execute

**Expected output:** 
- Confirmation that the gateway has been created with an endpoint URL
- Confirmation that the agent runtime has been deployed successfully

## Verification
After completing all steps, you should have:
- ✅ A deployed connectivity troubleshooting agent
- ✅ Lambda functions for DNS resolution, connectivity checking, and automatic fixes
- ✅ An AgentCore gateway providing API access
- ✅ A runtime environment hosting your agent
