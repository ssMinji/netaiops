# Module 6: Incident Auto-Analysis Agent (인시던트 자동 분석 에이전트)

AWS Bedrock AgentCore 기반의 인시던트 자동 분석 에이전트입니다.
Datadog, OpenSearch, Container Insight를 연동하여 인시던트 발생 시 자동으로 원인을 분석하고 대응 가이드를 제공합니다.

---

## 아키텍처

```
Streamlit Test UI (port 8502)
        │
        ▼
AWS Bedrock AgentCore Runtime
        │
        ▼
IncidentAnalysisAgent
        │
   ┌────┼────┐
   ▼    ▼    ▼
Datadog  OpenSearch  Container Insight
 API     Logs Search  (CloudWatch)
```

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| Datadog 메트릭 조회 | CPU, Memory, Latency, Error Rate 시계열 데이터 |
| Datadog APM 트레이스 | 느린 요청, 에러 트레이스 분석 |
| OpenSearch 로그 검색 | 키워드/패턴 기반 애플리케이션 로그 검색 |
| OpenSearch 이상 탐지 | 시간대별 로그 볼륨 이상 패턴 감지 |
| Container Insight | EKS 파드/노드/클러스터 리소스 메트릭 |
| 3계층 메모리 | 과거 인시던트 분석 결과 학습 및 활용 |

---

## 프로젝트 구조

```
workshop-module-6/
├── module-6/
│   ├── agentcore-incident-agent/       # 에이전트 코드
│   │   ├── main.py                     # AgentCore 엔트리포인트
│   │   ├── .bedrock_agentcore.yaml     # 런타임 설정
│   │   ├── requirements.txt
│   │   └── agent_config/
│   │       ├── agent.py                # IncidentAnalysisAgent
│   │       ├── agent_task.py           # 요청 처리
│   │       ├── context.py              # 컨텍스트 관리
│   │       ├── streaming_queue.py      # 스트리밍 큐
│   │       ├── access_token.py         # Cognito 토큰
│   │       ├── memory_hook_provider.py # 메모리 훅
│   │       └── utils.py                # SSM 유틸리티
│   └── prerequisite/
│       ├── lambda-datadog/             # Datadog MCP 도구
│       ├── lambda-opensearch/          # OpenSearch MCP 도구
│       └── lambda-container-insight/   # Container Insight MCP 도구
├── incident-chat-frontend/             # Streamlit 테스트 UI
│   ├── src/app.py
│   ├── requirements.txt
│   └── Dockerfile
└── README.md
```

---

## 사전 요구사항

- AWS 계정 및 IAM 권한
- AWS CLI 설치 및 구성
- Python 3.11+
- Docker (에이전트 배포용)
- Bedrock AgentCore 인프라 (Module 1~3 배포 완료)

### 외부 서비스

| 서비스 | 필요 항목 |
|--------|----------|
| Datadog | API Key, Application Key |
| OpenSearch | 도메인 엔드포인트 |
| EKS (Container Insight) | 클러스터 이름 |

---

## SSM 파라미터 설정

에이전트 배포 전 아래 SSM 파라미터를 생성하세요:

```bash
# Cognito 설정 (기존 인프라에서 확인)
aws ssm put-parameter --name "/app/incident/agentcore/cognito_provider" \
    --value "<cognito-provider-name>" --type String

# MCP Gateway URL
aws ssm put-parameter --name "/app/incident/agentcore/gateway_url" \
    --value "<gateway-url>" --type String

# Memory ID (선택사항)
aws ssm put-parameter --name "/app/incident/agentcore/memory_id" \
    --value "<memory-id>" --type String

# Datadog 인증 정보
aws ssm put-parameter --name "/app/incident/datadog/api_key" \
    --value "<datadog-api-key>" --type SecureString

aws ssm put-parameter --name "/app/incident/datadog/app_key" \
    --value "<datadog-app-key>" --type SecureString

# OpenSearch 엔드포인트
aws ssm put-parameter --name "/app/incident/opensearch/endpoint" \
    --value "<opensearch-endpoint>" --type String
```

---

## 빠른 시작

### Step 1: 에이전트 설정 및 로컬 테스트

```bash
cd workshop-module-6/module-6/agentcore-incident-agent

# 가상환경 설정
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 로컬 테스트
python main.py
```

### Step 2: 에이전트 배포

```bash
bedrock-agentcore deploy
```

### Step 3: Streamlit 테스트 UI 실행

```bash
cd workshop-module-6/incident-chat-frontend

# 가상환경 설정
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# UI 실행 (port 8502)
cd src
streamlit run app.py --server.port 8502
```

브라우저에서 `http://localhost:8502` 접속

### Docker로 실행

```bash
cd workshop-module-6/incident-chat-frontend
docker build -t netaiops-incident-chat .
docker run -p 8502:8502 netaiops-incident-chat
```

---

## 테스트 시나리오

UI 사이드바에서 테스트 시나리오를 선택하거나, 직접 입력하세요:

| 시나리오 | 입력 예시 |
|---------|----------|
| CPU 급증 분석 | "서비스 web-api의 CPU 사용률이 90%를 넘었습니다. 원인을 분석해주세요." |
| 에러율 증가 | "지난 1시간 동안 payment 서비스의 에러율이 5%를 초과했습니다." |
| 지연 시간 급증 | "API 응답 지연이 P99 기준 2초를 넘었습니다." |
| 파드 재시작 반복 | "EKS에서 checkout-service 파드가 반복적으로 재시작됩니다." |

---

## MCP 도구 상세

### Datadog 도구

| 도구 | 기능 |
|------|------|
| `datadog-query-metrics` | 시계열 메트릭 조회 (CPU, Memory, Latency 등) |
| `datadog-get-events` | 이벤트/알림 이력 조회 |
| `datadog-get-traces` | APM 트레이스 조회 (느린 요청, 에러) |
| `datadog-get-monitors` | 모니터 상태 조회 |

### OpenSearch 도구

| 도구 | 기능 |
|------|------|
| `opensearch-search-logs` | 키워드/패턴 기반 로그 검색 |
| `opensearch-anomaly-detection` | 시간대별 로그 볼륨 이상 탐지 |
| `opensearch-get-error-summary` | 에러 유형별 통계 조회 |

### Container Insight 도구

| 도구 | 기능 |
|------|------|
| `container-insight-pod-metrics` | 파드 CPU/Memory/Network 메트릭 |
| `container-insight-node-metrics` | 노드 리소스 사용률 |
| `container-insight-cluster-overview` | 클러스터 전체 상태 개요 |

---

## 향후 계획

- [ ] A2A 프로토콜로 CollaboratorAgent에 등록
- [ ] PagerDuty webhook 연동
- [ ] CloudFormation 배포 자동화
- [ ] 인시던트 자동 에스컬레이션 규칙

---

## 참고

- [AWS Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/)
- [Datadog API Reference](https://docs.datadoghq.com/api/)
- [OpenSearch Documentation](https://opensearch.org/docs/)
- [Container Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ContainerInsights.html)
