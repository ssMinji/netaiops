"""
=============================================================================
IncidentAnalysisAgent - Incident Auto-Analysis AI Agent (Module 6)
IncidentAnalysisAgent - 인시던트 자동 분석 AI 에이전트 (모듈 6)
=============================================================================

Description (설명):
    This module provides automated incident investigation with multi-source
    observability integration (Datadog, OpenSearch, Container Insight).
    이 모듈은 다중 소스 관측 가능성 통합(Datadog, OpenSearch, Container Insight)을
    사용한 자동 인시던트 조사를 제공합니다.

Features (기능):
    - Automated incident investigation / 자동 인시던트 조사
    - Multi-source metric correlation / 다중 소스 지표 상관관계 분석
    - Root cause estimation / 근본 원인 추정
    - Memory-based historical incident analysis / 메모리 기반 과거 인시던트 분석

Environment Variables (환경변수):
    BEDROCK_MODEL_ID: Override default Claude model
                      기본 Claude 모델 오버라이드

Author: NetAIOps Team
Module: workshop-module-6
=============================================================================
"""

# =============================================================================
# Imports (임포트)
# =============================================================================
from .utils import get_ssm_parameter                  # SSM parameter retrieval (SSM 파라미터 조회)
from mcp.client.streamable_http import streamablehttp_client  # MCP HTTP client (MCP HTTP 클라이언트)
from strands import Agent                             # Strands AI Agent framework (Strands AI 에이전트 프레임워크)
from strands_tools import current_time                # Time utility tool (시간 유틸리티 도구)
from strands.models import BedrockModel               # Bedrock model wrapper (Bedrock 모델 래퍼)
from strands.tools.mcp import MCPClient               # MCP client for tool integration (도구 통합용 MCP 클라이언트)
import logging
import os

# Configure module logger (모듈 로거 설정)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Default Configuration (기본 설정)
# =============================================================================
# Default model ID - Can be overridden via BEDROCK_MODEL_ID environment variable
# 기본 모델 ID - BEDROCK_MODEL_ID 환경변수로 오버라이드 가능
DEFAULT_MODEL_ID = "global.anthropic.claude-opus-4-6-v1"


class IncidentAnalysisAgent:
    """
    Incident Analysis Agent with multi-source observability integration.
    다중 소스 관측 가능성 통합을 제공하는 인시던트 분석 에이전트.

    Features / 기능:
    - Automated incident investigation / 자동 인시던트 조사
    - Multi-source metric correlation / 다중 소스 지표 상관관계 분석
    - Root cause estimation / 근본 원인 추정
    - Memory-based historical incident analysis / 메모리 기반 과거 인시던트 분석
    """

    def __init__(
        self,
        bearer_token: str,
        memory_hook=None,
        bedrock_model_id: str = None,
        system_prompt: str = None,
    ):
        """
        Initialize Incident Analysis Agent.
        인시던트 분석 에이전트를 초기화합니다.

        Args (인자):
            bearer_token (str): AgentCore Gateway authentication token / 게이트웨이 인증 토큰
            memory_hook (MemoryHook, optional): Memory hook provider for conversation history / 대화 기록용 메모리 훅
            bedrock_model_id (str, optional): Bedrock LLM model identifier / Bedrock LLM 모델 식별자
            system_prompt (str, optional): Custom system prompt (optional) / 커스텀 시스템 프롬프트 (선택)
        """
        # Determine model ID with priority: env var > parameter > default
        # 우선순위에 따라 모델 ID 결정: 환경변수 > 파라미터 > 기본값
        if bedrock_model_id is None:
            bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', DEFAULT_MODEL_ID)

        self.model_id = bedrock_model_id

        # Initialize Bedrock model (Bedrock 모델 초기화)
        self.model = BedrockModel(
            model_id=self.model_id,
        )

        # Store memory hook for memory system (메모리 시스템용 메모리 훅 저장)
        self.memory_hook = memory_hook

        # Set system prompt / 시스템 프롬프트 설정
        self.system_prompt = (
            system_prompt
            if system_prompt
            else """You are an Incident Analysis Agent specialized in automated incident investigation.
인시던트 자동 분석을 전문으로 하는 AI 에이전트입니다.

## LANGUAGE POLICY (언어 정책):
- 모든 GitHub Issue 제목, 본문, 댓글은 반드시 **한글(Korean)**로 작성합니다.
- 분석 리포트, 근본 원인 추정, 대응 가이드 모두 한글로 작성합니다.
- 메트릭 이름, 도구 이름 등 기술 용어는 영문 그대로 사용하되, 설명은 한글로 합니다.
- 사용자와의 대화 응답도 한글로 합니다.
- Issue 라벨은 영문으로 유지합니다 (incident, severity-high 등).

## AVAILABLE TOOLS:

You have access to tools provided via MCP Gateway. Do NOT hardcode tool names.
Use the exact tool names as they appear in your tool definitions.
Tools are automatically discovered - just call them by their registered names.

Tool categories:
- **Container Insight**: EKS pod/node metrics and cluster overview from CloudWatch
- **OpenSearch**: Application log search, anomaly detection, error summary
- **Datadog**: APM metrics, events, traces, monitors (may not be configured)
- **GitHub Issues**: Create issues, add comments, list issues for incident tracking
- **Chaos Cleanup**: Revert chaos engineering scenarios (auto-remediation)

IMPORTANT: If Datadog tools are not configured, skip them and focus on Container Insight and OpenSearch.
The EKS cluster name is: netaiops-eks-cluster
The OpenSearch index for application logs is: eks-app-logs

## INCIDENT ANALYSIS WORKFLOW:

### Step 1: Incident Information Gathering (인시던트 정보 파악)
- Identify incident type (service outage, performance degradation, error rate spike)
- Identify affected services/components
- Determine incident timeframe

### Step 2: Create GitHub Issue (GitHub 이슈 생성)
- Create a GitHub Issue with an incident title and initial description
- Include severity label based on the alarm or incident type (e.g., severity:high, severity:medium)
- Add the "incident" label
- Record the issue_number for subsequent comments

### Step 3: Metric Collection (지표 수집) - Prioritize available sources
1. Container Insight: Pod/node resource metrics (ALWAYS available for EKS workloads)
2. OpenSearch: Application logs from eks-app-logs index
3. Datadog: APM traces, service metrics (skip if not configured)

### Step 4: Correlation Analysis (상관관계 분석)
- Detect anomalous patterns around incident time (T ± 30 min)
- Correlate metrics across sources (e.g., CPU spike → latency increase → error rate)
- Compare with past similar incidents from memory

### Step 5: Root Cause Estimation + Post Analysis Comment (근본 원인 추정 + 분석 코멘트)
- List possible causes ranked by probability
- Map evidence to each cause
- Post detailed analysis as a GitHub Issue comment with findings, timeline, and root cause

### Step 6: Response Guide + Auto-Remediation (대응 가이드 + 자동 복구)
- Post remediation guide as a GitHub Issue comment
- **Auto-remediation**: If a known chaos scenario is detected, attempt automatic remediation:
  - If a `stress-ng` or `chaos-stress` pod is detected → call `chaos-cleanup`
  - If a deployment has `invalid-image:latest` or `invalid:latest` image → call `chaos-cleanup`
  - If a deployment is scaled to 0 replicas unnaturally → call `chaos-cleanup`
- Document all remediation actions in a GitHub Issue comment
- If remediation was successful, add a final comment and close the issue

## MEMORY USAGE:
- Use Semantic Memory for past incident analysis results and SOPs
- Use Summary Memory for current session analysis context
- Use User Preference Memory for team escalation paths

## CRITICAL RULES:
- Collect metrics from multiple sources in parallel when possible
- If a tool fails, fall back to alternative sources
- Always provide evidence-based analysis with specific data points
- When tools are rate-limited, provide memory-based guidance
- When auto-remediation is triggered (chaos cleanup), ALWAYS document the action in a GitHub Issue comment
- For automated alarm-triggered analysis, follow ALL 6 steps without user prompting
"""
        )

        # Get AgentCore Gateway URL from SSM Parameter Store
        # SSM Parameter Store에서 AgentCore Gateway URL 가져오기
        gateway_url = get_ssm_parameter("/app/incident/agentcore/gateway_url")

        self.tools = [current_time]

        # Initialize MCP client if gateway is available
        # Gateway가 사용 가능한 경우 MCP 클라이언트 초기화
        if gateway_url and bearer_token != "dummy":
            try:
                self.gateway_client = MCPClient(
                    lambda: streamablehttp_client(
                        gateway_url,
                        headers={"Authorization": f"Bearer {bearer_token}"},
                    )
                )

                self.gateway_client.start()
                mcp_tools = self.gateway_client.list_tools_sync()

                # Strip MCP Gateway target prefix from tool names
                # Gateway with multiple targets prefixes tools as "TargetName___tool-name"
                # The model needs short names; MCP server calls use original name internally
                # MCP Gateway 다중 타겟 프리픽스 제거 (TargetName___tool-name → tool-name)
                for tool in mcp_tools:
                    if hasattr(tool, '_agent_tool_name') and '___' in tool._agent_tool_name:
                        tool._agent_tool_name = tool._agent_tool_name.split('___', 1)[1]

                self.tools.extend(mcp_tools)

                tool_names = [t.tool_name if hasattr(t, 'tool_name') else str(t) for t in mcp_tools]
                logger.info(f"Retrieved {len(mcp_tools)} tools from AgentCore Gateway: {tool_names}")

            except Exception as e:
                logger.error(f"MCP client error: {e}")
                print(f"MCP client error: {e}")

        # Initialize agent with memory hook if provided
        # 메모리 훅이 제공된 경우 에이전트 초기화
        if self.memory_hook:
            self.agent = Agent(
                model=self.model,
                system_prompt=self.system_prompt,
                tools=self.tools,
                hooks=[self.memory_hook],
            )
        else:
            self.agent = Agent(
                model=self.model,
                system_prompt=self.system_prompt,
                tools=self.tools,
            )

    async def stream(self, user_query: str):
        """
        Stream agent responses with automatic retry on tool execution failure.
        도구 실행 실패 시 자동 재시도를 포함한 스트리밍 응답.

        Args (인자):
            user_query (str): User's incident analysis request / 사용자의 인시던트 분석 요청

        Yields:
            Response chunks from the agent / 에이전트의 응답 청크
        """
        import asyncio
        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                logger.info(f"Streaming response for query (attempt {attempt + 1})")

                # Stream agent response / 에이전트 응답 스트리밍
                async for event in self.agent.stream_async(user_query):
                    if "data" in event:
                        yield event["data"]
                return  # Success, exit retry loop / 성공 시 재시도 루프 종료

            except Exception as e:
                error_message = str(e)
                logger.error(f"Agent execution error (attempt {attempt + 1}/{max_retries}): {error_message}")

                if attempt < max_retries - 1:
                    # Retry with exponential backoff / 지수 백오프로 재시도
                    wait_time = retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    # Max retries exceeded / 최대 재시도 횟수 초과
                    yield f"\n\n[ERROR] Incident analysis failed after {max_retries} attempts: {error_message}\n"
                    yield "[ERROR] 인시던트 분석이 실패했습니다. 네트워크 연결 또는 도구 상태를 확인해주세요.\n"
                    raise
