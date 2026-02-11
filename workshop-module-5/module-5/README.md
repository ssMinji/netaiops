# Workshop Module 5: K8s Diagnostics Agent

## Overview

This module adds Kubernetes/EKS diagnostics capability to the NetAIOps platform. The K8s Diagnostics Agent can diagnose EKS cluster issues including pod failures, node health, deployment rollouts, service endpoints, log analysis, resource metrics, and more.

It uses the **official AWS Labs eks-mcp-server** (`awslabs.eks-mcp-server`) as the tool backend, deployed as an AgentCore Runtime with Streamable HTTP transport. The AgentCore MCP Gateway aggregates MCP server targets, allowing additional EKS-related MCP servers to be added without changing agent code.

## Architecture

```
CollaboratorAgent
    |
    v (A2A Protocol)
A2A K8s Agent (ECS/ALB, port 10009)
    |
    v (AgentCore Runtime)
K8s Diagnostics Agent (Bedrock AgentCore)
    |
    v (MCP Gateway - mcpServer target)
    +--> eks-mcp-server (AgentCore Runtime, Streamable HTTP)
    |       |
    |       +--> EKS Cluster API (Kubernetes client)
    |       +--> CloudWatch Logs / Container Insights
    |       +--> IAM / VPC / CloudFormation
    |
    +--> (future) additional EKS MCP servers
```

**Key difference from Modules 1-3:** Instead of custom Lambda tools behind the Gateway, this module uses the `mcpServer` Gateway target type pointing directly to the official eks-mcp-server running as an AgentCore Runtime.

## Components

### 1. AgentCore K8s Agent (`agentcore-k8s-agent/`)
- Bedrock AgentCore runtime with K8sAgent class
- System prompt with 15+ tool descriptions and 4 diagnostic workflows
- Memory integration for cluster context persistence
- MCP Gateway connectivity for tool invocation

### 2. EKS MCP Server (`agentcore-k8s-agent/prerequisite/eks-mcp-server/`)
- Official AWS Labs `awslabs.eks-mcp-server` package
- Deployed as AgentCore Runtime with Streamable HTTP transport
- 15+ tools: resource management, logs, metrics, events, VPC, IAM, troubleshooting
- Registered as `mcpServer` target on the MCP Gateway

### 3. A2A Wrapper (`a2a/a2a-k8s-agent/`)
- A2A protocol server (port 10009) for CollaboratorAgent integration
- AgentCard with EKS diagnostics skill definition
- OAuth2 M2M authentication via Cognito

## EKS MCP Server Tools

| Category | Tool | Description |
|----------|------|-------------|
| K8s Resources | `list_k8s_resources` | List pods, nodes, deployments, services with filtering |
| K8s Resources | `manage_k8s_resource` | CRUD operations on K8s resources |
| K8s Resources | `apply_yaml` | Apply K8s manifests to clusters |
| K8s Resources | `list_api_versions` | List available API versions |
| App Support | `generate_app_manifest` | Generate deployment + service YAML |
| Diagnostics | `get_pod_logs` | Retrieve pod container logs |
| Diagnostics | `get_k8s_events` | Get events for K8s resources |
| Diagnostics | `get_eks_insights` | EKS Insights for config/upgrade issues |
| Diagnostics | `search_eks_troubleshoot_guide` | Search EKS troubleshooting KB |
| CloudWatch | `get_cloudwatch_logs` | CloudWatch Logs for EKS resources |
| CloudWatch | `get_cloudwatch_metrics` | CloudWatch metrics with dimensions |
| CloudWatch | `get_eks_metrics_guidance` | Container Insights metric guidance |
| Networking | `get_eks_vpc_config` | VPC configuration for EKS clusters |
| IAM | `get_policies_for_role` | IAM role policy inspection |
| Cluster Mgmt | `manage_eks_stacks` | CloudFormation stack operations |

## Configuration

- **Region**: us-west-2 (Oregon)
- **Model**: Claude Opus 4.6 (`global.anthropic.claude-opus-4-6-v1`)
- **A2A Port**: 10009
- **Gateway Target Type**: `mcpServer` (HTTPS endpoint)

## Deployment

See [agentcore-k8s-agent/README.md](agentcore-k8s-agent/README.md) for detailed deployment steps.

## Verification

1. **EKS MCP Server**: Deploy as AgentCore Runtime, verify HTTP endpoint is healthy
2. **Gateway**: Create with `mcpServer` target, verify target status is ACTIVE
3. **AgentCore agent**: Deploy via `bedrock-agentcore deploy`, invoke with test prompts
4. **A2A wrapper**: Deploy to ECS/ALB, verify `/.well-known/agent-card.json`
5. **End-to-end**: Send K8s query through CollaboratorAgent
