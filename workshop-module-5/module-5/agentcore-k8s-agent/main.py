"""
=============================================================================
K8s Diagnostics Agent - EKS Cluster Diagnostics (Module 5)
K8s Diagnostics Agent - EKS 클러스터 진단 (모듈 5)
=============================================================================

Simplified single-entrypoint architecture based on Strands Agent + AgentCore Runtime.
Strands Agent + AgentCore Runtime 기반 단일 엔트리포인트 아키텍처.

Author: NetAIOps Team
Module: workshop-module-5 (agentcore-k8s-agent)
=============================================================================
"""

import os
import logging
import boto3
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands_tools import current_time
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from agent_config.access_token import get_gateway_access_token
from agent_config.memory_hook_provider import MemoryHookProvider

# =============================================================================
# Environment & Logging
# =============================================================================
os.environ["STRANDS_OTEL_ENABLE_CONSOLE_EXPORT"] = "true"
os.environ["STRANDS_TOOL_CONSOLE_MODE"] = "enabled"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================
DEFAULT_MODEL_ID = "global.anthropic.claude-opus-4-6-v1"
SSM_PREFIX = "/a2a/app/k8s/agentcore"

app = BedrockAgentCoreApp()
_memory_client = MemoryClient()


# =============================================================================
# Helpers
# =============================================================================
def get_ssm_parameter(name: str) -> str:
    """SSM Parameter Store에서 값 조회"""
    ssm = boto3.client("ssm")
    return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


def get_aws_account_id() -> str | None:
    """현재 AWS 계정 ID 조회"""
    try:
        return boto3.client("sts").get_caller_identity()["Account"]
    except Exception as e:
        logger.warning(f"Could not get AWS account ID: {e}")
        return None


# =============================================================================
# System Prompt
# =============================================================================
SYSTEM_PROMPT_TEMPLATE = """
You are a Kubernetes/EKS Diagnostics AI assistant specialized in Amazon EKS cluster troubleshooting and analysis.
Help users diagnose EKS cluster issues, manage Kubernetes resources, analyze logs, and monitor metrics.

IMPORTANT CONFIGURATION:
- ALWAYS use agent memory to find out the EKS cluster name and application context the user is requesting analysis of
- When asked about cluster details, always use agent memory to find the appropriate cluster name and contact
- When running diagnostic tools, ALWAYS use memory to find the cluster name and owner contact
- If the user has not yet specified a region or cluster name, **ask them** before running any diagnostic tools.
- Once the user provides region and cluster name, remember them for the rest of the session.
{account_info}

**CRITICAL BEHAVIOR RULES:**
- When region is NOT specified, ASK the user which region to use.
- When region IS specified but cluster name is NOT, call **set_aws_region** then **list_eks_clusters** to show available clusters. Let the user pick one.
- Once region and cluster name are known, execute diagnostics immediately without further confirmation.
- When multiple tools are relevant, call them in the most logical diagnostic order.

**REGION HANDLING:**
- When the user specifies or implies a specific AWS region (e.g. "Virginia", "Oregon", "Seoul", "us-east-1"),
  ALWAYS call **set_aws_region** FIRST before using any other EKS tools.
- Common region mappings: Virginia=us-east-1, Oregon=us-west-2, Seoul=ap-northeast-2,
  Tokyo=ap-northeast-1, Ireland=eu-west-1, Frankfurt=eu-central-1, Singapore=ap-southeast-1
- If the user does not mention a region, ASK which region to use.
- You only need to call set_aws_region once per region change, not before every single tool call.

**CLUSTER DISCOVERY:**
- When the user specifies a region but NOT a specific cluster name, use **list_eks_clusters** to show available clusters.
- Present the list to the user and let them choose which cluster to analyze.
- If only one cluster exists in the region, you may proceed with that cluster directly.

You have access to the official AWS Labs EKS MCP Server tools through the AgentCore Gateway.

CORE TOOLS ALWAYS AVAILABLE:
- current_time: Gets the current time in ISO 8601 format for a specified timezone

EKS MCP SERVER TOOLS (via AgentCore Gateway / awslabs.eks-mcp-server):

**Region Control:**

0. **set_aws_region**: Set the target AWS region for all subsequent EKS tool calls
   - Parameters: region (e.g. "us-east-1", "ap-northeast-2")
   - MUST be called before other tools when user specifies a region
   - Persists for the session until changed again

0.1. **list_eks_clusters**: List all EKS clusters in the current region
   - No parameters required (uses the region set by set_aws_region)
   - Call after set_aws_region to discover available clusters
   - Use this when the user specifies a region but not a cluster name

**Kubernetes Resource Management:**

1. **list_k8s_resources**: List Kubernetes resources with filtering
   - Parameters: cluster_name, kind, api_version, namespace (optional), label_selector (optional), field_selector (optional)

2. **manage_k8s_resource**: CRUD operations on individual K8s resources
   - Parameters: operation (create/replace/patch/delete/read), cluster_name, kind, api_version, name, namespace (optional), body (optional)

3. **apply_yaml**: Apply Kubernetes YAML manifests
   - Parameters: yaml_path, cluster_name, namespace, force

4. **list_api_versions**: List available API versions in the cluster
   - Parameters: cluster_name

5. **generate_app_manifest**: Generate deployment + service YAML manifests
   - Parameters: app_name, image_uri, output_dir, port, replicas, cpu, memory, namespace, load_balancer_scheme

**Diagnostics & Troubleshooting:**

6. **get_pod_logs**: Retrieve pod container logs
   - Parameters: cluster_name, pod_name, namespace, container_name (optional), since_seconds (optional), tail_lines (optional), limit_bytes (optional), previous (optional)

7. **get_k8s_events**: Get events for a specific K8s resource
   - Parameters: cluster_name, kind, name, namespace (optional)

8. **get_eks_insights**: Retrieve EKS Insights for cluster issues
   - Parameters: cluster_name, insight_id (optional), category (optional: MISCONFIGURATION, UPGRADE_READINESS)

9. **search_eks_troubleshoot_guide**: Search EKS troubleshooting knowledge base
   - Parameters: query

**CloudWatch Integration:**

10. **get_cloudwatch_logs**: Fetch CloudWatch logs for EKS resources
    - Parameters: cluster_name, log_type, resource_type, resource_name (optional), minutes (optional), start_time (optional), end_time (optional), limit (optional), filter_pattern (optional), fields (optional)

11. **get_cloudwatch_metrics**: Retrieve CloudWatch metrics
    - Parameters: cluster_name, metric_name, namespace, dimensions, minutes (optional), start_time (optional), end_time (optional), stat (optional), period (optional)

12. **get_eks_metrics_guidance**: Get available Container Insights metrics per resource type
    - Parameters: resource_type (cluster/node/pod/namespace/service)

**VPC & Networking:**

13. **get_eks_vpc_config**: Get comprehensive VPC configuration for EKS clusters
    - Parameters: cluster_name, vpc_id (optional)

**IAM:**

14. **get_policies_for_role**: Retrieve all policies attached to an IAM role
    - Parameters: role_name

**EKS Cluster Management:**

15. **manage_eks_stacks**: Manage EKS CloudFormation stacks
    - Parameters: operation (generate/deploy/describe/delete), template_file, cluster_name

**DIAGNOSTIC WORKFLOWS:**

1. **General Cluster Health Check:**
   - Use list_k8s_resources with kind=Node to check node status
   - Use list_k8s_resources with kind=Pod to check pod states across namespaces
   - Use list_k8s_resources with kind=Deployment to verify deployments
   - Use get_k8s_events on any unhealthy resources for details
   - Use get_eks_insights for configuration and upgrade issues

2. **Pod Crash Diagnosis:**
   - Use list_k8s_resources with kind=Pod to identify crashed/restarting pods
   - Use get_k8s_events on the failing pod for event details
   - Use get_pod_logs to get container logs from the crashing pod
   - Use get_cloudwatch_metrics to check resource utilization (OOM)
   - Use search_eks_troubleshoot_guide for known issue patterns

3. **Application Slowness Investigation:**
   - Use get_cloudwatch_metrics for CPU/memory utilization
   - Use list_k8s_resources with kind=Pod/Service to check health
   - Use get_cloudwatch_logs to search for timeout or error patterns
   - Use get_eks_vpc_config to verify networking

4. **Deployment Failure Analysis:**
   - Use list_k8s_resources with kind=Deployment to identify failed rollouts
   - Use get_k8s_events on the deployment for event details
   - Use get_pod_logs for init container or application startup logs
   - Use search_eks_troubleshoot_guide for known deployment issues

**RESPONSE FORMATTING RULES:**
- Organize findings by severity (Critical > Warning > Info)
- Always include cluster name, namespace, and resource names
- Provide specific kubectl commands or AWS CLI commands for remediation
- Show metrics with proper units (CPU in millicores, memory in Mi/Gi)
- Correlate findings across tools to provide unified diagnosis

Always be helpful and provide guidance based on the tools you actually have available in the current session.
"""


# =============================================================================
# K8sAgent
# =============================================================================
class K8sAgent:
    """K8s Diagnostics Agent - Strands + MCP Gateway + AgentCore Memory"""

    def __init__(self, bearer_token: str, memory_hook_provider: MemoryHookProvider = None,
                 actor_id: str = None, session_id: str = None):
        model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)
        self.model = BedrockModel(model_id=model_id)

        # Build system prompt with account info
        account_id = get_aws_account_id()
        account_info = (
            f'- **SESSION AWS ACCOUNT**: Use "{account_id}" as the account_id parameter '
            f"for EKS tools when AWS account ID is required"
            if account_id
            else "- **SESSION AWS ACCOUNT**: Could not determine AWS account ID from session"
        )
        self.system_prompt = SYSTEM_PROMPT_TEMPLATE.format(account_info=account_info)

        # Initialize tools: current_time + MCP Gateway tools
        self.tools = [current_time]

        gateway_url = get_ssm_parameter(f"{SSM_PREFIX}/gateway_url")
        if gateway_url and bearer_token and bearer_token != "dummy":
            try:
                self.mcp_client = MCPClient(
                    lambda: streamablehttp_client(
                        gateway_url,
                        headers={"Authorization": f"Bearer {bearer_token}"},
                    )
                )
                self.mcp_client.start()
                mcp_tools = self.mcp_client.list_tools_sync()
                self.tools.extend(mcp_tools)
                logger.info(f"Loaded {len(mcp_tools)} tools from MCP Gateway")
            except Exception as e:
                logger.warning(f"MCP client error: {e}")

        # Create Strands Agent with optional memory hooks
        hooks = [memory_hook_provider] if memory_hook_provider else []
        self.agent = Agent(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            hooks=hooks,
            description="K8s Diagnostics Agent",
        )

        # Set agent state for memory hook provider
        if actor_id and session_id:
            if not hasattr(self.agent, "state"):
                self.agent.state = {}

            if hasattr(self.agent.state, "set"):
                self.agent.state.set("actor_id", actor_id)
                self.agent.state.set("session_id", session_id)
            elif hasattr(self.agent.state, "__setitem__"):
                self.agent.state["actor_id"] = actor_id
                self.agent.state["session_id"] = session_id
            else:
                self.agent.state = {"actor_id": actor_id, "session_id": session_id}

            logger.info(f"Set agent state: actor_id={actor_id}, session_id={session_id}")

    async def stream(self, user_query: str):
        """Stream agent responses."""
        try:
            async for event in self.agent.stream_async(user_query):
                if "data" in event:
                    yield event["data"]
        except Exception as e:
            yield f"Error: {e}"


# =============================================================================
# Global Agent Cache
# =============================================================================
_agent: K8sAgent | None = None
_access_token: str | None = None


# =============================================================================
# Entrypoint
# =============================================================================
@app.entrypoint
async def invoke(payload, context):
    """AgentCore Runtime entrypoint"""
    global _agent, _access_token

    user_message = payload["prompt"]
    actor_id = payload["actor_id"]
    session_id = context.session_id

    if not session_id:
        raise Exception("Context session_id is not set")

    # Lazy initialization: create agent once, reuse for subsequent requests
    if _agent is None:
        if _access_token is None:
            _access_token = await get_gateway_access_token()

        # Get memory config from SSM
        memory_id = get_ssm_parameter(f"{SSM_PREFIX}/memory_id")

        # Get consistent user ID from SSM, fallback to actor_id
        try:
            user_id = get_ssm_parameter(f"{SSM_PREFIX}/user_id")
            logger.info(f"Using consistent USER_ID from SSM: {user_id}")
        except Exception:
            logger.warning("Could not retrieve USER_ID from SSM, using actor_id")
            user_id = actor_id

        # Create memory hook provider
        memory_hook = MemoryHookProvider(
            memory_id=memory_id,
            client=_memory_client,
        )

        # Create agent
        _agent = K8sAgent(
            bearer_token=_access_token,
            memory_hook_provider=memory_hook,
            actor_id=user_id,
            session_id=session_id,
        )

    # Stream response directly
    async for chunk in _agent.stream(user_message):
        yield chunk


# =============================================================================
# Lambda handler & main
# =============================================================================
def handler(event, context):
    """Lambda container handler"""
    return app.handle(event, context)


if __name__ == "__main__":
    app.run()
