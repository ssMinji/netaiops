"""
=============================================================================
K8s Diagnostics Agent - EKS Cluster Diagnostics (Module 5 - A2A)
K8s Diagnostics Agent - EKS 클러스터 진단 (모듈 5 - A2A)
=============================================================================

Description (설명):
    Specialized agent for Kubernetes/EKS cluster diagnostics and
    troubleshooting within the A2A (Agent-to-Agent) collaboration framework.
    A2A (에이전트 간) 협업 프레임워크 내에서 Kubernetes/EKS 클러스터 진단 및
    문제 해결을 위한 전문 에이전트입니다.

Capabilities (기능):
    - Kubernetes resource management (K8s 리소스 관리)
    - Pod health and crash diagnosis (파드 상태 및 크래시 진단)
    - Node health monitoring (노드 상태 모니터링)
    - Deployment rollout and manifest generation (디플로이먼트 롤아웃 및 매니페스트 생성)
    - CloudWatch log/event analysis (CloudWatch 로그/이벤트 분석)
    - Container Insights resource metrics (Container Insights 리소스 메트릭)
    - EKS cluster stack management (EKS 클러스터 스택 관리)
    - VPC configuration analysis (VPC 구성 분석)
    - IAM policy inspection (IAM 정책 조회)
    - EKS Insights and troubleshooting (EKS 인사이트 및 문제 해결)

A2A Integration (A2A 통합):
    This agent can be invoked by the Host/Collaborator agent for
    K8s-specific tasks in multi-agent workflows.
    이 에이전트는 다중 에이전트 워크플로우에서 K8s 관련 작업을 위해
    Host/Collaborator 에이전트에 의해 호출될 수 있습니다.

Environment Variables (환경변수):
    BEDROCK_MODEL_ID: Override default Claude model
                      기본 Claude 모델 오버라이드

Author: NetAIOps Team
Module: workshop-module-5 (agentcore-k8s-agent)
=============================================================================
"""

# =============================================================================
# Imports (임포트)
# =============================================================================
from .memory_hook_provider import MemoryHookProvider  # Memory hook provider (메모리 훅 프로바이더)
from .utils import get_ssm_parameter                  # SSM parameter retrieval (SSM 파라미터 조회)
from mcp.client.streamable_http import streamablehttp_client  # MCP HTTP client
from strands import Agent                             # Strands AI Agent framework
from strands_tools import current_time                # Time utility tool (시간 유틸리티)
from strands.models import BedrockModel               # Bedrock model wrapper
from strands.tools.mcp import MCPClient               # MCP client for tools
from bedrock_agentcore.memory import MemoryClient     # AgentCore memory client
import logging
import boto3
import os

# Configure module logger (모듈 로거 설정)
logger = logging.getLogger(__name__)

# =============================================================================
# Default Configuration (기본 설정)
# =============================================================================
# Default model ID - Supports env var override for flexibility
# 기본 모델 ID - 유연성을 위해 환경변수 오버라이드 지원
DEFAULT_MODEL_ID = "global.anthropic.claude-opus-4-6-v1"


def get_aws_account_id():
    """
    Get the current AWS account ID from the session.
    세션에서 현재 AWS 계정 ID 가져오기.

    Returns (반환값):
        str: AWS account ID or None if unavailable
             AWS 계정 ID 또는 사용 불가 시 None
    """
    try:
        sts = boto3.client('sts')
        response = sts.get_caller_identity()
        return response['Account']
    except Exception as e:
        logger.warning(f"Could not get AWS account ID: {e}")
        return None


class K8sAgent:
    """
    K8s Diagnostics agent for A2A collaboration.
    A2A 협업을 위한 K8s 진단 에이전트.

    Handles EKS pod diagnostics, node health, deployment status,
    log analysis, and resource metrics as part of multi-agent
    troubleshooting workflows.
    다중 에이전트 문제 해결 워크플로우의 일부로
    EKS 파드 진단, 노드 상태, 디플로이먼트 상태, 로그 분석,
    리소스 메트릭을 처리합니다.
    """

    def __init__(
        self,
        bearer_token: str = None,
        memory_hook_provider: MemoryHookProvider = None,
        bedrock_model_id: str = None,
        system_prompt: str = None,
        actor_id: str = None,
        session_id: str = None,
    ):
        """
        Initialize the K8s Diagnostics Agent.
        K8s Diagnostics Agent 초기화.

        Args (인자):
            bearer_token (str): Unused, kept for API compatibility (하위 호환성)
            memory_hook_provider (MemoryHookProvider): Memory hook provider (메모리 훅 프로바이더)
            bedrock_model_id (str): Override model ID (모델 ID 오버라이드)
            system_prompt (str): Custom system prompt (사용자 정의 시스템 프롬프트)
            actor_id (str): Actor identifier for sessions (세션용 액터 식별자)
            session_id (str): Session identifier (세션 식별자)
        """
        # Model ID priority: env var > parameter > default
        # 모델 ID 우선순위: 환경변수 > 파라미터 > 기본값
        if bedrock_model_id is None:
            bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', DEFAULT_MODEL_ID)

        self.model_id = bedrock_model_id
        self.model = BedrockModel(model_id=self.model_id)
        self.memory_hook_provider = memory_hook_provider

        # Get AWS account ID from session
        aws_account_id = get_aws_account_id()
        account_info = f"- **SESSION AWS ACCOUNT**: Use \"{aws_account_id}\" as the account_id parameter for EKS tools when AWS account ID is required" if aws_account_id else "- **SESSION AWS ACCOUNT**: Could not determine AWS account ID from session"

        self.system_prompt = (
            system_prompt
            if system_prompt
            else f"""
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
   - Use to check pod status, node health, deployments, services, etc.

2. **manage_k8s_resource**: CRUD operations on individual K8s resources
   - Parameters: operation (create/replace/patch/delete/read), cluster_name, kind, api_version, name, namespace (optional), body (optional)
   - Use for reading specific resources or making changes

3. **apply_yaml**: Apply Kubernetes YAML manifests
   - Parameters: yaml_path, cluster_name, namespace, force
   - Supports multi-document YAML files

4. **list_api_versions**: List available API versions in the cluster
   - Parameters: cluster_name

5. **generate_app_manifest**: Generate deployment + service YAML manifests
   - Parameters: app_name, image_uri, output_dir, port, replicas, cpu, memory, namespace, load_balancer_scheme

**Diagnostics & Troubleshooting:**

6. **get_pod_logs**: Retrieve pod container logs
   - Parameters: cluster_name, pod_name, namespace, container_name (optional), since_seconds (optional), tail_lines (optional), limit_bytes (optional), previous (optional)
   - Requires --allow-sensitive-data-access flag on the MCP server

7. **get_k8s_events**: Get events for a specific K8s resource
   - Parameters: cluster_name, kind, name, namespace (optional)
   - Returns timestamps, count, message, reason, reporting component, type

8. **get_eks_insights**: Retrieve EKS Insights for cluster issues
   - Parameters: cluster_name, insight_id (optional), category (optional: MISCONFIGURATION, UPGRADE_READINESS)
   - Identifies configuration issues and upgrade readiness problems

9. **search_eks_troubleshoot_guide**: Search EKS troubleshooting knowledge base
   - Parameters: query
   - Returns symptoms, short-term and long-term fixes

**CloudWatch Integration:**

10. **get_cloudwatch_logs**: Fetch CloudWatch logs for EKS resources
    - Parameters: cluster_name, log_type (application/host/performance/control-plane/custom), resource_type (pod/node/container/cluster), resource_name (optional), minutes (optional), start_time (optional), end_time (optional), limit (optional), filter_pattern (optional), fields (optional)

11. **get_cloudwatch_metrics**: Retrieve CloudWatch metrics
    - Parameters: cluster_name, metric_name, namespace, dimensions, minutes (optional), start_time (optional), end_time (optional), stat (optional), period (optional)

12. **get_eks_metrics_guidance**: Get available Container Insights metrics per resource type
    - Parameters: resource_type (cluster/node/pod/namespace/service)
    - Returns metric names, dimensions, and descriptions

**VPC & Networking:**

13. **get_eks_vpc_config**: Get comprehensive VPC configuration for EKS clusters
    - Parameters: cluster_name, vpc_id (optional)
    - Provides CIDR blocks, route tables, subnet info, capacity validation

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
   - Summarize overall cluster health with actionable findings

2. **Pod Crash Diagnosis:**
   - Use list_k8s_resources with kind=Pod to identify crashed/restarting pods
   - Use get_k8s_events on the failing pod for event details
   - Use get_pod_logs to get container logs from the crashing pod
   - Use get_cloudwatch_metrics to check resource utilization (OOM)
   - Use search_eks_troubleshoot_guide for known issue patterns
   - Provide root cause analysis and remediation steps

3. **Application Slowness Investigation:**
   - Use get_cloudwatch_metrics for CPU/memory utilization
   - Use list_k8s_resources with kind=Pod/Service to check health
   - Use get_cloudwatch_logs to search for timeout or error patterns
   - Use get_eks_vpc_config to verify networking
   - Identify bottlenecks and recommend scaling or configuration changes

4. **Deployment Failure Analysis:**
   - Use list_k8s_resources with kind=Deployment to identify failed rollouts
   - Use get_k8s_events on the deployment for event details
   - Use get_pod_logs for init container or application startup logs
   - Use search_eks_troubleshoot_guide for known deployment issues
   - Recommend rollback or fix steps

**RESPONSE FORMATTING RULES:**
- Organize findings by severity (Critical > Warning > Info)
- Always include cluster name, namespace, and resource names
- Provide specific kubectl commands or AWS CLI commands for remediation
- Show metrics with proper units (CPU in millicores, memory in Mi/Gi)
- Correlate findings across tools to provide unified diagnosis

Always be helpful and provide guidance based on the tools you actually have available in the current session.
"""
        )

        # Get gateway URL
        gateway_url = get_ssm_parameter("/a2a/app/k8s/agentcore/gateway_url")

        self.tools = [current_time]

        # Initialize MCP client if gateway is available
        if gateway_url and bearer_token and bearer_token != "dummy":
            try:
                self.gateway_client = MCPClient(
                    lambda: streamablehttp_client(
                        gateway_url,
                        headers={"Authorization": f"Bearer {bearer_token}"},
                    )
                )

                self.gateway_client.start()
                mcp_tools = self.gateway_client.list_tools_sync()
                self.tools.extend(mcp_tools)
                logger.info(f"Loaded {len(mcp_tools)} tools from MCP Gateway")

            except Exception as e:
                logger.warning(f"MCP client error: {e}")
                print(f"MCP client error: {e}")

        # Initialize agent with memory hook provider if provided
        if self.memory_hook_provider:
            self.agent = Agent(
                model=self.model,
                system_prompt=self.system_prompt,
                tools=self.tools,
                hooks=[self.memory_hook_provider],
                description='K8s Diagnostics Agent',
            )
        else:
            self.agent = Agent(
                model=self.model,
                system_prompt=self.system_prompt,
                tools=self.tools,
                description='K8s Diagnostics Agent',
            )

        # Set agent state for memory hook provider
        if actor_id and session_id:
            # Store actor_id and session_id for memory hook provider access
            self.actor_id = actor_id
            self.session_id = session_id

            # Ensure agent state is properly initialized for memory hooks
            if not hasattr(self.agent, 'state'):
                self.agent.state = {}

            # Set state using multiple methods to ensure compatibility
            if hasattr(self.agent.state, 'set'):
                self.agent.state.set("actor_id", actor_id)
                self.agent.state.set("session_id", session_id)
            elif hasattr(self.agent.state, '__setitem__'):
                self.agent.state["actor_id"] = actor_id
                self.agent.state["session_id"] = session_id
            else:
                # Fallback: store in agent instance for hook provider access
                setattr(self.agent, '_actor_id', actor_id)
                setattr(self.agent, '_session_id', session_id)
                # Also create a state dict if it doesn't exist
                if not hasattr(self.agent, 'state'):
                    self.agent.state = {"actor_id": actor_id, "session_id": session_id}

            logger.info(f"Set agent state: actor_id={actor_id}, session_id={session_id}")

    async def stream(self, user_query: str):
        try:
            async for event in self.agent.stream_async(user_query):
                if "data" in event:
                    yield event["data"]
        except Exception as e:
            yield f"Error: {e}"
