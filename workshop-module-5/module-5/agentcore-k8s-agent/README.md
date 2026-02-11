# K8s Diagnostics Agent with Amazon Bedrock AgentCore

### Core Components:
- **AgentCore Runtime**: BedrockAgentCoreApp with streaming responses
- **OAuth2 Authentication**: PKCE authorization code flow
- **MCP Gateway**: Tool access gateway with `mcpServer` target type
- **EKS MCP Server**: Official AWS Labs eks-mcp-server (15+ tools)
- **Cognito Authentication**: Complete OAuth2 provider setup

## Architecture

```
User -> OAuth2 PKCE Flow -> AgentCore Runtime -> MCP Gateway (mcpServer target) -> eks-mcp-server Runtime -> EKS / CloudWatch / IAM
```

## Project Structure

```
agentcore-k8s-agent/
├── .bedrock_agentcore.yaml           # Agent configuration
├── main.py                           # BedrockAgentCoreApp runtime entrypoint
├── README.md                         # This documentation
├── requirements.txt                  # Python dependencies
├── Dockerfile                        # Container build
├── agent_config/                     # Agent logic modules
│   ├── __init__.py
│   ├── access_token.py               # Gateway authentication tokens
│   ├── agent.py                      # K8sAgent class + system prompt
│   ├── agent_task.py                 # Core agent processing logic
│   ├── context.py                    # K8sContext management
│   ├── memory_hook_provider.py       # Memory integration
│   ├── streaming_queue.py            # Response streaming
│   └── utils.py                      # Utility functions
├── prerequisite/                     # Tool backend deployment
│   └── eks-mcp-server/              # Official AWS Labs EKS MCP Server
│       ├── main.py                   # HTTP transport wrapper
│       ├── Dockerfile                # Container build
│       ├── .bedrock_agentcore.yaml   # AgentCore runtime config
│       ├── deploy-eks-mcp-server.sh  # Deployment script
│       └── requirements.txt          # Dependencies
├── scripts/
│   ├── agentcore_gateway.py          # Gateway management (mcpServer targets)
│   ├── setup-dependencies.sh         # Dependency installation
│   └── utils.py                      # Script utilities
└── test/
    └── test_agent.py                 # PKCE OAuth2 flow testing
```

## EKS MCP Server Tools (via awslabs.eks-mcp-server)

### Kubernetes Resource Management
| Tool | Description |
|------|-------------|
| `list_k8s_resources` | List K8s resources with namespace/label/field filtering |
| `manage_k8s_resource` | Create, read, update, patch, delete K8s resources |
| `apply_yaml` | Apply K8s YAML manifests (multi-document support) |
| `list_api_versions` | List available API versions in the cluster |
| `generate_app_manifest` | Generate deployment + service manifests |

### Diagnostics & Troubleshooting
| Tool | Description |
|------|-------------|
| `get_pod_logs` | Pod container logs with time/line filtering |
| `get_k8s_events` | K8s events with timestamps, reasons, messages |
| `get_eks_insights` | EKS Insights (MISCONFIGURATION, UPGRADE_READINESS) |
| `search_eks_troubleshoot_guide` | Search EKS troubleshooting knowledge base |

### CloudWatch Integration
| Tool | Description |
|------|-------------|
| `get_cloudwatch_logs` | CloudWatch Logs for pods, nodes, containers, clusters |
| `get_cloudwatch_metrics` | CloudWatch metrics with configurable dimensions |
| `get_eks_metrics_guidance` | Container Insights metrics guidance per resource type |

### VPC, IAM & Cluster Management
| Tool | Description |
|------|-------------|
| `get_eks_vpc_config` | Comprehensive VPC configuration for EKS clusters |
| `get_policies_for_role` | IAM role policies (assume role, managed, inline) |
| `manage_eks_stacks` | CloudFormation stack operations for EKS clusters |

## Deployment Steps

#### 1. Setup dependencies
```bash
chmod +x ./scripts/setup-dependencies.sh
./scripts/setup-dependencies.sh
```

#### 2. Deploy EKS MCP Server as AgentCore Runtime
```bash
chmod +x ./prerequisite/eks-mcp-server/deploy-eks-mcp-server.sh
./prerequisite/eks-mcp-server/deploy-eks-mcp-server.sh
```

#### 3. Activate venv and create gateway (mcpServer target)
```bash
source .venv/bin/activate
python3 scripts/agentcore_gateway.py create --name k8s-gateway
```

#### 4. Deploy K8s Agent runtime
```bash
python3 scripts/agentcore_agent_runtime.py create --name k8s_agent_runtime
```

#### 5. Test the system
```bash
python3 test/test_agent.py a2a_k8s_agent_runtime --prompt "Check pod status in my cluster" --interactive
```

## Adding New MCP Server Targets

The gateway supports adding additional EKS-related MCP servers as targets:

```bash
python3 scripts/agentcore_gateway.py add-target \
    --name "EksMonitoringMcp" \
    --description "EKS monitoring MCP server" \
    --endpoint "https://<new-mcp-server-endpoint>"
```

The K8s Agent will automatically discover and use tools from all registered MCP server targets.

## SSM Parameters

All parameters are stored under `/a2a/app/k8s/agentcore/`:

| Parameter | Purpose |
|-----------|---------|
| `gateway_url` | MCP gateway URL for K8s tools |
| `gateway_id` | MCP gateway ID |
| `cognito_provider` | Cognito provider name for M2M auth |
| `memory_id` | AgentCore memory ID |
| `user_id` | Consistent user ID |
| `machine_client_secret` | OAuth client secret |
| `cognito_token_url` | Cognito token endpoint |
| `eks_mcp_server_endpoint` | EKS MCP Server runtime HTTPS endpoint |
| `eks_mcp_server_arn` | EKS MCP Server runtime ARN |
| `gateway_iam_role` | Gateway execution role ARN |
