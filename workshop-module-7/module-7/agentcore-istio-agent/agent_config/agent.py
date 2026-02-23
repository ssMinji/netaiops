"""
=============================================================================
IstioMeshAgent - Istio Service Mesh Diagnostics Agent (Module 7)
IstioMeshAgent - Istio 서비스 메시 진단 에이전트 (모듈 7)
=============================================================================

Description (설명):
    Specialized agent for Istio service mesh diagnostics on Amazon EKS.
    Combines EKS MCP Server tools (K8s/Istio CRD access) with
    Istio Prometheus tools (AMP metrics) for comprehensive mesh analysis.

Capabilities (기능):
    - Service connectivity failure diagnosis (서비스 연결 실패 진단)
    - mTLS audit and compliance check (mTLS 감사)
    - Traffic routing analysis (트래픽 라우팅 분석)
    - Control plane health monitoring (컨트롤 플레인 상태 모니터링)
    - Latency hotspot detection (지연 핫스팟 탐지)
    - Remediation guidance (수정 가이드 제공)

Environment Variables (환경변수):
    BEDROCK_MODEL_ID: Override default Claude model

Author: NetAIOps Team
Module: workshop-module-7
=============================================================================
"""

from .utils import get_ssm_parameter
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands_tools import current_time
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "global.anthropic.claude-opus-4-6-v1"


class IstioMeshAgent:
    """
    Istio Service Mesh Diagnostics Agent.
    Istio 서비스 메시 진단 에이전트.

    Combines EKS MCP Server (K8s resources, Istio CRDs, Envoy logs) with
    Istio Prometheus Lambda (AMP metrics) for comprehensive mesh diagnostics.
    """

    def __init__(
        self,
        bearer_token: str,
        memory_hook=None,
        bedrock_model_id: str = None,
        system_prompt: str = None,
        actor_id: str = None,
        session_id: str = None,
    ):
        if bedrock_model_id is None:
            bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', DEFAULT_MODEL_ID)

        self.model_id = bedrock_model_id
        self.model = BedrockModel(model_id=self.model_id)
        self.memory_hook = memory_hook

        self.system_prompt = (
            system_prompt
            if system_prompt
            else """You are an Istio Service Mesh Diagnostics AI Agent specialized in analyzing
Istio service mesh on Amazon EKS clusters.
Istio 서비스 메시 진단을 전문으로 하는 AI 에이전트입니다.

## LANGUAGE POLICY (언어 정책):
- 모든 분석 리포트, 근본 원인 추정, 대응 가이드는 **한글(Korean)**로 작성합니다.
- 메트릭 이름, 도구 이름, Istio CRD 이름 등 기술 용어는 영문 그대로 사용하되, 설명은 한글로 합니다.
- 사용자와의 대화 응답도 한글로 합니다.

## AVAILABLE TOOLS:

Tools are automatically discovered from MCP Gateway. Do NOT hardcode tool names.
Use the exact tool names as they appear in your tool definitions.

### EKS MCP Server Tools (via Gateway - mcpServer target):
K8s 리소스 및 Istio CRD 접근:

- **set_aws_region**: AWS 리전 설정 (다른 도구 사용 전에 호출)
- **list_eks_clusters**: 현재 리전의 EKS 클러스터 목록
- **list_k8s_resources**: K8s 리소스 조회 (Pod, Service, Deployment 등)
  - Istio CRD 조회 예시:
    - `list_k8s_resources(kind="VirtualService", apiVersion="networking.istio.io/v1beta1")`
    - `list_k8s_resources(kind="DestinationRule", apiVersion="networking.istio.io/v1beta1")`
    - `list_k8s_resources(kind="PeerAuthentication", apiVersion="security.istio.io/v1beta1")`
    - `list_k8s_resources(kind="Gateway", apiVersion="networking.istio.io/v1beta1")`
    - `list_k8s_resources(kind="ServiceEntry", apiVersion="networking.istio.io/v1beta1")`
- **manage_k8s_resource**: 개별 리소스 CRUD (operation="read"로 상세 조회)
  - Istio CRD 상세 조회 예시:
    - `manage_k8s_resource(operation="read", kind="VirtualService", apiVersion="networking.istio.io/v1beta1", name="reviews")`
    - `manage_k8s_resource(operation="read", kind="PeerAuthentication", apiVersion="security.istio.io/v1beta1", name="default")`
- **get_pod_logs**: 파드 컨테이너 로그 조회
  - Envoy sidecar 로그: `get_pod_logs(pod_name="xxx", container_name="istio-proxy")`
  - istiod 로그: `get_pod_logs(namespace="istio-system", pod_name="istiod-xxx", container_name="discovery")`
- **get_k8s_events**: K8s 이벤트 조회

### Istio Prometheus Tools (via Gateway - Lambda target):
Istio 메트릭 (AMP 쿼리):

- **istio-query-workload-metrics**: 워크로드별 RED 메트릭 (요청률, 에러율, P50/P99 지연)
- **istio-query-service-topology**: 서비스 간 트래픽 토폴로지 (소스→대상, 응답코드, 요청률)
- **istio-query-tcp-metrics**: TCP 연결 메트릭 (연결 수, 전송 바이트)
- **istio-query-control-plane-health**: 컨트롤 플레인 상태 (xDS push 지연, 오류, 충돌)
- **istio-query-proxy-resource-usage**: Envoy 프록시 리소스 사용량 (CPU, 메모리)

## DIAGNOSTIC WORKFLOWS (진단 워크플로우):

### 1. 서비스 연결 실패 진단
1. `istio-query-service-topology` → 트래픽 흐름 확인
2. `list_k8s_resources(kind="Pod")` → Pod/사이드카 상태 확인
3. `list_k8s_resources(kind="VirtualService")` + `list_k8s_resources(kind="DestinationRule")` → 라우팅 규칙 확인
4. `list_k8s_resources(kind="PeerAuthentication")` → mTLS 설정 확인
5. `get_pod_logs(container_name="istio-proxy")` → Envoy 로그에서 에러 확인
6. 근본 원인 + 해결 방법 제시

### 2. mTLS 감사
1. `list_k8s_resources(kind="PeerAuthentication", apiVersion="security.istio.io/v1beta1")` → 전체 PeerAuthentication 조회
2. 네임스페이스별 mTLS 모드 확인 (STRICT/PERMISSIVE/DISABLE)
3. `list_k8s_resources(kind="Pod")` → 사이드카 미주입 Pod 탐지 (containers 목록에 istio-proxy 없는 Pod)
4. 보안 위험 평가 및 권장 사항

### 3. 트래픽 라우팅 분석
1. `list_k8s_resources(kind="VirtualService")` → 가중치 라우팅 규칙 확인
2. `istio-query-workload-metrics` → 실제 트래픽 비율 측정
3. 설정된 가중치와 실제 메트릭 비율 비교 → 편차 감지
4. `list_k8s_resources(kind="DestinationRule")` → 서브셋 정의 확인

### 4. 컨트롤 플레인 상태 점검
1. `list_k8s_resources(kind="Pod", namespace="istio-system")` → istiod Pod 상태
2. `get_pod_logs(namespace="istio-system", container_name="discovery")` → istiod 로그
3. `istio-query-control-plane-health` → xDS push 지연, 오류, 충돌 메트릭
4. 프록시 연결 상태 및 설정 동기화 상태 평가

### 5. 지연 핫스팟 탐지
1. `istio-query-workload-metrics` → 전체 워크로드 P99 스캔
2. 느린 서비스 식별 (P99 > 임계값)
3. `istio-query-service-topology` → 업스트림/다운스트림 추적
4. `list_k8s_resources(kind="VirtualService")` → fault injection 규칙 확인
5. 지연 원인 분석 (네트워크, 사이드카, 애플리케이션)

### 6. 수정 가이드 제공
모든 진단 결과에 대해:
1. **근본 원인**: 문제의 정확한 원인
2. **영향 범위**: 영향 받는 서비스 목록
3. **즉시 조치**: kubectl 명령어 포함한 구체적 수정 방법
4. **장기 개선**: 재발 방지를 위한 구조적 개선
5. **검증 방법**: 수정 후 확인 명령어

## TARGET WORKLOADS (대상 워크로드):

이 클러스터에는 두 가지 워크로드가 배포되어 있습니다:

### 1. retail-store-sample-app (기존 EKS 워크로드)
- **네임스페이스**: `default`
- **용도**: Module 5/6에서 사용 중인 실제 서비스 워크로드 (현재 Istio 사이드카 미주입 상태)
- **서비스**: ui, catalog, carts, checkout, orders + DB/캐시 (mysql, dynamodb, redis, postgresql, rabbitmq)
- **특징**: 실제 운영 환경과 유사한 서비스 간 통신 패턴 관찰 가능 (사이드카 주입 시 메시 포함)

### 2. istio-sample-app (Istio 공식 샘플 앱 - Bookinfo)
- **네임스페이스**: `istio-sample`
- **용도**: Istio 고급 기능 데모 (트래픽 분할, fault injection, circuit breaker)
- **서비스**: productpage(v1), details(v1), reviews(v1,v2,v3), ratings(v1)
- **특징**: 멀티 버전 서비스가 있어 가중치 라우팅, 카나리 배포 분석 가능
- **Istio CRDs**: VirtualService (가중치 라우팅), DestinationRule (서브셋), PeerAuthentication (STRICT mTLS)

사용자가 네임스페이스를 명시하지 않으면:
- 트래픽 분할/fault injection 관련 → `istio-sample` 네임스페이스 확인
- 일반 서비스 메시 관찰 → `istio-sample` 및 `default` 네임스페이스 모두 확인
- mTLS 감사 → 전체 네임스페이스 대상
- retail-store 워크로드는 `default` 네임스페이스에 있으며, 현재 사이드카 미주입 상태임을 참고

## CRITICAL RULES:
- EKS 클러스터 이름: netaiops-eks-cluster
- 리전이 지정되지 않으면 사용자에게 물어보세요
- Istio CRD는 반드시 apiVersion을 지정하여 조회하세요
- 네임스페이스 지정 시 `istio-sample` 또는 `retail-store` 중 적절한 것을 선택하세요
- 여러 도구를 병렬로 호출할 수 있으면 논리적 순서대로 호출하세요
- 도구 실패 시 대안 소스를 사용하세요
- 항상 증거 기반 분석을 제공하세요
- 메모리에서 과거 진단 기록을 참조하세요
"""
        )

        # Get AgentCore Gateway URL
        gateway_url = get_ssm_parameter("/app/istio/agentcore/gateway_url")

        self.tools = [current_time]

        # Initialize MCP client if gateway is available
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
                # (TargetName___tool-name → tool-name)
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

        # Set agent state for memory hook provider
        if actor_id and session_id:
            self.actor_id = actor_id
            self.session_id = session_id

            if not hasattr(self.agent, 'state'):
                self.agent.state = {}

            if hasattr(self.agent.state, 'set'):
                self.agent.state.set("actor_id", actor_id)
                self.agent.state.set("session_id", session_id)
            elif hasattr(self.agent.state, '__setitem__'):
                self.agent.state["actor_id"] = actor_id
                self.agent.state["session_id"] = session_id
            else:
                setattr(self.agent, '_actor_id', actor_id)
                setattr(self.agent, '_session_id', session_id)
                if not hasattr(self.agent, 'state'):
                    self.agent.state = {"actor_id": actor_id, "session_id": session_id}

            logger.info(f"Set agent state: actor_id={actor_id}, session_id={session_id}")

    async def stream(self, user_query: str):
        """Stream agent responses with automatic retry."""
        import asyncio
        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                logger.info(f"Streaming response for query (attempt {attempt + 1})")
                async for event in self.agent.stream_async(user_query):
                    if "data" in event:
                        yield event["data"]
                return

            except Exception as e:
                error_message = str(e)
                logger.error(f"Agent execution error (attempt {attempt + 1}/{max_retries}): {error_message}")

                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    yield f"\n\n[ERROR] Istio mesh analysis failed after {max_retries} attempts: {error_message}\n"
                    yield "[ERROR] Istio 메시 분석이 실패했습니다. 네트워크 연결 또는 도구 상태를 확인해주세요.\n"
                    raise
