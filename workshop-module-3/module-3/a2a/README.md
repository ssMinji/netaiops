# A2A Local Agent Deployment

This directory contains the complete A2A (Agent-to-Agent) deployment solution for AgentCore runtime, including both the **Host Agent** and **Log Analytics Agent** with comprehensive deployment automation.

## 🏗️ Architecture Overview

The A2A system consists of two main components that work together:

### 1. **Log Analytics Agent** (`log-analytics-agent/`)
- **Type**: A2A Server wrapped in AgentCore runtime
- **Purpose**: Provides specialized Transit Gateway traffic analysis capabilities
- **Deployment**: Creates an AgentCore runtime that runs the A2A server internally
- **Port**: Originally runs on localhost:10005 (when deployed as AgentCore, this is internal)

### 2. **Host Agent** (`host/`)
- **Type**: Pure AgentCore runtime
- **Purpose**: Orchestrates requests and coordinates with remote agents
- **Deployment**: Direct AgentCore runtime deployment
- **Communication**: Connects to other agents via A2A protocol

## 🚀 Quick Start - Deploy Both Agents

### Prerequisites
1. **Deploy main infrastructure first**:
   ```bash
   cd ../../agentcore-log-analytics
   ./scripts/prereq.sh
   ```

2. **Install dependencies**:
   ```bash
   pip install bedrock-agentcore click boto3
   ```

### One-Command Deployment
```bash
# Deploy both agents with default names
python3 deploy_a2a_agents.py deploy-all

# Deploy with custom names
python3 deploy_a2a_agents.py deploy-all --log-analytics-name my_log_agent --host-name my_host_agent
```

This will:
1. ✅ Check prerequisites
2. 📊 Deploy Log Analytics Agent as AgentCore runtime
3. 🏠 Deploy Host Agent as AgentCore runtime  
4. 🔍 Verify both deployments
5. 📋 Provide testing instructions

## 📋 Individual Agent Deployment

### Deploy Only Log Analytics Agent
```bash
python3 deploy_a2a_agents.py deploy-log-analytics --log-analytics-name a2a_log_analytics_agent
```

### Deploy Only Host Agent
```bash
python3 deploy_a2a_agents.py deploy-host --host-name a2a_host_agent
```

## 🔧 Manual Deployment (Advanced)

### Log Analytics Agent
```bash
cd log-analytics-agent
python3 agentcore_log_analytics_runtime.py create --name a2a_log_analytics_agent
```

### Host Agent
```bash
cd host
python3 agentcore_host_runtime.py create --name a2a_host_agent
```

## 🧪 Testing Deployed Agents

### Test Log Analytics Agent
```bash
cd host
python3 test_deployment.py test a2a_log_analytics_agent --prompt "Analyze Transit Gateway traffic for Retail-Application"
```

### Test Host Agent
```bash
cd host
python3 test_deployment.py test a2a_host_agent --prompt "Hello, coordinate with log analytics"
```

### Interactive Testing
```bash
cd host
python3 test_deployment.py test a2a_host_agent --interactive
```

## 📊 Management Commands

### List All Deployed Agents
```bash
python3 deploy_a2a_agents.py list-agents
```

### Delete Agents
```bash
# Delete specific agents
python3 deploy_a2a_agents.py delete-agents a2a_log_analytics_agent a2a_host_agent

# Dry run (preview only)
python3 deploy_a2a_agents.py delete-agents a2a_log_analytics_agent --dry-run
```

## 📁 Directory Structure

```
a2a_local/
├── deploy_a2a_agents.py              # 🎯 Main deployment orchestrator
├── requirements.txt                  # 📦 Common dependencies
├── README.md                         # 📖 This documentation
├── host/                             # 🏠 Host Agent (AgentCore runtime)
│   ├── agentcore_host_runtime.py     # 🚀 Host agent deployment script
│   ├── test_deployment.py            # 🧪 Testing utilities
│   ├── requirements.txt              # 📦 Host-specific dependencies
│   ├── DEPLOYMENT_GUIDE.md           # 📋 Detailed deployment guide
│   ├── main.py                       # 🎯 AgentCore entrypoint
│   ├── agent.py                      # 🤖 Host agent implementation
│   └── ... (other host agent files)
└── log-analytics-agent/              # 📊 Log Analytics Agent (A2A + AgentCore)
    ├── agentcore_log_analytics_runtime.py  # 🚀 Log analytics deployment script
    ├── main_agentcore.py              # 🎯 AgentCore wrapper (auto-generated)
    ├── __main__.py                    # 🌐 A2A server implementation
    ├── config.yaml                    # ⚙️  Agent configuration
    ├── agent_executer.py              # 🔧 Agent execution logic
    └── ... (other log analytics files)
```

## 🔄 Deployment Process Details

### What Happens During Deployment

#### Log Analytics Agent Deployment:
1. **Wrapper Creation**: Creates `main_agentcore.py` that wraps the A2A server
2. **AgentCore Configuration**: Configures with OAuth2 and execution role
3. **Container Build**: Builds ARM64 container via CodeBuild
4. **Runtime Deployment**: Deploys to Bedrock AgentCore
5. **Verification**: Confirms successful deployment

#### Host Agent Deployment:
1. **Direct Configuration**: Configures existing `main.py` with AgentCore
2. **OAuth2 Setup**: Uses same OAuth2 configuration as reference
3. **Container Build**: Builds ARM64 container via CodeBuild  
4. **Runtime Deployment**: Deploys to Bedrock AgentCore
5. **Verification**: Confirms successful deployment

### Key Features:
- ✅ **Reference Pattern Compliance**: Follows exact same pattern as `agentcore_agent_runtime.py`
- 🔐 **OAuth2 Authentication**: Uses machine client for runtime access
- 🏗️ **SSM Integration**: Retrieves configuration from Parameter Store
- 🛡️ **IAM Management**: Ensures proper execution role permissions
- 🔄 **ARM64 Support**: Uses CodeBuild for proper container architecture
- 🧪 **Comprehensive Testing**: Includes interactive testing capabilities

## 🔍 Troubleshooting

### Common Issues

1. **Prerequisites Not Deployed**
   ```
   ❌ Missing parameter: /a2a/app/log-analytics/agentcore/gateway_iam_role
   ```
   **Solution**: Deploy prerequisites first: `cd ../../agentcore-log-analytics && ./scripts/prereq.sh`

2. **AgentCore CLI Not Found**
   ```
   ❌ AgentCore CLI not found
   ```
   **Solution**: Install AgentCore CLI: `pip install bedrock-agentcore`

3. **Permission Issues**
   ```
   ⚠️ Could not verify/add execution role permissions
   ```
   **Solution**: Ensure AWS credentials have IAM permissions

4. **Agent Not Found After Deployment**
   ```
   ❌ Agent 'agent_name' not found in deployed runtimes
   ```
   **Solution**: Check deployment logs for errors, verify AWS region

### Debug Commands
```bash
# Check AWS credentials and region
aws sts get-caller-identity
aws configure get region

# List existing runtimes
python3 deploy_a2a_agents.py list-agents

# Test individual deployment scripts
cd host && python3 agentcore_host_runtime.py create --name test_host
cd log-analytics-agent && python3 agentcore_log_analytics_runtime.py create --name test_log
```

## 🎯 Integration with Main System

This A2A local deployment integrates with the main agentcore-log-analytics system:

- **Shared Prerequisites**: Uses same SSM parameters and OAuth2 configuration
- **Same IAM Roles**: Uses same execution roles as main system
- **Compatible Architecture**: Follows same deployment patterns
- **Unified Testing**: Can be tested alongside main system agents

## 📚 Additional Documentation

- **Host Agent Details**: See `host/README.md` and `host/DEPLOYMENT_GUIDE.md`
- **Main System**: See `../../agentcore-log-analytics/README.md`
- **A2A Protocol**: See `../README.md` for A2A architecture details

## 🎉 Success Indicators

After successful deployment, you should see:

```
🎉 All agents deployed and verified successfully!

📋 Next Steps:
   Test Log Analytics: cd log-analytics-agent && python ../host/test_deployment.py test a2a_log_analytics_agent --prompt 'Analyze TGW traffic'
   Test Host Agent: cd host && python test_deployment.py test a2a_host_agent --prompt 'Hello'
   Interactive Test: cd host && python test_deployment.py test a2a_host_agent --interactive
```

Both agents will be available as production AgentCore runtimes, ready for integration with your applications and workflows.
