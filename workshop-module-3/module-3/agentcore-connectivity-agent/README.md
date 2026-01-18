# Approach-2 : Troubleshooting Agent with Amazon Bedrock AgentCore

### Core Components:
- **AgentCore Runtime**: BedrockAgentCoreApp with streaming responses  
- **OAuth2 Authentication**: PKCE authorization code flow (same as reference)
- **MCP Gateway**: Tool access gateway with JWT authorization
- **VPC Analyzer Lambda**: VPC Reachability Analyzer integration
- **Cognito Authentication**: Complete OAuth2 provider setup

## 🏗️ Architecture

```
User → OAuth2 PKCE Flow → AgentCore Runtime → MCP Gateway → VPC Analyzer Lambda → AWS VPC Reachability Analyzer
```

## 📁 Project Structure (Reference Compliant)

```
troubleshooting-agent-cloudshell/
├── .bedrock_agentcore.yaml           # 🎯 Agent configuration (reference standard)
├── main.py                           # 🚀 BedrockAgentCoreApp runtime entrypoint
├── README.md                         # 📖 This documentation
├── requirements.txt                  # 📦 Python dependencies
├── agent_config/                     # 🧠 Agent logic modules (same as reference)
│   ├── __init__.py
│   ├── access_token.py               # Gateway authentication tokens
│   ├── agent_task.py                 # Core agent processing logic
│   ├── context.py                    # Context management
│   ├── streaming_queue.py            # Response streaming
│   └── utils.py                      # Utility functions
├── images/                           # 📸 Architecture diagrams
├── prerequisite/                     # 🏗️ Infrastructure templates (reference location)
│   ├── cognito.yaml                  # Complete Cognito + SSM parameters setup
│   ├── lambda-check/                 # VPC Connectivity Check Lambda tool (renamed)
│   │   ├── api_spec.json             # OpenAPI specification for connectivity analysis
│   │   ├── deploy-check-tool.sh      # Connectivity Lambda deployment script (renamed)
│   │   └── python/                   # Lambda function code
│   │       ├── Dockerfile            # Container configuration
│   │       ├── lambda_function.py    # VPC Reachability Analyzer handler
│   │       └── requirements.txt      # Lambda dependencies
│   ├── lambda-dns/                   # DNS Resolution Lambda tool (NEW!)
│   │   ├── api_spec.json             # OpenAPI specification for DNS resolution
│   │   ├── deploy-dns-tool.sh        # DNS Lambda deployment script
│   │   └── python/                   # Lambda function code
│   │       ├── Dockerfile            # Container configuration
│   │       ├── lambda_function.py    # Route 53 DNS resolution handler
│   │       └── requirements.txt      # Lambda dependencies
│   └── lambda-fix/                   # Connectivity Fix Lambda tool 
│       ├── api_spec.json             # OpenAPI specification for connectivity fixes
│       ├── deploy-connectivity-fix-tool.sh # Fix Lambda deployment script
│       └── python/                   # Lambda function code
│           ├── Dockerfile            # Container configuration
│           ├── lambda_function.py    # Security group fix handler
│           └── requirements.txt      # Lambda dependencies
├── scripts/                          # 🚀 All deployment logic (reference location)
│   ├── agentcore_agent_runtime.py   # Runtime deployment management
│   ├── agentcore_gateway.py          # Gateway creation and management
│   ├── cognito_credentials_provider.py # Complete Cognito setup
│   ├── prereq.sh                     # Prerequisites deployment
│   ├── setup_memory.py               # Memory configuration setup
│   ├── setup-dependencies.sh         # Dependency installation script
│   ├── test_memory_validation.py     # Memory functionality testing
│   └── utils.py                      # Shared deployment utilities
└── test/                             # 🧪 Testing (reference location)
    └── test_agent.py                 # PKCE OAuth2 flow testing (same as reference)
```

### Prerequisites
- AWS EC2 instance with proper IAM permissions
- Route 53 Private Hosted Zone (for DNS resolution)

### Deployment Steps
```bash
mkdir troubleshooting-agent
cd troubleshooting-agent

# 1. Setup dependencies
chmod +x scripts/setup-dependencies.sh
./scripts/setup-dependencies.sh

# 2. Deploy infrastructure (Cognito, IAM roles)
chmod +x scripts/prereq.sh
./scripts/prereq.sh

# 3. Activate venv
source .venv/bin/activate
python3 scripts/cognito_credentials_provider.py create-provider

# 4. Deploy DNS resolution tool
chmod +x prerequisite/lambda-dns/deploy-dns-tool.sh
cd prerequisite/lambda-dns && ./deploy-dns-tool.sh && cd ../..

# 5. Deploy connectivity analysis tool 
chmod +x prerequisite/lambda-check/deploy-check-tool.sh 
cd prerequisite/lambda-check && ./deploy-check-tool.sh && cd ../..

# 6. Deploy connectivity fix tool
chmod +x prerequisite/lambda-fix/deploy-connectivity-fix-tool.sh 
cd prerequisite/lambda-fix && ./deploy-connectivity-fix-tool.sh && cd ../..

# 7. Setup memory configuration
chmod +x scripts/setup_memory.py
python3 scripts/setup_memory.py

# 8. Create gateway and runtime
python3 scripts/agentcore_gateway.py create --name troubleshooting-gateway
python3 scripts/agentcore_agent_runtime.py create --name troubleshooting_agent_runtime

# 9. Test the system
python3 test/test_agent.py troubleshooting_agent_runtime --prompt "Hello" --interactive
```
