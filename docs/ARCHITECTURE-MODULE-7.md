# Module 7: Istio Service Mesh Diagnostics Agent - Architecture

## Overview

Module 7은 Amazon EKS 위의 Istio 서비스 메시 진단 전문 AI 에이전트입니다. EKS MCP Server (K8s 리소스 + Istio CRD 접근)와 Istio Prometheus Lambda (AMP 메트릭 조회)를 **하이브리드 MCP Gateway**로 결합하여 종합적인 메시 분석을 수행합니다.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE                                     │
│                                                                                 │
│    ┌──────────────────────────┐                                                 │
│    │   Streamlit Chat UI     │                                                  │
│    │   or A2A Collaborator   │                                                  │
│    └───────────┬─────────────┘                                                  │
│                │ HTTP + Bearer Token                                             │
└────────────────┼────────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     AUTHENTICATION (us-east-1)                                  │
│                                                                                 │
│    ┌──────────────────────────────────────────────┐                              │
│    │         Amazon Cognito User Pool             │                              │
│    │         OAuth2 (PKCE / M2M)                  │                              │
│    └──────────────────────┬───────────────────────┘                              │
│                           │ JWT Access Token                                     │
│    ┌──────────────────────┴──────────────────────────┐                           │
│    │     SSM Parameter Store                         │                           │
│    │     /app/istio/agentcore/*                      │                           │
│    │     - gateway_url, gateway_id                   │                           │
│    │     - cognito_provider, cognito_token_url       │                           │
│    │     - memory_id, user_id                        │                           │
│    │     - amp_workspace_id, amp_endpoint            │                           │
│    └─────────────────────────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                  AGENTCORE RUNTIME LAYER (us-east-1)                            │
│                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │                   Istio Mesh Agent Runtime                                │   │
│  │                   (istio_mesh_agent_runtime)                              │   │
│  │                                                                           │   │
│  │  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐  │   │
│  │  │  main.py    │  │  agent_task.py   │  │     IstioMeshAgent          │  │   │
│  │  │ (Entrypoint)│─▶│  (Request Router)│─▶│                              │  │   │
│  │  └─────────────┘  └──────────────────┘  │  ┌──────────────────────┐   │  │   │
│  │                                          │  │  Strands Agent       │   │  │   │
│  │  ┌─────────────────────────────────┐     │  │  + Claude Opus 4.6   │   │  │   │
│  │  │  IstioContext (ContextVar)      │     │  │  + System Prompt     │   │  │   │
│  │  │  - gateway_token               │     │  │  + MCP Tools (20+)   │   │  │   │
│  │  │  - response_queue              │     │  │  + current_time      │   │  │   │
│  │  │  - agent, memory_id, actor_id  │     │  │  + Retry (3x, exp)   │   │  │   │
│  │  └─────────────────────────────────┘     │  └──────────────────────┘   │  │   │
│  │                                          │                              │  │   │
│  │  ┌─────────────────────────────────┐     │  ┌──────────────────────┐   │  │   │
│  │  │  StreamingQueue                 │     │  │ MemoryHookProvider   │   │  │   │
│  │  │  (Async response chunks)        │     │  │ (STM_ONLY, 30 days) │   │  │   │
│  │  └─────────────────────────────────┘     │  └──────────────────────┘   │  │   │
│  │                                          └──────────────────────────────┘  │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                           │                                                      │
│                           │ Bearer Token (JWT)                                   │
│                           ▼                                                      │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │                  HYBRID MCP GATEWAY                                        │   │
│  │                  (Two target types in one gateway)                         │   │
│  │                                                                           │   │
│  │  ┌─────────────────────────────┐  ┌─────────────────────────────────────┐ │   │
│  │  │  Target 1: mcpServer        │  │  Target 2: Lambda                   │ │   │
│  │  │  (Streamable HTTP)          │  │  (AWS Lambda Invoke)                │ │   │
│  │  │                             │  │                                     │ │   │
│  │  │  EKS MCP Server Runtime     │  │  istio-prometheus Lambda            │ │   │
│  │  │  ┌───────────────────────┐  │  │  ┌───────────────────────────────┐  │ │   │
│  │  │  │ K8s Resources:       │  │  │  │ Istio Metrics:               │  │ │   │
│  │  │  │ - set_aws_region     │  │  │  │ - istio-query-workload-      │  │ │   │
│  │  │  │ - list_eks_clusters  │  │  │  │   metrics                    │  │ │   │
│  │  │  │ - list_k8s_resources │  │  │  │ - istio-query-service-       │  │ │   │
│  │  │  │ - manage_k8s_resource│  │  │  │   topology                   │  │ │   │
│  │  │  │ - get_pod_logs       │  │  │  │ - istio-query-tcp-metrics    │  │ │   │
│  │  │  │ - get_k8s_events     │  │  │  │ - istio-query-control-       │  │ │   │
│  │  │  │ - apply_yaml         │  │  │  │   plane-health               │  │ │   │
│  │  │  │ - ...                │  │  │  │ - istio-query-proxy-         │  │ │   │
│  │  │  │                      │  │  │  │   resource-usage             │  │ │   │
│  │  │  │ Istio CRDs:         │  │  │  └───────────────────────────────┘  │ │   │
│  │  │  │ - VirtualService    │  │  │                 │                    │ │   │
│  │  │  │ - DestinationRule   │  │  │                 │ SigV4 Auth         │ │   │
│  │  │  │ - PeerAuthentication│  │  │                 ▼                    │ │   │
│  │  │  │ - Gateway           │  │  │  ┌───────────────────────────────┐  │ │   │
│  │  │  │ - ServiceEntry      │  │  │  │ Amazon Managed Prometheus    │  │ │   │
│  │  │  └───────────────────────┘  │  │  │ (AMP)                       │  │ │   │
│  │  │           │                 │  │  │ PromQL query_range / query  │  │ │   │
│  │  │           │ K8s API         │  │  └───────────────────────────────┘  │ │   │
│  │  │           ▼                 │  │                                     │ │   │
│  │  │  ┌───────────────────────┐  │  └─────────────────────────────────────┘ │   │
│  │  │  │ EKS Cluster          │  │                                           │   │
│  │  │  │ (us-west-2)          │  │                                           │   │
│  │  │  └───────────────────────┘  │                                           │   │
│  │  └─────────────────────────────┘                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      EKS CLUSTER (us-west-2)                                    │
│                      netaiops-eks-cluster | K8s 1.31                            │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │  Istio Control Plane (namespace: istio-system)                           │    │
│  │                                                                          │    │
│  │  ┌──────────────────┐  ┌──────────────────────────────────────────────┐  │    │
│  │  │  istiod           │  │  Prometheus Scraper → AMP                   │  │    │
│  │  │  - Pilot (xDS)   │  │  - istio_requests_total                     │  │    │
│  │  │  - Config sync   │  │  - istio_request_duration_milliseconds      │  │    │
│  │  │  - mTLS CA       │  │  - istio_tcp_connections_opened/closed      │  │    │
│  │  └──────────────────┘  │  - pilot_proxy_convergence_time             │  │    │
│  │                         │  - pilot_xds_push_errors                    │  │    │
│  │                         │  - container_memory/cpu (istio-proxy)       │  │    │
│  │                         └──────────────────────────────────────────────┘  │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │  Workload 1: retail-store-sample-app (namespace: default)                │    │
│  │  (현재 Istio 사이드카 미주입 상태)                                       │    │
│  │                                                                          │    │
│  │  ┌─────┐  ┌─────────┐  ┌──────┐  ┌────────┐  ┌──────────┐              │    │
│  │  │ UI  │  │ Catalog │  │ Cart │  │ Orders │  │ Checkout │              │    │
│  │  └─────┘  └─────────┘  └──────┘  └────────┘  └──────────┘              │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │  Workload 2: Bookinfo (namespace: istio-sample)                          │    │
│  │  (Istio 사이드카 주입, mTLS STRICT)                                      │    │
│  │                                                                          │    │
│  │              ┌──────────────────┐                                        │    │
│  │              │   productpage    │                                        │    │
│  │              │   (v1)           │                                        │    │
│  │              └─────┬──────┬─────┘                                        │    │
│  │                    │      │                                              │    │
│  │           ┌────────┘      └────────┐                                    │    │
│  │           ▼                        ▼                                    │    │
│  │  ┌──────────────┐     ┌──────────────────────────────────┐              │    │
│  │  │   details    │     │          reviews                 │              │    │
│  │  │   (v1)       │     │  ┌────┐  ┌────┐  ┌────┐         │              │    │
│  │  └──────────────┘     │  │ v1 │  │ v2 │  │ v3 │         │              │    │
│  │                        │  └────┘  └──┬─┘  └──┬─┘         │              │    │
│  │                        └─────────────┼───────┼────────────┘              │    │
│  │                                      │       │                          │    │
│  │                                      ▼       ▼                          │    │
│  │                              ┌──────────────────┐                       │    │
│  │                              │    ratings (v1)  │                       │    │
│  │                              └──────────────────┘                       │    │
│  │                                                                          │    │
│  │  Istio CRDs Applied:                                                     │    │
│  │  ┌──────────────────┐ ┌──────────────────┐ ┌────────────────────────┐   │    │
│  │  │ VirtualService   │ │ DestinationRule  │ │ PeerAuthentication     │   │    │
│  │  │ (weighted route) │ │ (v1/v2/v3 subset)│ │ (STRICT mTLS)         │   │    │
│  │  └──────────────────┘ └──────────────────┘ └────────────────────────┘   │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │  Fault Injection Scenarios (testing)                                      │    │
│  │                                                                          │    │
│  │  ┌────────────────────────┐  ┌────────────────────────┐                  │    │
│  │  │ fault-delay-reviews    │  │ fault-abort-ratings    │                  │    │
│  │  │ 50% requests → 7s     │  │ 50% requests → HTTP 500│                  │    │
│  │  │ delay                  │  │                        │                  │    │
│  │  └────────────────────────┘  └────────────────────────┘                  │    │
│  │  ┌────────────────────────┐                                              │    │
│  │  │ circuit-breaker        │                                              │    │
│  │  │ max connections/       │                                              │    │
│  │  │ requests/pending       │                                              │    │
│  │  └────────────────────────┘                                              │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Hybrid MCP Gateway Architecture

```
                    ┌────────────────────────────────┐
                    │       IstioMeshAgent            │
                    │   (Strands + Claude Opus 4.6)   │
                    └───────────────┬────────────────┘
                                    │
                          Bearer Token (JWT)
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────────┐
        │                    MCP Gateway                         │
        │            (Hybrid: 2 target types)                    │
        │                                                        │
        │    Tool name prefix stripping:                         │
        │    "TargetName___tool-name" → "tool-name"              │
        └──────────────┬──────────────────────┬─────────────────┘
                       │                      │
          ┌────────────┘                      └────────────┐
          │                                                │
          ▼                                                ▼
┌─────────────────────────┐              ┌─────────────────────────────┐
│  Target: mcpServer      │              │  Target: Lambda             │
│  Protocol: Streamable   │              │  Invocation: AWS Lambda     │
│  HTTP                   │              │                             │
│                         │              │  lambda-istio-prometheus    │
│  EKS MCP Server         │              │                             │
│  (AgentCore Runtime)    │              │  ┌───────────────────────┐  │
│                         │              │  │ SigV4 Auth → AMP      │  │
│  K8s API Tools:         │              │  │                       │  │
│  ├─ set_aws_region      │              │  │ PromQL Queries:       │  │
│  ├─ list_eks_clusters   │              │  │ ├─ istio_requests_    │  │
│  ├─ list_k8s_resources  │              │  │ │  total (rate/error) │  │
│  ├─ manage_k8s_resource │              │  │ ├─ istio_request_     │  │
│  ├─ get_pod_logs        │              │  │ │  duration (P50/P99) │  │
│  ├─ get_k8s_events      │              │  │ ├─ istio_tcp_*        │  │
│  ├─ apply_yaml          │              │  │ ├─ pilot_proxy_*      │  │
│  └─ ...                 │              │  │ └─ container_*        │  │
│                         │              │  │   (istio-proxy)       │  │
│  Istio CRD Access:      │              │  └───────────────────────┘  │
│  ├─ VirtualService      │              │                             │
│  ├─ DestinationRule     │              │  5 Tool Endpoints:          │
│  ├─ PeerAuthentication  │              │  ├─ istio-query-workload-   │
│  ├─ Gateway             │              │  │  metrics                 │
│  └─ ServiceEntry        │              │  ├─ istio-query-service-    │
│         │               │              │  │  topology                │
│         │               │              │  ├─ istio-query-tcp-metrics │
│         ▼               │              │  ├─ istio-query-control-    │
│  ┌──────────────┐       │              │  │  plane-health            │
│  │ EKS Cluster  │       │              │  └─ istio-query-proxy-      │
│  │ K8s API      │       │              │     resource-usage          │
│  └──────────────┘       │              │         │                   │
│                         │              │         ▼                   │
└─────────────────────────┘              │  ┌──────────────────────┐   │
                                         │  │  Amazon Managed      │   │
                                         │  │  Prometheus (AMP)    │   │
                                         │  │  /api/v1/query_range │   │
                                         │  │  /api/v1/query       │   │
                                         │  └──────────────────────┘   │
                                         └─────────────────────────────┘
```

---

## Diagnostic Workflows

### 1. Service Connectivity Failure (서비스 연결 실패 진단)

```
┌─────────────────────────────────────────────────────────────────┐
│  "productpage에서 reviews 서비스 호출이 실패합니다"             │
└────────────────────────────┬────────────────────────────────────┘
                             │
      ┌──────────────────────┼──────────────────────┐
      │                      │                      │
      ▼                      ▼                      ▼
┌──────────────┐  ┌────────────────────┐  ┌────────────────────┐
│ istio-query- │  │ list_k8s_resources │  │ list_k8s_resources │
│ service-     │  │ kind=Pod           │  │ kind=VirtualService│
│ topology     │  │ (sidecar check)    │  │ + DestinationRule  │
└──────┬───────┘  └─────────┬──────────┘  └─────────┬──────────┘
       │                    │                        │
       └────────────────────┼────────────────────────┘
                            │
                            ▼
               ┌───────────────────────────┐
               │ list_k8s_resources        │
               │ kind=PeerAuthentication   │
               │ (mTLS mode check)         │
               └─────────────┬─────────────┘
                             │
                             ▼
               ┌───────────────────────────┐
               │ get_pod_logs              │
               │ container=istio-proxy     │
               │ (Envoy error logs)        │
               └─────────────┬─────────────┘
                             │
                             ▼
               ┌───────────────────────────┐
               │ Root Cause + Remediation  │
               │ (한글 리포트)             │
               └───────────────────────────┘
```

### 2. mTLS Audit (mTLS 감사)

```
┌──────────────────────────────────────────────────────────────┐
│  "클러스터 전체 mTLS 상태를 점검해주세요"                     │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
               ┌─────────────────────────────────┐
               │ list_k8s_resources              │
               │ kind=PeerAuthentication         │
               │ apiVersion=security.istio.io/   │
               │ v1beta1 (all namespaces)        │
               └─────────────┬───────────────────┘
                             │
                             ▼
               ┌─────────────────────────────────┐
               │ Analyze mTLS mode per namespace  │
               │ - STRICT (recommended)           │
               │ - PERMISSIVE (risk)              │
               │ - DISABLE (critical risk)        │
               └─────────────┬───────────────────┘
                             │
                             ▼
               ┌─────────────────────────────────┐
               │ list_k8s_resources kind=Pod     │
               │ (check istio-proxy container    │
               │  in each pod's containers)      │
               └─────────────┬───────────────────┘
                             │
                             ▼
               ┌─────────────────────────────────┐
               │ Security Assessment (한글)      │
               │ - 사이드카 미주입 Pod 목록       │
               │ - PERMISSIVE 네임스페이스 경고   │
               │ - STRICT 전환 가이드             │
               └─────────────────────────────────┘
```

### 3. Latency Hotspot Detection (지연 핫스팟 탐지)

```
┌──────────────────────────────────────────────────────────────┐
│  "서비스 메시 전체에서 느린 서비스를 찾아주세요"              │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
               ┌─────────────────────────────────┐
               │ istio-query-workload-metrics     │
               │ (all namespaces, P99 scan)       │
               └─────────────┬───────────────────┘
                             │
                             ▼
               ┌─────────────────────────────────┐
               │ Identify slow services           │
               │ (P99 > threshold)                │
               └─────────────┬───────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
   ┌────────────────┐ ┌──────────────┐ ┌──────────────────┐
   │ istio-query-   │ │ list_k8s_    │ │ istio-query-     │
   │ service-       │ │ resources    │ │ proxy-resource-  │
   │ topology       │ │ kind=Virtual │ │ usage            │
   │ (trace path)   │ │ Service      │ │ (Envoy overhead) │
   └───────┬────────┘ │ (fault       │ └───────┬──────────┘
           │          │  injection?) │         │
           │          └──────┬───────┘         │
           │                 │                 │
           └─────────────────┼─────────────────┘
                             │
                             ▼
               ┌─────────────────────────────────┐
               │ Latency Cause Analysis (한글)   │
               │ - 네트워크 지연                  │
               │ - 사이드카 오버헤드              │
               │ - 애플리케이션 처리 시간         │
               │ - Fault injection 규칙           │
               └─────────────────────────────────┘
```

---

## Key Components

| Component | Technology | Region | Purpose |
|-----------|-----------|--------|---------|
| Istio Agent Runtime | AgentCore + Strands + Claude Opus 4.6 | us-east-1 | Istio 메시 진단 에이전트 |
| EKS MCP Server Runtime | awslabs.eks-mcp-server + FastMCP | us-east-1 | K8s/Istio CRD 도구 서버 |
| istio-prometheus Lambda | Python + SigV4Auth | us-east-1 | AMP 메트릭 쿼리 |
| MCP Gateway | Hybrid (mcpServer + Lambda) | us-east-1 | 도구 라우팅 |
| Cognito | OAuth2 | us-east-1 | 인증 |
| EKS Cluster | K8s 1.31 + Istio 1.20+ | us-west-2 | 대상 클러스터 |
| Amazon Managed Prometheus | PromQL API | us-west-2 | Istio 메트릭 저장/쿼리 |
| Memory | AgentCore Memory (STM_ONLY, 30d) | us-east-1 | 세션 컨텍스트 유지 |
| SSM Parameter Store | /app/istio/agentcore/* | us-east-1 | 설정 관리 |

---

## MCP Tool Inventory (20+ tools)

### EKS MCP Server Tools (via mcpServer target)

| Tool | Description | Istio Use Case |
|------|-------------|---------------|
| `set_aws_region` | AWS 리전 설정 | 클러스터 리전 지정 |
| `list_eks_clusters` | EKS 클러스터 목록 | 클러스터 탐색 |
| `list_k8s_resources` | K8s 리소스 조회 | VirtualService, DestinationRule, PeerAuthentication, Gateway, ServiceEntry 조회 |
| `manage_k8s_resource` | K8s 리소스 CRUD | Istio CRD 상세 조회 (operation="read") |
| `get_pod_logs` | Pod 로그 조회 | Envoy sidecar 로그 (container=istio-proxy), istiod 로그 |
| `get_k8s_events` | K8s 이벤트 | Pod/Deployment 이벤트 |
| `apply_yaml` | YAML 적용 | Istio CRD 적용 |
| `get_cloudwatch_logs` | CloudWatch 로그 | EKS 컨트롤 플레인 로그 |
| `get_cloudwatch_metrics` | CloudWatch 메트릭 | Container Insights |
| `get_eks_vpc_config` | VPC 구성 | 네트워크 분석 |

### Istio Prometheus Tools (via Lambda target)

| Tool | PromQL Query | Description |
|------|-------------|-------------|
| `istio-query-workload-metrics` | `istio_requests_total`, `istio_request_duration_milliseconds_bucket` | 워크로드별 RED 메트릭 (요청률, 에러율, P50/P99 지연) |
| `istio-query-service-topology` | `istio_requests_total` by src/dst | 서비스 간 트래픽 토폴로지 (소스→대상, 응답코드, 요청률) |
| `istio-query-tcp-metrics` | `istio_tcp_connections_*`, `istio_tcp_*_bytes_total` | TCP 연결/바이트 메트릭 |
| `istio-query-control-plane-health` | `pilot_proxy_convergence_time`, `pilot_xds_push_errors`, `pilot_xds` | istiod 상태 (xDS push 지연, 에러, 연결된 프록시 수) |
| `istio-query-proxy-resource-usage` | `container_memory_working_set_bytes`, `container_cpu_usage_seconds_total` (istio-proxy) | Envoy 사이드카 CPU/메모리 사용량 |

---

## Target Workloads

### Bookinfo (istio-sample namespace)

```
                         ┌─────────────────────┐
                         │    Istio Gateway     │
                         │ (bookinfo-gateway)   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   productpage (v1)   │
                         │   [istio-proxy]      │
                         └─────┬──────────┬─────┘
                               │          │
                    ┌──────────┘          └──────────────┐
                    ▼                                    ▼
          ┌─────────────────┐              ┌──────────────────────────────┐
          │  details (v1)   │              │      reviews                 │
          │  [istio-proxy]  │              │                              │
          └─────────────────┘              │  VirtualService weights:     │
                                           │  v1: 33% │ v2: 33% │ v3: 34%│
                                           │                              │
                                           │  DestinationRule subsets:    │
                                           │  v1 (version: v1)           │
                                           │  v2 (version: v2) ──┐       │
                                           │  v3 (version: v3) ──┤       │
                                           └──────────────────────┤──────┘
                                                                  │
                                                                  ▼
                                                   ┌──────────────────────┐
                                                   │   ratings (v1)      │
                                                   │   [istio-proxy]     │
                                                   └──────────────────────┘

          PeerAuthentication: mode=STRICT (mutual TLS enforced)
```

### Fault Injection Scenarios

```
┌─────────────────────────────────────────────────────────────┐
│  fault-delay-reviews.yaml                                   │
│  VirtualService: reviews                                    │
│  Match: 50% of requests                                     │
│  Action: fixedDelay = 7s                                    │
│  Effect: P99 latency spike on reviews                       │
├─────────────────────────────────────────────────────────────┤
│  fault-abort-ratings.yaml                                   │
│  VirtualService: ratings                                    │
│  Match: 50% of requests                                     │
│  Action: httpStatus = 500                                   │
│  Effect: Error rate spike on ratings                        │
├─────────────────────────────────────────────────────────────┤
│  circuit-breaker.yaml                                       │
│  DestinationRule: reviews                                   │
│  outlierDetection + connectionPool limits                   │
│  Effect: Connection throttling under load                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Language Policy

모든 출력물은 한국어(한글)로 작성됩니다:
- 진단 분석 리포트
- 근본 원인 추정
- 대응 가이드 (kubectl 명령어 포함)
- 사용자 대화 응답

기술 용어(VirtualService, DestinationRule, PeerAuthentication, PromQL 등)는 영문 유지.
