# Setup A2A (Agent-to-Agent Communication)

This guide will help you set up the Agent-to-Agent (A2A) communication system that allows your AgentCore agents to work together and coordinate their activities. The A2A system creates a collaborative environment where agents can share information and coordinate responses.


## Overview
The A2A system consists of:
- **A2A Connectivity Agent**: Runs on ECS and provides connectivity troubleshooting services
- **A2A Log Analytics Agent**: Runs on ECS and provides log analysis services  
- **A2A Collaborator Agent**: Runs on AgentCore and coordinates between the other agents

## Prerequisites
- You have setup troubleshoot connectivity agent
- You have setup log analytics agent
- Make sure you are in test EC2 instance
- You are in stage-4 directory


## Step 1: Navigate to the A2A Directory
Navigate to the A2A directory from the stage-4 folder:

```bash
cd ../a2a
```

**Note:** If you're starting fresh (not coming from the log analytics deployment), use:
```bash
cd a2a
```

## Step 2: Deploy A2A Connectivity Agent
Deploy the connectivity agent as a containerized service on AWS ECS (Give some time for the ECS service deployment status to be updated to `success`):

```bash
cd a2a-connectivity-agent && chmod +x fix-docker-hub-auth.sh && ./fix-docker-hub-auth.sh && chmod +x ./deploy-to-ecs.sh && ./deploy-to-ecs.sh && cd ..
```
```bash
chmod +x ./fix-vpc-endpoint-policy.sh
./fix-vpc-endpoint-policy.sh
```

Create s3 bucket 

aws s3 mb s3://baseline-deploy-237616366264 --region us-east-1


aws s3 cp alb_access_guide.html s3://baseline-deploy-237616366264/module-3/alb_access_guide.html

**What this does:**
1. **fix-docker-hub-auth.sh**: Configures Docker Hub authentication to avoid rate limiting issues
2. **deploy-to-ecs.sh**: 
   - Builds a Docker container with the connectivity agent
   - Pushes the container to Amazon ECR (Elastic Container Registry)
   - Creates an ECS service to run the agent
   - Sets up an Application Load Balancer (ALB) for external access
   - Configures auto-scaling and health checks

**Expected output:**
- Docker build and push confirmation messages
- ECS service creation confirmation
- ALB endpoint URL that other agents can use to communicate with this agent

**Time estimate:** 5-10 minutes for container build and deployment

## Step 3: Deploy A2A Log Analytics Agent
Deploy the log analytics agent as a containerized service on AWS ECS (Give some time for the ECS service deployment status to be updated to `success`):

```bash
cd a2a-log-analytics-agent && chmod +x fix-docker-hub-auth.sh && ./fix-docker-hub-auth.sh && chmod +x ./deploy-to-ecs.sh && ./deploy-to-ecs.sh
```

```bash
chmod +x ./fix-vpc-endpoint-policy.sh
./fix-vpc-endpoint-policy.sh
```

**What this does:**
1. **fix-docker-hub-auth.sh**: Configures Docker Hub authentication
2. **deploy-to-ecs.sh**: 
   - Builds a Docker container with the log analytics agent
   - Pushes the container to Amazon ECR
   - Creates an ECS service to run the agent
   - Sets up an Application Load Balancer for external access
   - Configures the agent to work with the connectivity agent

**Expected output:**
- Docker build and push confirmation messages
- ECS service creation confirmation
- ALB endpoint URL for the log analytics agent

**Time estimate:** 5-10 minutes for container build and deployment

## Step 4: Verify ALB Status and Test Agent Endpoints
Before creating the collaborator agent runtime, verify that both ALB endpoints are accessible and the agents are responding correctly:

```bash
python3 update_alb_status.py
```

**What this does:**
- Updates the ALB status and retrieves current endpoint information
- Generates an updated access guide with the latest ALB DNS names
- Verifies that both ECS services are healthy and responding

Next, upload the ALB access guide to S3 so you can download it to your local machine and test the endpoints in your browser:

```bash
# Upload the ALB access guide to S3 bucket (replace {aws-account} with your AWS account number)
aws s3 cp alb_access_guide.html s3://baseline-deploy-{aws-account}/stage-4/alb_access_guide.html
```

**Testing the endpoints:**
1. Download the HTML file from S3 to your local machine:
   - Navigate to the S3 bucket `s3://baseline-deploy-{aws-account}/stage-4/` in the AWS Console
   - Download the `alb_access_guide.html` file to your local computer
   - Or use AWS CLI if configured locally: `aws s3 cp s3://baseline-deploy-{aws-account}/stage-4/alb_access_guide.html ~/alb_access_guide.html`

2. Open the downloaded HTML file in your browser:
   - Double-click the downloaded file, or
   - Right-click and select "Open with" your preferred browser
   
2. **Test Health Endpoints**: Click on "Test Health Endpoint" for both:
   - Connectivity Troubleshooting Agent
   - Log Analytics Agent
   
   Verify that both endpoints return a successful health check response.

3. **Test Agent Cards**: Click on "View Agent Card" for both agents to confirm:
   - Connectivity Troubleshooting Agent card loads properly
   - Log Analytics Agent card loads properly
   
   The agent cards should display JSON configuration showing the agent capabilities and endpoints.

**Expected results:**
- ✅ Both health endpoints return HTTP 200 status
- ✅ Both agent cards load and display valid JSON configuration
- ✅ No connectivity errors or timeouts

**Troubleshooting:** If any endpoints fail to respond:
- Wait 2-3 minutes for ECS services to fully initialize
- Check AWS ECS console to ensure both services are running
- Verify security groups allow inbound traffic on the required ports

## Step 5: Create A2A Collaborator Agent Runtime
Create the AgentCore runtime that will coordinate between the ECS-based agents:

```bash
cd a2a-collaborator-agent
```

```bash
python3 ./scripts/agentcore_agent_runtime.py create --name a2a_collaborator_agent_runtime
```

**What this does:**
- Creates an AgentCore runtime for the collaborator agent
- Configures the agent to communicate with both ECS-based agents
- Sets up OAuth authentication for secure agent-to-agent communication
- Updates configuration files with the ALB endpoints from the previous steps

**Expected output:**
- Configuration update messages showing ALB DNS values being retrieved
- AgentCore runtime creation confirmation
- Runtime ID that you'll use for testing

**Important:** Save the runtime ID from the output - you'll need it for testing!

## Step 6: Test A2A System
Test the complete A2A system to ensure all agents can communicate properly:

Navigate to Bedrock AgentCore service in AWS Console and get the Collaborator Agent Runtime Id and replace {agentcore-runtime-id}. Replace {aws-account-id} with your AWS account
```bash
python3 test_a2a_collaborator_agent.py --aws-account-id {aws-account-id} --agentcore-runtime-id {agentcore-runtime-id}
```

**What this does:**
- Tests authentication between all agents
- Verifies that the collaborator agent can reach both ECS agents
- Sends sample requests through the A2A communication channels
- Validates that responses are properly coordinated

**Expected output:**
- Authentication success messages
- Communication test results between agents
- Sample coordination workflow demonstration

## Verification
After completing all steps, you should have:
- ✅ A2A Connectivity Agent running on ECS with ALB endpoint
- ✅ A2A Log Analytics Agent running on ECS with ALB endpoint  
- ✅ A2A Collaborator Agent runtime deployed on AgentCore
- ✅ Successful test results showing agent-to-agent communication

## Understanding the A2A Architecture

### Communication Flow
1. **User Request** → Collaborator Agent (AgentCore)
2. **Collaborator Agent** → Connectivity Agent (ECS) for network issues
3. **Collaborator Agent** → Log Analytics Agent (ECS) for traffic analysis
4. **Agents coordinate** to provide comprehensive responses
5. **Collaborator Agent** → User with coordinated response

### Agent Responsibilities
- **Connectivity Agent**: Diagnoses and fixes network connectivity issues
- **Log Analytics Agent**: Analyzes traffic patterns and identifies anomalies
- **Collaborator Agent**: Coordinates requests, combines insights, and manages workflows
