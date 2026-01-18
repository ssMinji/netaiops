# Performance Agent with Amazon Bedrock AgentCore

### Core Components:
- **AgentCore Runtime**: BedrockAgentCoreApp with streaming responses  
- **OAuth2 Authentication**: PKCE authorization code flow
- **MCP Gateway**: Tool access gateway with JWT authorization
- **Performance Lambda**: Transit Gateway traffic analysis integration
- **Cognito Authentication**: Complete OAuth2 provider setup
- **Test Infrastructure**: Multi-region network infrastructure for testing

## 🏗️ Architecture

```
User → OAuth2 PKCE Flow → AgentCore Runtime → MCP Gateway → Performance Lambda → AWS Transit Gateway Flow Logs
```

## 📁 Project Structure

```
agentcore-performance/
├── .bedrock_agentcore.yaml           # 🎯 Agent configuration
├── main.py                           # 🚀 BedrockAgentCoreApp runtime entrypoint
├── README.md                         # 📖 This documentation
├── requirements.txt                  # 📦 Python dependencies
├── agent_config/                     # 🧠 Agent logic modules
│   ├── __init__.py
│   ├── access_token.py               # Gateway authentication tokens
│   ├── agent_task.py                 # Core agent processing logic
│   ├── context.py                    # Context management
│   ├── memory_hook_provider.py       # Memory integration
│   ├── streaming_queue.py            # Response streaming
│   └── utils.py                      # Utility functions
├── prerequisite/                     # 🏗️ Infrastructure templates
│   ├── cognito.yaml                  # Complete Cognito + SSM parameters setup
│   └── lambda-performance/         # Transit Gateway Performance Lambda tool
│       ├── deploy-analyze-tgw-traffic-tool.sh # Lambda deployment script
│       ├── DYNAMODB_DATA_USAGE.md    # DynamoDB usage documentation
│       └── python/                   # Lambda function code
│           ├── Dockerfile            # Container configuration
│           ├── lambda_function.py    # TGW traffic analysis handler
│           └── requirements.txt      # Lambda dependencies
├── scripts/                          # 🚀 All deployment logic
│   ├── agentcore_agent_runtime.py   # Runtime deployment management
│   ├── agentcore_gateway.py          # Gateway creation and management
│   ├── cognito_credentials_provider.py # Complete Cognito setup
│   ├── prereq.sh                     # Prerequisites deployment
│   ├── search_memory.py              # Memory search functionality
│   ├── setup_memory.py               # Memory configuration setup
│   ├── setup-dependencies.sh         # Dependency installation script
│   └── utils.py                      # Shared deployment utilities
├── test/                             # 🧪 Testing
│   └── test_agent.py                 # PKCE OAuth2 flow testing
└── test_infra/                       # 🌐 Multi-region test infrastructure
    ├── README.md                     # Test infrastructure documentation
    ├── deploy-retail-app-main.sh     # Retail application StackSet deployment
    ├── deploy-cross-region-tgw-peering.sh # Cross-region TGW peering
    ├── deploy-app-control-plane.sh   # Application control plane deployment
    ├── test-retail-connectivity.sh   # Network connectivity testing
    ├── retail-app.yml                # Retail application CloudFormation template
    ├── cross-region-tgw-peering.yml  # Cross-region peering template
    ├── app-control-plane-use1.yml    # Control plane template
    └── lambda/                       # Infrastructure metadata Lambda functions
        ├── populate_metadata.py      # Comprehensive metadata population
        └── populate_application_metadata.py # Application-specific metadata
```

### Prerequisites
- **Amazon Linux EC2 instance** with necessary IAM permissions to run the deployment steps
- **IAM permissions** for the EC2 instance to deploy and manage:
  - Amazon Bedrock AgentCore resources
  - AWS Lambda functions
  - Amazon Cognito user pools
  - AWS Systems Manager (SSM) parameters
  - Amazon DynamoDB tables
  - AWS CloudFormation stacks
  - Amazon SNS topics and subscriptions
  - VPC and networking resources
- **Multi-region access** to deploy resources in `us-east-1` and `us-west-2` regions (for test infrastructure)

## Deployment Steps

#### 1. Setup dependencies
```bash
chmod +x ./scripts/setup-dependencies.sh
./scripts/setup-dependencies.sh
```

#### 2. Deploy infrastructure (Cognito, IAM roles)
```bash
chmod +x ./scripts/prereq.sh
./scripts/prereq.sh
```

#### 3. Activate venv
```bash
source .venv/bin/activate
python3 scripts/cognito_credentials_provider.py create-provider
```

#### 4. Deploy performance tool
```bash
chmod +x ./prerequisite/lambda-performance/deploy-analyze-tgw-traffic-tool.sh
./prerequisite/lambda-performance/deploy-analyze-tgw-traffic-tool.sh
```

#### 5. Setup memory configuration
```bash
# Create the memory system for application contact tracking
python3 scripts/setup_memory.py --action create

# Add application contact information (replace with your actual company emails)
python3 scripts/setup_memory.py --action seed --app Retail-Application --email aksareen@amazon.com
python3 scripts/setup_memory.py --action seed --app Finance-Application --email finance@yourcompany.com

# Optional: Add more applications as needed
# python3 scripts/setup_memory.py --action seed --app <YourApp-Name> --email <contact@yourcompany.com>

# Optional: Verify seeded memory
# python3 scripts/setup_memory.py --action verify
```

#### 6. Create gateway and runtime
```bash
python3 scripts/agentcore_gateway.py create --name performance-gateway
python3 scripts/agentcore_agent_runtime.py create --name performance_agent_runtime
```

#### 7. Deploy retail application infrastructure
```bash
chmod +x ./test_infra/deploy-retail-app-main.sh
./test_infra/deploy-retail-app-main.sh
```

#### 8. Deploy cross-region peering
```bash
chmod +x ./test_infra/deploy-cross-region-tgw-peering.sh
./test_infra/deploy-cross-region-tgw-peering.sh
```

#### 9. Deploy control plane (use same email as step 5 for SNS notifications)
```bash
chmod +x ./test_infra/deploy-app-control-plane.sh
./test_infra/deploy-app-control-plane.sh -app Retail-Application -email retail@yourcompany.com
```

#### 10. Verify test infrastructure deployment
```bash
chmod +x ./test_infra/test-retail-connectivity.sh
./test_infra/test-retail-connectivity.sh
```

#### 11. Test the system
```bash
python3 test/test_agent_m2m.py a2a_performance_agent_runtime --prompt "Hello" --interactive
```

## 🌐 Test Infrastructure Deployment

To set up the complete multi-region test infrastructure for realistic performance testing, see the detailed deployment guide:

**📖 [Test Infrastructure Deployment Guide](test_infra/README.md)**

The test infrastructure provides a realistic multi-region environment with:
- **Multi-region deployment**: us-east-1 and us-west-2 with cross-region connectivity
- **Network infrastructure**: 4 VPCs, Transit Gateways, and EC2 instances
- **Monitoring infrastructure**: DynamoDB metadata storage and Lambda functions
- **Comprehensive testing**: Automated connectivity validation and troubleshooting

For detailed deployment instructions, prerequisites, troubleshooting, and architecture information, refer to the [Test Infrastructure README](test_infra/README.md).
