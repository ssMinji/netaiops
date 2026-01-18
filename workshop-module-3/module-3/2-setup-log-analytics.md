# Deployment Steps - Log Analytics

This guide will help you deploy the AgentCore Log Analytics Agent that can analyze AWS Transit Gateway (TGW) traffic logs and provide insights into network traffic patterns and issues.

## Prerequisites
- You have setup troubleshoot connectivity agent
- Make sure you are in test EC2 instance
- You are in stage-4 directory


## Step 1: Navigate to the Log Analytics Agent Directory
Navigate to the log analytics agent directory from the stage-4 folder:

```bash
cd ../agentcore-log-analytics-agent
```

**Note:** If you're starting fresh (not coming from the connectivity agent deployment), use:
```bash
cd agentcore-log-analytics-agent
```

## Step 2: Setup Dependencies
Install all required Python dependencies and tools:

```bash
chmod +x ./scripts/setup-dependencies.sh
./scripts/setup-dependencies.sh
```

**What this does:** This script installs Python virtual environment, required packages, and the AgentCore CLI tools needed for log analytics deployment.

**Expected output:** You should see messages about Python packages being installed and virtual environment being created.

## Step 3: Deploy Infrastructure
Deploy the required AWS infrastructure including Cognito user pools and IAM roles:

```bash
chmod +x ./scripts/prereq.sh
./scripts/prereq.sh
```

**What this does:** Creates Cognito user pools for authentication, IAM roles for the log analytics agent, and sets up necessary AWS permissions for accessing VPC Flow Logs and Transit Gateway logs.

**Expected output:** Confirmation messages about Cognito pools, IAM roles, and log access permissions being created successfully.

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
- Creates authentication providers specifically for the log analytics agent

**Expected output:** Confirmation that the Cognito credentials provider has been created.

## Step 5: Deploy Log Analytics Tool
Deploy the Lambda function that analyzes Transit Gateway traffic logs:

```bash
chmod +x ./prerequisite/lambda-log-analytics/deploy-analyze-tgw-traffic-tool.sh
./prerequisite/lambda-log-analytics/deploy-analyze-tgw-traffic-tool.sh
```

**What this does:** Creates a Lambda function that can:
- Parse VPC Flow Logs and Transit Gateway logs
- Analyze traffic patterns and anomalies
- Identify potential security issues or performance bottlenecks
- Generate insights about network usage

**Expected output:** Confirmation that the TGW traffic analysis tool has been deployed successfully.

## Step 6: Setup Memory Configuration
Configure the agent's memory system for application contact tracking and historical analysis:

### 6a. Create the Memory System
```bash
# Create the memory system for application contact tracking
python3 scripts/setup_memory.py --action create
```

**What this does:** Sets up the memory system that allows the agent to store and recall information about applications, their contacts, and historical traffic patterns.

### 6b. Add Application Contact Information
Add contact information for applications that the agent will monitor:

```bash
# Add application contact information (replace with your actual company emails)
python3 scripts/setup_memory.py --action seed --app Retail-Application --email aksareen@amazon.com
```

# Optiional
```bash
python3 scripts/setup_memory.py --action seed --app Finance-Application --email finance@yourcompany.com
```

**What this does:** Seeds the memory system with application ownership information so the agent knows who to contact when issues are detected with specific applications.

**Important:** Replace the email addresses with actual contact emails for your applications.


### 6c. Verify Memory Setup (Optional)
Verify that the memory system has been properly configured (Give a minute before running below command):

```bash
# Verify seeded memory
python3 scripts/setup_memory.py --action verify
```

**What this does:** Displays all the applications and contacts stored in the memory system to confirm everything was set up correctly.

## Step 7: Create Gateway and Runtime
Create the AgentCore gateway and runtime that will host your log analytics agent:

```bash
python3 scripts/agentcore_gateway.py create --name a2a-log-analytics-gateway
```

```bash
python3 scripts/agentcore_agent_runtime.py create --name a2a_log_analytics_agent_runtime
```

**What this does:** 
- Creates an AgentCore gateway that provides API access to your log analytics agent
- Creates the runtime environment where your log analytics agent will execute
- Configures the agent to access and analyze your AWS network logs

**Expected output:** 
- Confirmation that the gateway has been created with an endpoint URL
- Confirmation that the agent runtime has been deployed successfully
- The agent should now be ready to analyze network traffic logs

## Verification
After completing all steps, you should have:
- ✅ A deployed log analytics agent capable of analyzing network traffic
- ✅ Lambda function for TGW traffic analysis
- ✅ Memory system configured with application contacts
- ✅ An AgentCore gateway providing API access
- ✅ A runtime environment hosting your log analytics agent
