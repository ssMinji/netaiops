# Module 5: Kubernetes/EKS Diagnostics Agent - Architecture

## Overview

Module 5는 Amazon EKS 클러스터 진단 전문 AI 에이전트입니다. AWS Labs 공식 `eks-mcp-server`를 별도 AgentCore Runtime으로 배포하고, K8s Agent가 MCP Gateway의 `mcpServer` 타겟을 통해 연결하는 2-Runtime 아키텍처를 사용합니다.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE                                     │
│                                                                                 │
│    ┌──────────────────────────┐        ┌──────────────────────────┐              │
│    │   Streamlit Chat UI     │        │   A2A Collaborator       │              │
│    │   (k8s-chat-frontend)   │        │   (Module 3 Agent)       │              │
│    │   port: 8501            │        │                          │              │
│    └───────────┬─────────────┘        └────────────┬─────────────┘              │
│                │ HTTP                               │ A2A Protocol              │
└────────────────┼────────────────────────────────────┼───────────────────────────┘
                 │                                    │
                 ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     AUTHENTICATION (us-east-1)                                  │
│                                                                                 │
│    ┌──────────────────────────────────────────────┐                              │
│    │         Amazon Cognito User Pool             │                              │
│    │                                              │                              │
│    │  ┌──────────────┐    ┌────────────────────┐  │                              │
│    │  │ User Client  │    │  Machine Client    │  │                              │
│    │  │ (PKCE Flow)  │    │  (M2M Credentials) │  │                              │
│    │  └──────┬───────┘    └────────┬───────────┘  │                              │
│    │         │                     │              │                              │
│    │         ▼                     ▼              │                              │
│    │     OAuth2 Access Token (JWT)                │                              │
│    └──────────────────────┬───────────────────────┘                              │
│                           │                                                      │
│    ┌──────────────────────┴──────────────────────────┐                           │
│    │     SSM Parameter Store                         │                           │
│    │     /a2a/app/k8s/agentcore/*                    │                           │
│    │     - gateway_url, gateway_id                   │                           │
│    │     - cognito_provider, userpool_id             │                           │
│    │     - memory_id, user_id                        │                           │
│    │     - eks_mcp_server_endpoint                   │                           │
│    └─────────────────────────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                  AGENTCORE RUNTIME LAYER (us-east-1)                            │
│                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │                    K8s Diagnostics Agent Runtime                          │   │
│  │                    (a2a_k8s_agent_runtime)                                │   │
│  │                                                                           │   │
│  │  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐  │   │
│  │  │  main.py    │  │  agent_task.py   │  │      K8sAgent               │  │   │
│  │  │ (Entrypoint)│─▶│  (Request Router)│─▶│                              │  │   │
│  │  └─────────────┘  └──────────────────┘  │  ┌──────────────────────┐   │  │   │
│  │                                          │  │  Strands Agent       │   │  │   │
│  │  ┌─────────────────────────────────┐     │  │  + Claude Opus 4.6   │   │  │   │
│  │  │  K8sContext (ContextVar)        │     │  │  + System Prompt     │   │  │   │
│  │  │  - gateway_token               │     │  │  + MCP Tools (15+)   │   │  │   │
│  │  │  - response_queue              │     │  │  + current_time      │   │  │   │
│  │  │  - agent instance              │     │  └──────────┬───────────┘   │  │   │
│  │  │  - memory_id, actor_id         │     │             │               │  │   │
│  │  └─────────────────────────────────┘     │  ┌──────────▼───────────┐   │  │   │
│  │                                          │  │ MemoryHookProvider   │   │  │   │
│  │  ┌─────────────────────────────────┐     │  │ (STM_ONLY, 30 days) │   │  │   │
│  │  │  StreamingQueue                 │     │  └──────────────────────┘   │  │   │
│  │  │  (Async response streaming)     │     └──────────────────────────────┘  │   │
│  │  └─────────────────────────────────┘                                       │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                           │                                                      │
│                           │ Bearer Token (JWT)                                   │
│                           ▼                                                      │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │                     MCP Gateway                                           │   │
│  │                                                                           │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │  Target: mcpServer                                                 │   │   │
│  │  │  Protocol: Streamable HTTP                                         │   │   │
│  │  │  Endpoint: EKS MCP Server Runtime                                  │   │   │
│  │  └───────────────────────────────┬─────────────────────────────────────┘   │   │
│  └──────────────────────────────────┼────────────────────────────────────────┘   │
│                                     │                         d                   │
│                                     ▼                                            │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │              EKS MCP Server Runtime                                       │   │
│  │              (Standalone AgentCore Runtime)                                │   │
│  │                                                                           │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │  awslabs.eks-mcp-server (Official AWS Labs Package)                │   │   │
│  │  │                                                                     │   │   │
│  │  │  ┌─────────────┐ ┌────────────────┐ ┌──────────────────────────┐   │   │   │
│  │  │  │ K8sHandler  │ │CloudWatch      │ │ InsightsHandler          │   │   │   │
│  │  │  │             │ │Handler         │ │                          │   │   │   │
│  │  │  │ -list_k8s_  │ │-get_cloudwatch │ │ -get_eks_insights        │   │   │   │
│  │  │  │  resources  │ │ _logs          │ │ -search_eks_troubleshoot │   │   │   │
│  │  │  │ -manage_k8s │ │-get_cloudwatch │ │  _guide                  │   │   │   │
│  │  │  │  _resource  │ │ _metrics       │ └──────────────────────────┘   │   │   │
│  │  │  │ -apply_yaml │ │-get_eks_metrics│                                │   │   │
│  │  │  │ -get_pod_   │ │ _guidance      │ ┌──────────────────────────┐   │   │   │
│  │  │  │  logs       │ └────────────────┘ │ VpcConfigHandler         │   │   │   │
│  │  │  │ -get_k8s_   │                    │ -get_eks_vpc_config      │   │   │   │
│  │  │  │  events     │ ┌────────────────┐ └──────────────────────────┘   │   │   │
│  │  │  └─────────────┘ │ IAMHandler     │                                │   │   │
│  │  │                  │ -get_policies_ │ ┌──────────────────────────┐   │   │   │
│  │  │  ┌─────────────┐ │  for_role      │ │ EksStackHandler          │   │   │   │
│  │  │  │ Custom Tools│ └────────────────┘ │ -manage_eks_stacks       │   │   │   │
│  │  │  │-set_aws_    │                    └──────────────────────────┘   │   │   │
│  │  │  │ region      │ ┌────────────────┐                                │   │   │
│  │  │  │-list_eks_   │ │ EKS KB Handler │                                │   │   │
│  │  │  │ clusters    │ │-search_eks_    │                                │   │   │
│  │  │  └─────────────┘ │ troubleshoot   │                                │   │   │
│  │  │                  └────────────────┘                                │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                     │                                            │
└─────────────────────────────────────┼────────────────────────────────────────────┘
                                      │ AWS SDK (boto3) / K8s API
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      AWS INFRASTRUCTURE                                         │
│                                                                                 │
│  ┌────────────────────────────────────────────────────────────────────────┐      │
│  │  Amazon EKS Cluster (us-west-2)                                       │      │
│  │  Name: netaiops-eks-cluster  |  Version: 1.31                         │      │
│  │  Nodes: 2-3x m5.large                                                 │      │
│  │                                                                        │      │
│  │  ┌────────────────────────────────────────────────────────────────┐    │      │
│  │  │  retail-store-sample-app (namespace: default)                  │    │      │
│  │  │                                                                │    │      │
│  │  │  ┌─────┐  ┌─────────┐  ┌──────┐  ┌────────┐  ┌──────────┐   │    │      │
│  │  │  │ UI  │  │ Catalog │  │ Cart │  │ Orders │  │ Checkout │   │    │      │
│  │  │  └──┬──┘  └────┬────┘  └──┬───┘  └───┬────┘  └────┬─────┘   │    │      │
│  │  │     │          │          │           │            │          │    │      │
│  │  │     ▼          ▼          ▼           ▼            ▼          │    │      │
│  │  │  ┌──────┐  ┌───────┐  ┌──────────┐                           │    │      │
│  │  │  │MySQL │  │MySQL  │  │DynamoDB  │                           │    │      │
│  │  │  └──────┘  └───────┘  └──────────┘                           │    │      │
│  │  └────────────────────────────────────────────────────────────────┘    │      │
│  └────────────────────────────────────────────────────────────────────────┘      │
│                                                                                 │
│  ┌──────────────────────┐  ┌───────────────────┐  ┌────────────────────┐        │
│  │ CloudWatch           │  │ AgentCore Memory  │  │ Amazon ECR         │        │
│  │ - Container Insights │  │ (STM_ONLY)        │  │ - k8s agent image  │        │
│  │ - Control Plane Logs │  │ - 30 day expiry   │  │ - eks-mcp image    │        │
│  │ - Application Logs   │  │                   │  │                    │        │
│  └──────────────────────┘  └───────────────────┘  └────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
┌──────┐   1. User Query    ┌────────────────┐
│ User │ ─────────────────▶ │ Streamlit UI   │
└──────┘                    └───────┬────────┘
                                    │
                     2. PKCE OAuth2 │ Token Request
                                    ▼
                            ┌───────────────┐
                            │    Cognito    │
                            └───────┬───────┘
                                    │ 3. JWT Access Token
                                    ▼
                    ┌───────────────────────────────┐
                    │  AgentCore Runtime API         │
                    │  POST /runtimes/{arn}/         │
                    │       invocations              │
                    └───────────────┬───────────────┘
                                    │
                     4. Route to    │ K8s Agent Runtime
                                    ▼
            ┌───────────────────────────────────────────┐
            │            K8s Agent                      │
            │                                           │
            │  5. agent_task() initializes:              │
            │     - MemoryHookProvider (recall context)  │
            │     - MCPClient (connect to Gateway)       │
            │     - Strands Agent (Claude Opus 4.6)      │
            │                                           │
            │  6. Agent reasons + selects tools          │
            └──────────────────┬────────────────────────┘
                               │
                7. MCP Tool    │ Calls (Bearer Token)
                   Request     │
                               ▼
                    ┌──────────────────────┐
                    │    MCP Gateway       │
                    │  (mcpServer target)  │
                    └──────────┬───────────┘
                               │
                8. Streamable  │ HTTP
                               ▼
                ┌──────────────────────────────┐
                │   EKS MCP Server Runtime     │
                │                              │
                │  9. Execute K8s/AWS API calls │
                │     - kubectl operations     │
                │     - CloudWatch queries     │
                │     - IAM policy lookups     │
                └──────────────┬───────────────┘
                               │
                10. AWS SDK    │ / K8s API
                               ▼
                   ┌───────────────────────┐
                   │  EKS Cluster          │
                   │  (us-west-2)          │
                   └───────────────────────┘
```

---

## Diagnostic Workflows

```
                    ┌─────────────────────────┐
                    │    User Request         │
                    │  "Pod keeps crashing"   │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  1. set_aws_region      │
                    │     (us-west-2)         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  2. list_k8s_resources  │
                    │     kind=Pod            │
                    │     (find crashed pods) │
                    └────────────┬────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
          ┌──────────────┐ ┌──────────┐ ┌──────────────┐
          │3. get_k8s_   │ │4. get_   │ │5. get_cloud  │
          │   events     │ │  pod_logs│ │  watch_metrics│
          │              │ │          │ │  (CPU/Memory) │
          └──────┬───────┘ └────┬─────┘ └──────┬───────┘
                 │              │               │
                 └──────────────┼───────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │  6. search_eks_         │
                    │     troubleshoot_guide  │
                    │     (known patterns)    │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  7. Root Cause Analysis  │
                    │  + Remediation Steps    │
                    │  (kubectl commands)     │
                    └─────────────────────────┘
```

---

## Key Components

| Component | Technology | Region | Purpose |
|-----------|-----------|--------|---------|
| K8s Agent Runtime | AgentCore + Strands + Claude Opus 4.6 | us-east-1 | AI 진단 에이전트 |
| EKS MCP Server Runtime | awslabs.eks-mcp-server + FastMCP | us-east-1 | K8s/EKS API 도구 서버 |
| MCP Gateway | mcpServer target (Streamable HTTP) | us-east-1 | 도구 라우팅 |
| Cognito | OAuth2 PKCE + M2M | us-east-1 | 인증 |
| EKS Cluster | Kubernetes 1.31 (2-3 m5.large) | us-west-2 | 대상 클러스터 |
| Memory | AgentCore Memory (STM_ONLY, 30d) | us-east-1 | 세션 컨텍스트 유지 |
| SSM Parameter Store | 11+ parameters | us-east-1 | 설정 관리 |
| ECR | Docker images (linux/arm64) | us-east-1 | 컨테이너 이미지 저장 |

---

## MCP Tool Inventory (15+ tools)

| Category | Tool | Description |
|----------|------|-------------|
| Region | `set_aws_region` | AWS 리전 설정 |
| Region | `list_eks_clusters` | EKS 클러스터 목록 |
| K8s Resources | `list_k8s_resources` | K8s 리소스 조회 (Pod, Node, Deployment 등) |
| K8s Resources | `manage_k8s_resource` | K8s 리소스 CRUD |
| K8s Resources | `apply_yaml` | YAML 매니페스트 적용 |
| K8s Resources | `list_api_versions` | API 버전 목록 |
| K8s Resources | `generate_app_manifest` | Deployment+Service YAML 생성 |
| Diagnostics | `get_pod_logs` | Pod 컨테이너 로그 |
| Diagnostics | `get_k8s_events` | K8s 이벤트 |
| Diagnostics | `get_eks_insights` | EKS Insights (설정/업그레이드 이슈) |
| Diagnostics | `search_eks_troubleshoot_guide` | EKS 트러블슈팅 KB 검색 |
| CloudWatch | `get_cloudwatch_logs` | CloudWatch 로그 |
| CloudWatch | `get_cloudwatch_metrics` | CloudWatch 메트릭 |
| CloudWatch | `get_eks_metrics_guidance` | Container Insights 메트릭 가이드 |
| VPC | `get_eks_vpc_config` | VPC 구성 정보 |
| IAM | `get_policies_for_role` | IAM 역할 정책 |
| Stack | `manage_eks_stacks` | CloudFormation 스택 관리 |
