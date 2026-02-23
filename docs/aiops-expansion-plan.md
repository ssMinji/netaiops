# NetAIOps 확장 계획서 - AIOps 기능 추가

> 작성일: 2026-02-10
> 프로젝트: NetAIOps (AWS Bedrock AgentCore 기반 네트워크 AI 운영 플랫폼)

---

## 목차

1. [현재 프로젝트 분석](#1-현재-프로젝트-분석)
2. [브레인스토밍 항목 적합도 평가](#2-브레인스토밍-항목-적합도-평가)
3. [선정 항목 및 구축 계획](#3-선정-항목-및-구축-계획)
   - [Phase 1: Incident 자동 분석 에이전트](#phase-1-incident-자동-분석-에이전트-module-6)
   - [Phase 2: 운영 레포트 자동화 에이전트](#phase-2-운영-레포트-자동화-에이전트-module-7)
   - [Phase 3: Help 채널 1선 대응 에이전트](#phase-3-help-채널-1선-대응-에이전트-module-8)
4. [구축 우선순위 및 의존 관계](#4-구축-우선순위-및-의존-관계)
5. [향후 확장 가능 항목](#5-향후-확장-가능-항목)

---

## 1. 현재 프로젝트 분석

### 기술 스택

| 구분 | 기술 |
|------|------|
| AI 런타임 | AWS Bedrock AgentCore |
| 모델 | Claude Opus 4.6 / Opus 4.5 / Sonnet 4 |
| 에이전트 프레임워크 | Strands Agents (A2A 프로토콜) |
| 인프라 | CloudFormation (VPC, EC2, RDS, Lambda, API Gateway) |
| 모니터링 | CloudWatch (Logs, Metrics, Alarms) |
| 네트워크 | Route 53, VPC Reachability Analyzer, Transit Gateway |
| 인증 | Cognito (OAuth2 PKCE) |
| 프론트엔드 | Streamlit (Chat UI) |

### 구현 완료 모듈

| 모듈 | 기능 | 핵심 역량 |
|------|------|-----------|
| Module 1 | 기본 AgentCore | 에이전트 구조, MCP 도구, 스트리밍 |
| Module 2 | 메모리 강화 에이전트 | 3계층 메모리 (Semantic/Summary/Preference) |
| Module 3 | A2A 멀티에이전트 협업 | 에이전트 간 통신, 오케스트레이션 |
| Module 4 | LLM-as-a-Judge 평가 | 자동 품질 평가, HTML 대시보드 |
| Module 5 | Kubernetes 진단 | EKS MCP Server, 파드/노드 진단 |
| Chat Frontend | Streamlit 웹 UI | 대화형 에이전트 인터페이스 |

### 현재 연동 서비스

**연동 완료:** AWS Bedrock, Route 53, VPC Reachability Analyzer, CloudWatch, SSM Parameter Store, Cognito, SNS, DynamoDB

**미연동:** Datadog, Slack, Jira, Confluence, OpenSearch, GitHub API

---

## 2. 브레인스토밍 항목 적합도 평가

### 평가 기준

- **기술 시너지**: 기존 아키텍처와의 통합 용이성
- **구현 난이도**: 필요한 신규 인프라 및 연동 범위
- **비즈니스 임팩트**: 운영 효율화 기여도

### 평가 결과

| # | 항목 | 적합도 | 기술 시너지 | 구현 난이도 | 비즈니스 임팩트 | 선정 |
|---|------|--------|------------|------------|----------------|------|
| 1 | Incident 자동 분석 | ★★★★★ | 높음 | 중간 | 높음 | ✅ |
| 2 | 레포트 자동화 | ★★★★☆ | 높음 | 낮음 | 높음 | ✅ |
| 3 | Help 채널 1선 대응 | ★★★★☆ | 중간 | 중간 | 높음 | ✅ |
| 4 | 연관서비스 모니터 | ★★★☆☆ | 중간 | 높음 | 중간 | - |
| 5 | Jira 업무 자동화 | ★★★☆☆ | 낮음 | 중간 | 중간 | - |
| 6 | 버전 관리 어시스턴스 | ★★☆☆☆ | 낮음 | 낮음 | 낮음 | - |
| 7 | 요기요 검색량 모니터 | ★★☆☆☆ | 낮음 | 높음 | 중간 | - |

### 선정 사유

**Incident 자동 분석 (★★★★★)**
- CloudWatch가 이미 연동되어 있어 확장이 가장 자연스러움
- K8s 에이전트(Module 5)의 Container Insight와 직접 시너지
- A2A 프레임워크(Module 3)에 즉시 등록 가능

**레포트 자동화 (★★★★☆)**
- CloudWatch 메트릭 수집 인프라가 이미 존재
- 평가 대시보드(Module 4) 패턴을 레포트 생성에 재활용 가능
- Phase 1의 인시던트 데이터를 입력으로 활용

**Help 채널 1선 대응 (★★★★☆)**
- Streamlit 채팅 프론트엔드와 메모리 시스템이 이미 존재
- Slack을 새로운 인터페이스 채널로 추가하는 구조
- Jira 업무 자동화 기능을 부분적으로 포함 (미선정 항목 커버)

---

## 3. 선정 항목 및 구축 계획

### Phase 1: Incident 자동 분석 에이전트 (Module 6)

기존 CloudWatch 에이전트를 확장하고, Datadog/OpenSearch/Container Insight를 추가 연동하여 인시던트 발생 시 자동으로 원인을 분석하고 대응 가이드를 제공합니다.

#### 디렉토리 구조

```
workshop-module-6/
├── module-6/
│   ├── agentcore-incident-agent/
│   │   ├── agent_config/
│   │   │   ├── agent.py                # IncidentAnalysisAgent
│   │   │   ├── agent_task.py
│   │   │   └── memory_hook_provider.py
│   │   ├── .bedrock_agentcore.yaml
│   │   └── requirements.txt
│   └── mcp-tools/
│       ├── lambda-datadog/             # Datadog API 연동
│       │   └── lambda_function.py
│       ├── lambda-opensearch/          # OpenSearch 로그 검색
│       │   └── lambda_function.py
│       └── lambda-container-insight/   # Container Insight 메트릭
│           └── lambda_function.py
├── cfn/
│   └── incident-agent-setup.yaml       # 인프라 배포 템플릿
└── README.md
```

#### 에이전트 동작 흐름

```
1. 인시던트 알림 수신
   (CloudWatch Alarm / Datadog Alert / PagerDuty Webhook)
         │
         ▼
2. 관련 지표 자동 수집
   ├── CloudWatch 메트릭 (CPU, Memory, Network, Disk)
   ├── Datadog APM 트레이스 (Latency, Error Rate, Throughput)
   └── OpenSearch 로그 (Application Log, Error Pattern)
         │
         ▼
3. 시계열 상관관계 분석
   - 인시던트 시점 전후 이상 패턴 탐지
   - 메트릭 간 상관관계 분석
         │
         ▼
4. 근본 원인 추정
   - 메모리 시스템에서 과거 유사 인시던트 참조
   - 패턴 매칭 기반 원인 후보 도출
         │
         ▼
5. 대응 가이드 생성
   - SOP 기반 단계별 가이드
   - 자동 실행 가능 조치 제안
   - 에스컬레이션 판단
```

#### MCP 도구 설계

| 도구 | 기능 | 데이터 소스 |
|------|------|------------|
| `datadog-query-metrics` | 시계열 메트릭 조회 (CPU, Memory, Latency, Error Rate) | Datadog API v2 |
| `datadog-get-events` | 이벤트/알림 이력 조회 | Datadog Events API |
| `datadog-get-traces` | APM 트레이스 조회 (느린 요청, 에러 트레이스) | Datadog APM API |
| `opensearch-search-logs` | 키워드/패턴 기반 로그 검색 | OpenSearch Query DSL |
| `opensearch-anomaly-detection` | 로그 이상 탐지 (ML 기반) | OpenSearch AD Plugin |
| `container-insight-metrics` | EKS 파드/노드/클러스터 메트릭 | CloudWatch Container Insights |
| `container-insight-logs` | 컨테이너 stdout/stderr 로그 | CloudWatch Logs Insights |

#### A2A 연동

기존 CollaboratorAgent에 IncidentAgent를 등록합니다.

```
CollaboratorAgent (오케스트레이터)
        │
   +----+----+----+
   │         │         │
   ▼         ▼         ▼
Connectivity  Performance  Incident
  Agent        Agent       Agent (신규)
```

- "서비스 장애 분석해줘" → IncidentAgent로 자동 라우팅
- IncidentAgent가 ConnectivityAgent / PerformanceAgent에 하위 분석 요청 가능

#### 필요 외부 설정

| 서비스 | 필요 항목 | 저장 위치 |
|--------|----------|-----------|
| Datadog | API Key, Application Key | SSM Parameter Store (SecureString) |
| OpenSearch | Endpoint URL, 인증 정보 | SSM Parameter Store |
| Container Insight | EKS 클러스터 ARN | CloudFormation Output |

---

### Phase 2: 운영 레포트 자동화 에이전트 (Module 7)

주기적/온디맨드로 비용, 운영, 인시던트 레포트를 생성하고 인사이트를 함께 제공합니다.

#### 디렉토리 구조

```
workshop-module-7/
├── module-7/
│   ├── agentcore-report-agent/
│   │   ├── agent_config/
│   │   │   ├── agent.py                # ReportGenerationAgent
│   │   │   ├── agent_task.py
│   │   │   └── report_templates/       # 레포트 템플릿
│   │   │       ├── cost_report.py
│   │   │       ├── ops_report.py
│   │   │       └── incident_report.py
│   │   ├── .bedrock_agentcore.yaml
│   │   └── requirements.txt
│   └── mcp-tools/
│       ├── lambda-cost-explorer/       # AWS Cost Explorer API
│       │   └── lambda_function.py
│       └── lambda-report-store/        # S3 레포트 저장/조회
│           └── lambda_function.py
├── scheduler/
│   └── eventbridge-rules.yaml          # 주기적 실행 스케줄
└── README.md
```

#### 레포트 유형

| 레포트 | 주기 | 데이터 소스 | 내용 |
|--------|------|------------|------|
| **비용 레포트** | 주 1회 (월요일) | AWS Cost Explorer | 서비스별 비용, 전주 대비 변동, 이상 비용 탐지, 최적화 제안 |
| **운영 레포트** | 일 1회 (09:00) | CloudWatch, Datadog | 가용성 SLA, 응답시간 P50/P95/P99, 에러율, 배포 이력 |
| **인시던트 레포트** | 이벤트 기반 | Phase 1 결과 | 타임라인, 영향 범위, 근본 원인, 조치 내역, 재발 방지 |

#### 동작 흐름

```
1. 트리거
   ├── EventBridge 스케줄 (주기적)
   └── 사용자 요청 / 인시던트 종료 (온디맨드)
         │
         ▼
2. 데이터 수집
   ├── Cost Explorer API (비용 데이터)
   ├── CloudWatch Metrics/Logs (운영 지표)
   └── Phase 1 IncidentAgent 분석 결과 (인시던트 데이터)
         │
         ▼
3. LLM 분석 및 인사이트 생성
   - 트렌드 분석, 이상 탐지
   - 전주/전월 대비 비교
   - 개선 권고사항 도출
         │
         ▼
4. 레포트 생성 및 저장
   - Markdown / HTML 형식
   - S3 버킷에 저장 (이력 관리)
         │
         ▼
5. 알림 발송
   - Slack 채널 (Phase 3 인프라 활용)
   - 이메일 (SNS)
```

#### MCP 도구 설계

| 도구 | 기능 |
|------|------|
| `cost-explorer-query` | 기간별/서비스별 비용 데이터 조회 |
| `cost-explorer-forecast` | 비용 예측 (향후 30일) |
| `report-store-save` | S3에 레포트 저장 |
| `report-store-list` | 이전 레포트 목록 조회 |
| `report-store-get` | 특정 레포트 조회 |

---

### Phase 3: Help 채널 1선 대응 에이전트 (Module 8)

Slack을 인터페이스로 사용하여, 운영팀 문의에 지식 기반으로 1차 대응합니다. 해결 불가 시 Jira 티켓을 자동 생성합니다.

#### 디렉토리 구조

```
workshop-module-8/
├── module-8/
│   ├── agentcore-helpdesk-agent/
│   │   ├── agent_config/
│   │   │   ├── agent.py                # HelpDeskAgent
│   │   │   ├── agent_task.py
│   │   │   └── memory_hook_provider.py
│   │   ├── knowledge_base/             # RAG 지식 베이스 설정
│   │   │   └── kb_config.yaml
│   │   ├── .bedrock_agentcore.yaml
│   │   └── requirements.txt
│   └── mcp-tools/
│       ├── lambda-slack/               # Slack Bot 연동
│       │   └── lambda_function.py
│       ├── lambda-confluence/          # Confluence 검색
│       │   └── lambda_function.py
│       └── lambda-jira/                # Jira 연동
│           └── lambda_function.py
├── slack-app/
│   ├── manifest.yaml                   # Slack App 매니페스트
│   └── event-handler/
│       └── lambda_function.py          # Slack Events API 핸들러
├── cfn/
│   └── helpdesk-agent-setup.yaml
└── README.md
```

#### 동작 흐름

```
1. Slack help 채널에 질문 게시
         │
         ▼
2. Slack Events API → Lambda → AgentCore 호출
         │
         ▼
3. 지식 검색
   ├── Bedrock Knowledge Base (Confluence 문서, SOP)
   ├── 3계층 메모리 (유사 문의 이력)
   └── 과거 인시던트 레포트 (Phase 2)
         │
         ▼
4. 답변 생성 → Slack 스레드에 응답
         │
         ├── 해결됨 → 메모리에 저장 (향후 참조)
         │
         └── 해결 불가
               │
               ▼
5. Jira 티켓 자동 생성
   - 문의 내용 요약
   - 1차 분석 결과 첨부
   - 적절한 담당자 assign
   - Slack 스레드에 티켓 링크 공유
```

#### 지식 소스

| 소스 | 연동 방식 | 용도 |
|------|----------|------|
| Confluence | Bedrock Knowledge Base (RAG) | 운영 문서, SOP, 아키텍처 문서 |
| GitHub Wiki | Bedrock Knowledge Base (RAG) | 기술 문서, 트러블슈팅 가이드 |
| 과거 Slack 스레드 | 메모리 시스템 | 이전 문의/답변 이력 |
| 인시던트 레포트 | S3 (Phase 2) | 과거 장애 분석 결과 |

#### MCP 도구 설계

| 도구 | 기능 |
|------|------|
| `slack-send-message` | Slack 채널/스레드에 메시지 전송 |
| `slack-get-thread` | 스레드 대화 이력 조회 |
| `confluence-search` | Confluence 문서 검색 |
| `confluence-get-page` | 특정 페이지 내용 조회 |
| `jira-create-ticket` | Jira 티켓 생성 |
| `jira-search-issues` | 유사 이슈 검색 |
| `jira-add-comment` | 티켓에 코멘트 추가 |

#### Slack App 설정

```yaml
# slack-app/manifest.yaml
display_information:
  name: NetAIOps HelpDesk
  description: AI 기반 운영 지원 봇

features:
  bot_user:
    display_name: NetAIOps Bot
    always_online: true

oauth_config:
  scopes:
    bot:
      - channels:history
      - channels:read
      - chat:write
      - chat:write.customize
      - users:read

event_subscriptions:
  bot_events:
    - message.channels
    - app_mention
```

---

## 4. 구축 우선순위 및 의존 관계

### 의존 관계 다이어그램

```
Phase 1: Incident 자동 분석 ──────────┐
  (기존 CloudWatch + Datadog/OS 확장)  │
                                       ├──→ Phase 2: 레포트 자동화
Phase 1.5: Slack Bot 기반 인프라 구축 ─┘     (인시던트 데이터 활용)
                                                │
                                                ▼
                                         Phase 3: Help 채널 1선 대응
                                           (레포트 + 인시던트 데이터 +
                                            Slack 인프라 활용)
```

### Phase 1이 최우선인 이유

1. **기존 인프라 활용**: CloudWatch 도구가 이미 Lambda로 구현되어 확장이 가장 용이
2. **K8s 시너지**: Module 5의 Container Insight와 직접 연계
3. **A2A 즉시 등록**: Module 3 CollaboratorAgent에 바로 추가 가능
4. **데이터 파이프라인**: 인시던트 분석 결과가 Phase 2, 3의 입력 데이터가 됨

### 전체 아키텍처 (확장 후)

```
+-------------------------------------------------------------------------+
|                         사용자 인터페이스                                 |
|           (Streamlit Chat / Slack Bot / API / Dashboard)                |
+------------------------------------+------------------------------------+
                                     |
+------------------------------------v------------------------------------+
|                    AWS Bedrock AgentCore Runtime                        |
|                                                                         |
|  기존 에이전트                          신규 에이전트                     |
|  +------------------+                  +------------------+             |
|  | Troubleshooting  |                  |    Incident      |             |
|  |      Agent       |                  |  Analysis Agent  |             |
|  +------------------+                  |    (Phase 1)     |             |
|  | Performance      |                  +------------------+             |
|  |      Agent       |                  |    Report        |             |
|  +------------------+                  |  Generation Agent|             |
|  | Collaborator     |                  |    (Phase 2)     |             |
|  |      Agent       |                  +------------------+             |
|  +------------------+                  |    HelpDesk      |             |
|  | K8s Diagnostics  |                  |      Agent       |             |
|  |      Agent       |                  |    (Phase 3)     |             |
|  +------------------+                  +------------------+             |
|                                                                         |
|  +-------------------------------------------------------------------+ |
|  |                       Memory Management                           | |
|  |  Semantic (365d) + Summary (Session) + User Preference (90d)      | |
|  +-------------------------------------------------------------------+ |
+------------------------------------+------------------------------------+
                                     |
+------------------------------------v------------------------------------+
|                         도구 레이어 (Lambda MCP)                        |
|                                                                         |
|  기존 도구                              신규 도구                        |
|  +--------------+                      +--------------+                 |
|  | DNS Lookup   |                      | Datadog API  |                 |
|  | Connectivity |                      | OpenSearch   |                 |
|  | CloudWatch   |                      | Container    |                 |
|  | Network Flow |                      |   Insight    |                 |
|  | EKS MCP      |                      | Cost Explorer|                 |
|  +--------------+                      | Slack Bot    |                 |
|                                        | Confluence   |                 |
|                                        | Jira         |                 |
|                                        | Report Store |                 |
|                                        +--------------+                 |
+-------------------------------------------------------------------------+
                                     |
+------------------------------------v------------------------------------+
|                          외부 서비스 연동                                |
|  +----------+  +----------+  +----------+  +----------+  +----------+  |
|  | Datadog  |  |OpenSearch|  |  Slack   |  |Confluence|  |   Jira   |  |
|  +----------+  +----------+  +----------+  +----------+  +----------+  |
+-------------------------------------------------------------------------+
```

---

## 5. 향후 확장 가능 항목

Phase 1~3 완료 후 별도 평가를 권장하는 항목입니다.

| 항목 | 확장 방향 | 비고 |
|------|----------|------|
| **Jira 업무 자동화** | Phase 3 HelpDesk 에이전트에서 Jira 연동이 이미 포함됨. 추가로 PR 연관, 자동 assign 고도화 가능 | Phase 3에서 부분 커버 |
| **연관서비스 모니터** | AWS Health Dashboard API + 외부 서비스 Status Page 크롤링으로 구현 가능 | 별도 모듈 권장 |
| **버전 관리 어시스턴스** | GitHub Dependabot + LLM 요약으로 구현 가능. 현재 인프라 운영 중심과는 성격이 다름 | 우선순위 낮음 |
| **요기요 검색량 모니터** | 비즈니스 특화 기능으로 별도 프로젝트가 적합. 웹 크롤링 + 트래픽 상관분석 필요 | 별도 프로젝트 권장 |

---

## 부록: 필요 외부 서비스 계정/권한 정리

| 서비스 | 필요 항목 | Phase |
|--------|----------|-------|
| Datadog | API Key, Application Key | Phase 1 |
| OpenSearch | 도메인 엔드포인트, IAM 인증 | Phase 1 |
| Slack | Bot Token, Signing Secret, App 설치 | Phase 2, 3 |
| Confluence | API Token, 도메인 URL | Phase 3 |
| Jira | API Token, 프로젝트 키 | Phase 3 |
| AWS Cost Explorer | IAM 권한 (ce:GetCostAndUsage 등) | Phase 2 |
