# Module 6: Incident Auto-Analysis Agent - Architecture

## Overview

Module 6는 CloudWatch 알람 기반 자동 인시던트 분석 에이전트입니다. SNS 알림을 수신한 Lambda가 AgentCore Runtime을 자동 호출하며, 에이전트는 Container Insight, OpenSearch, Datadog, GitHub 등 6개 Lambda MCP 도구를 사용하여 근본 원인 분석과 자동 복구까지 수행합니다.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        TRIGGER LAYER (us-west-2)                                │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐     │
│  │  Amazon EKS Cluster (netaiops-eks-cluster)                             │     │
│  │                                                                         │     │
│  │  ┌──────────────────────────────────────────────────────────────────┐   │     │
│  │  │  retail-store-sample-app (namespace: default)                    │   │     │
│  │  │  ┌─────┐ ┌─────────┐ ┌──────┐ ┌────────┐ ┌──────────┐          │   │     │
│  │  │  │ UI  │ │ Catalog │ │ Cart │ │ Orders │ │ Checkout │          │   │     │
│  │  │  └─────┘ └─────────┘ └──────┘ └────────┘ └──────────┘          │   │     │
│  │  └──────────────────────────────────────────────────────────────────┘   │     │
│  │                          │                                              │     │
│  │                          │ Metrics / Logs                               │     │
│  │                          ▼                                              │     │
│  │  ┌──────────────────────────────────────────────────┐                   │     │
│  │  │  CloudWatch Container Insights                   │                   │     │
│  │  │  - pod_cpu_utilization                           │                   │     │
│  │  │  - pod_number_of_container_restarts              │                   │     │
│  │  │  - node_cpu_utilization                          │                   │     │
│  │  └──────────────────────┬───────────────────────────┘                   │     │
│  └─────────────────────────┼───────────────────────────────────────────────┘     │
│                            │                                                     │
│                            ▼                                                     │
│  ┌──────────────────────────────────────────────────────────┐                    │
│  │  CloudWatch Alarms (us-west-2)                           │                    │
│  │                                                          │                    │
│  │  ┌────────────────────┐  Threshold                       │                    │
│  │  │ netaiops-cpu-spike │  pod_cpu > 80% (60s x 3)        │                    │
│  │  └────────────────────┘                                  │                    │
│  │  ┌────────────────────────┐  Threshold                   │                    │
│  │  │ netaiops-pod-restarts  │  restarts > 3 (300s x 1)    │                    │
│  │  └────────────────────────┘                              │                    │
│  │  ┌──────────────────────────┐  Threshold                 │                    │
│  │  │ netaiops-node-cpu-high   │  node_cpu > 85% (60s x 3) │                    │
│  │  └──────────────────────────┘                            │                    │
│  └──────────────────────────┬───────────────────────────────┘                    │
│                             │ ALARM state                                        │
│                             ▼                                                    │
│  ┌──────────────────────────────────────────────┐                                │
│  │  Amazon SNS Topic                            │                                │
│  │  (netaiops-incident-alarm-topic)             │                                │
│  └──────────────────────────┬───────────────────┘                                │
│                             │                                                    │
└─────────────────────────────┼────────────────────────────────────────────────────┘
                              │ SNS Notification
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      INVOCATION LAYER (us-east-1)                               │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │  Lambda: incident-alarm-trigger                                          │    │
│  │                                                                          │    │
│  │  ┌──────────────────┐    ┌───────────────────┐    ┌──────────────────┐   │    │
│  │  │ 1. Parse SNS     │───▶│ 2. Get M2M Token  │───▶│ 3. Build Korean  │   │    │
│  │  │    Alarm Message  │    │    from Cognito   │    │    Prompt        │   │    │
│  │  └──────────────────┘    └───────────────────┘    └────────┬─────────┘   │    │
│  │                                                             │             │    │
│  │                                      ┌──────────────────────▼──────────┐  │    │
│  │                                      │ 4. POST /runtimes/{arn}/       │  │    │
│  │                                      │    invocations                  │  │    │
│  │                                      │    Session: alarm-{name}-{uuid}│  │    │
│  │                                      └────────────────────────────────┘  │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                              │                                                   │
│                              │ Cognito M2M Token (client_credentials)            │
│                              ▼                                                   │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │  Amazon Cognito (M2M Authentication)                                     │    │
│  │  - Machine Client ID + Secret (from SSM)                                 │    │
│  │  - Token URL: /oauth2/token                                              │    │
│  │  - Grant: client_credentials                                             │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   AGENT RUNTIME LAYER (us-east-1)                               │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │              Incident Analysis Agent Runtime                              │    │
│  │              (incident_analysis_agent_runtime)                            │    │
│  │                                                                           │    │
│  │  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐  │    │
│  │  │  main.py    │  │  agent_task.py   │  │  IncidentAnalysisAgent      │  │    │
│  │  │ (Entrypoint)│─▶│  (Request Router)│─▶│                              │  │    │
│  │  └─────────────┘  └──────────────────┘  │  ┌──────────────────────┐   │  │    │
│  │                                          │  │  Strands Agent       │   │  │    │
│  │  ┌─────────────────────────────────┐     │  │  + Claude Opus 4.6   │   │  │    │
│  │  │  IncidentContext (ContextVar)   │     │  │  + System Prompt     │   │  │    │
│  │  │  - gateway_token               │     │  │  + MCP Tools         │   │  │    │
│  │  │  - response_queue              │     │  │  + current_time      │   │  │    │
│  │  │  - agent instance              │     │  │  + Retry (3x, exp)   │   │  │    │
│  │  └─────────────────────────────────┘     │  └──────────────────────┘   │  │    │
│  │                                          │                              │  │    │
│  │  ┌─────────────────────────────────┐     │  ┌──────────────────────┐   │  │    │
│  │  │  StreamingQueue                 │     │  │ MemoryHook           │   │  │    │
│  │  │  (Async response chunks)        │     │  │ (NO_MEMORY mode)     │   │  │    │
│  │  └─────────────────────────────────┘     │  └──────────────────────┘   │  │    │
│  │                                          └──────────────────────────────┘  │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                              │                                                   │
│                              │ Bearer Token (JWT)                                │
│                              ▼                                                   │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │                       MCP Gateway                                        │    │
│  │                                                                          │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌──────────┐ ┌────────┐ ┌───────────┐  │    │
│  │  │ Target:     │ │ Target:     │ │ Target:  │ │Target: │ │ Target:   │  │    │
│  │  │ container-  │ │ opensearch  │ │ datadog  │ │github  │ │ chaos     │  │    │
│  │  │ insight     │ │             │ │(optional)│ │        │ │           │  │    │
│  │  │ [Lambda]    │ │ [Lambda]    │ │[Lambda]  │ │[Lambda]│ │ [Lambda]  │  │    │
│  │  └──────┬──────┘ └──────┬──────┘ └────┬─────┘ └───┬────┘ └─────┬─────┘  │    │
│  └─────────┼───────────────┼─────────────┼───────────┼─────────────┼────────┘    │
│            │               │             │           │             │              │
└────────────┼───────────────┼─────────────┼───────────┼─────────────┼─────────────┘
             │               │             │           │             │
             ▼               ▼             ▼           ▼             ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       MCP TOOL LAMBDAS (us-east-1)                              │
│                                                                                 │
│  ┌──────────────────────┐  ┌───────────────────────┐  ┌──────────────────────┐  │
│  │ lambda-container-    │  │ lambda-opensearch      │  │ lambda-datadog       │  │
│  │ insight              │  │                        │  │ (optional)           │  │
│  │                      │  │ Tools:                 │  │                      │  │
│  │ Tools:               │  │ - opensearch-search-   │  │ Tools:               │  │
│  │ - container-insight- │  │   logs                 │  │ - datadog-query-     │  │
│  │   pod-metrics        │  │ - opensearch-anomaly-  │  │   metrics            │  │
│  │ - container-insight- │  │   detection            │  │ - datadog-get-events │  │
│  │   node-metrics       │  │ - opensearch-get-      │  │ - datadog-get-traces │  │
│  │ - container-insight- │  │   error-summary        │  │ - datadog-get-       │  │
│  │   cluster-overview   │  │                        │  │   monitors           │  │
│  └──────────┬───────────┘  └───────────┬────────────┘  └──────────┬───────────┘  │
│             │                          │                          │               │
│             ▼                          ▼                          ▼               │
│  ┌──────────────────┐     ┌───────────────────┐      ┌────────────────────┐      │
│  │ CloudWatch       │     │ Amazon OpenSearch  │      │ Datadog API        │      │
│  │ (us-west-2)      │     │ Index: eks-app-    │      │ (External)         │      │
│  │ Container        │     │ logs               │      │                    │      │
│  │ Insights         │     └───────────────────┘      └────────────────────┘      │
│  └──────────────────┘                                                            │
│                                                                                  │
│  ┌──────────────────────┐  ┌───────────────────────┐                             │
│  │ lambda-github        │  │ lambda-chaos           │                             │
│  │                      │  │                        │                             │
│  │ Tools:               │  │ Tools:                 │                             │
│  │ - github-create-     │  │ - chaos-cleanup        │                             │
│  │   issue              │  │   (auto-remediation)   │                             │
│  │ - github-add-comment │  │                        │                             │
│  │ - github-list-issues │  │ Detects & removes:     │                             │
│  │                      │  │ - stress-ng pods       │                             │
│  │ Language: Korean     │  │ - invalid-image deploy │                             │
│  └──────────┬───────────┘  │ - 0-replica scales     │                             │
│             │              └───────────┬────────────┘                             │
│             ▼                          │                                          │
│  ┌──────────────────┐                  ▼                                         │
│  │ GitHub API       │     ┌───────────────────────┐                              │
│  │ (PAT from SSM)   │     │ EKS Cluster           │                              │
│  │                   │     │ (us-west-2)           │                              │
│  └──────────────────┘     │ kubectl operations    │                              │
│                            └───────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Incident Analysis Workflow (6-Step)

```
   CloudWatch Alarm TRIGGERED
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Incident Information Gathering (인시던트 정보 파악)    │
│                                                                 │
│  - 인시던트 유형 식별 (서비스 중단, 성능 저하, 에러율 급증)     │
│  - 영향 서비스/컴포넌트 식별                                    │
│  - 인시던트 시간대 확인                                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: GitHub Issue Creation (GitHub 이슈 생성)              │
│                                                                 │
│  github-create-issue:                                           │
│  - 제목: "[인시던트] {alarm_name} 알람 발생" (한글)             │
│  - 라벨: incident, severity:high, auto-analysis                 │
│  - 본문: 알람 상세 정보 (한글)                                  │
│  - issue_number 기록 (이후 코멘트용)                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: Metric Collection (지표 수집) - Parallel              │
│                                                                 │
│  ┌────────────────────┐ ┌──────────────────┐ ┌──────────────┐   │
│  │ Container Insight  │ │   OpenSearch     │ │   Datadog    │   │
│  │                    │ │                  │ │  (optional)  │   │
│  │ - Pod CPU/Memory   │ │ - eks-app-logs   │ │ - APM traces │   │
│  │ - Node CPU/Memory  │ │   index search   │ │ - Metrics    │   │
│  │ - Network metrics  │ │ - Error patterns │ │              │   │
│  └────────────────────┘ └──────────────────┘ └──────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4: Correlation Analysis (상관관계 분석)                   │
│                                                                 │
│  - T ± 30분 이상 패턴 탐지                                     │
│  - 메트릭 간 상관관계 (CPU spike → latency ↑ → error rate ↑)   │
│  - 메모리 기반 과거 유사 인시던트 비교                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 5: Root Cause Estimation (근본 원인 추정)                │
│                                                                 │
│  github-add-comment:                                            │
│  - 확률순 원인 목록 (한글)                                      │
│  - 증거 매핑 (어떤 메트릭이 어떤 원인을 가리키는지)             │
│  - 타임라인 분석                                                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 6: Response Guide + Auto-Remediation (대응 가이드 + 복구)│
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Chaos Scenario Detection:                                 │  │
│  │                                                            │  │
│  │  stress-ng pod? ──────────┐                                │  │
│  │  invalid-image deploy? ───┤── YES ──▶ chaos-cleanup tool   │  │
│  │  0-replica scale? ────────┘          (auto-remediation)    │  │
│  │                                            │               │  │
│  │                    NO                      ▼               │  │
│  │                     │            github-add-comment:        │  │
│  │                     ▼            "복구 완료" (한글)         │  │
│  │            github-add-comment:           │                 │  │
│  │            대응 가이드 (한글)             ▼                 │  │
│  │            - 즉시 조치                 Close Issue          │  │
│  │            - 장기 개선                                      │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Event-Driven Auto-Invocation Flow

```
┌───────────┐      ┌──────────────┐      ┌──────────────┐      ┌─────────────┐
│  EKS      │      │  CloudWatch  │      │    SNS       │      │  Lambda     │
│  Cluster  │─────▶│  Alarm       │─────▶│   Topic      │─────▶│  alarm-     │
│  Metrics  │      │  ALARM state │      │              │      │  trigger    │
└───────────┘      └──────────────┘      └──────────────┘      └──────┬──────┘
                                                                       │
                                              ┌────────────────────────┘
                                              │
                        ┌─────────────────────▼────────────────────────┐
                        │                                              │
                        │  1. Parse alarm message                      │
                        │  2. Skip if state == OK                      │
                        │  3. Get M2M token from Cognito               │
                        │  4. Build Korean analysis prompt             │
                        │  5. POST to AgentCore Runtime API            │
                        │     - Bearer: M2M token                      │
                        │     - Session: alarm-{name}-{uuid}           │
                        │     - Actor: "alarm-trigger"                 │
                        │     - Timeout: 300s                          │
                        │                                              │
                        └─────────────────────┬────────────────────────┘
                                              │
                                              ▼
                        ┌──────────────────────────────────────────────┐
                        │  Incident Analysis Agent                     │
                        │  (Fully autonomous 6-step workflow)          │
                        │                                              │
                        │  Collect → Analyze → Diagnose → Remediate   │
                        └──────────────────────────────────────────────┘
```

---

## Key Components

| Component | Technology | Region | Purpose |
|-----------|-----------|--------|---------|
| Incident Agent Runtime | AgentCore + Strands + Claude Opus 4.6 | us-east-1 | 인시던트 분석 에이전트 |
| alarm-trigger Lambda | Python + requests | us-east-1 | SNS → AgentCore 호출 브릿지 |
| container-insight Lambda | Python + boto3 | us-east-1 | CloudWatch 메트릭 조회 |
| opensearch Lambda | Python + boto3 | us-east-1 | OpenSearch 로그 검색 |
| datadog Lambda | Python + requests | us-east-1 | Datadog APM 통합 (선택) |
| github Lambda | Python + requests | us-east-1 | GitHub 이슈 관리 |
| chaos Lambda | Python + boto3/kubectl | us-east-1 | 카오스 시나리오 자동 복구 |
| MCP Gateway | Lambda targets (5 targets) | us-east-1 | 도구 라우팅 |
| Cognito | OAuth2 M2M (client_credentials) | us-east-1 | 서비스 간 인증 |
| CloudWatch Alarms | 3 alarms | us-west-2 | 인시던트 감지 |
| SNS Topic | netaiops-incident-alarm-topic | us-west-2 | 알람 알림 전달 |
| EKS Cluster | netaiops-eks-cluster | us-west-2 | 대상 클러스터 |
| SSM Parameter Store | /app/incident/* | us-east-1 | 설정/자격증명 관리 |

---

## MCP Tool Inventory

| Lambda | Tool | Description |
|--------|------|-------------|
| container-insight | `container-insight-pod-metrics` | Pod CPU, Memory, Network 메트릭 |
| container-insight | `container-insight-node-metrics` | Node CPU, Memory 메트릭 |
| container-insight | `container-insight-cluster-overview` | 클러스터 전체 개요 |
| opensearch | `opensearch-search-logs` | eks-app-logs 인덱스 로그 검색 |
| opensearch | `opensearch-anomaly-detection` | 이상 탐지 |
| opensearch | `opensearch-get-error-summary` | 에러 요약 |
| datadog | `datadog-query-metrics` | Datadog 메트릭 조회 |
| datadog | `datadog-get-events` | Datadog 이벤트 |
| datadog | `datadog-get-traces` | APM 트레이스 |
| datadog | `datadog-get-monitors` | 모니터 상태 |
| github | `github-create-issue` | GitHub 이슈 생성 (한글) |
| github | `github-add-comment` | GitHub 코멘트 추가 (한글) |
| github | `github-list-issues` | GitHub 이슈 목록 |
| chaos | `chaos-cleanup` | 카오스 시나리오 자동 복구 |

---

## Language Policy

모든 출력물은 한국어(한글)로 작성됩니다:
- GitHub Issue 제목/본문/코멘트
- 근본 원인 분석 리포트
- 대응 가이드
- 사용자 응답

기술 용어(메트릭 이름, 도구 이름 등)는 영문 유지, 라벨은 영문 (`incident`, `severity:high`).
