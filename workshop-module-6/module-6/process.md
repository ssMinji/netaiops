# Module 6 - Incident Analysis Agent 동작 흐름

## 전체 아키텍처

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────────┐     ┌──────────────────────────┐
│  Chat Frontend   │     │ Chaos Lambda │     │ CloudWatch  │     │  Alarm Trigger   │     │  Incident Analysis Agent │
│  (Streamlit)     │────▶│ (EKS 장애주입)│────▶│  Alarms     │────▶│  Lambda (SNS)    │────▶│  (Bedrock AgentCore)     │
└─────────────────┘     └──────────────┘     └─────────────┘     └──────────────────┘     └──────────────────────────┘
                                                                                                    │
                                                                                          ┌─────────┼─────────┐
                                                                                          ▼         ▼         ▼
                                                                                   ┌──────────┐ ┌────────┐ ┌────────┐
                                                                                   │Container │ │Open    │ │GitHub  │
                                                                                   │Insight   │ │Search  │ │Issues  │
                                                                                   └──────────┘ └────────┘ └────────┘
```

## Step 1: 장애 주입 (Chaos Engineering)

**트리거**: Chat Frontend에서 "Trigger Incident" 버튼 클릭

**컴포넌트**: `incident-chaos-tools` Lambda

**동작**:
1. Frontend의 Chaos 버튼 (CPU Stress, Error Injection, Latency Injection, Pod Crash) 클릭
2. Frontend가 `incident-chaos-tools` Lambda를 직접 호출
3. Lambda가 EKS 클러스터(`netaiops-eks-cluster`, us-west-2)에 Chaos 파드 배포
   - `chaos-cpu-stress`: stress-ng로 CPU 부하 생성
   - `chaos-error-injection`: 에러 응답 반환하는 파드 배포
   - `chaos-latency-injection`: 응답 지연 파드 배포
   - `chaos-pod-crash`: CrashLoopBackOff 유발 파드 배포

**결과**: EKS 메트릭이 비정상적으로 급증

---

## Step 2: CloudWatch 알람 감지

**트리거**: EKS Container Insights 메트릭 임계값 초과

**컴포넌트**: CloudWatch Alarms (us-west-2)

**알람 목록**:

| 알람 이름 | 메트릭 | 임계값 | 평가 주기 |
|-----------|--------|--------|-----------|
| `netaiops-cpu-spike` | pod_cpu_utilization | > 80% | 60초 x 3회 (2/3 위반) |
| `netaiops-pod-restarts` | pod_number_of_container_restarts | > 3 | 300초 x 1회 |
| `netaiops-node-cpu-high` | node_cpu_utilization | > 85% | 60초 x 3회 (2/3 위반) |

**동작**:
1. Container Insights가 EKS 메트릭을 CloudWatch로 전송
2. 알람 조건 충족 시 상태가 `OK` → `ALARM`으로 변경
3. SNS Topic(`netaiops-incident-alarm-topic`, us-west-2)으로 알림 발행

---

## Step 3: 에이전트 자동 호출

**트리거**: SNS 알림 수신

**컴포넌트**: `incident-alarm-trigger` Lambda (us-east-1)

**동작**:
1. SNS에서 CloudWatch 알람 메시지 수신
2. 알람 상태 확인 — `OK` 복귀 시 무시
3. 알람 상세 정보 파싱 (알람명, 메트릭, 임계값, 발생 시간 등)
4. SSM에서 Cognito M2M 자격증명 조회
5. Cognito `client_credentials` flow로 액세스 토큰 획득
6. 한글 인시던트 분석 프롬프트 생성:
   ```
   [자동 인시던트 알림]
   CloudWatch 알람이 트리거되었습니다...
   제목: "[인시던트] {alarm_name} 알람 발생"
   ```
7. AgentCore Runtime API 호출:
   - `POST https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{agent_arn}/invocations`
   - Session ID: `alarm-{alarm_name}-{uuid}`
   - Actor ID: `alarm-trigger`

**SSM 파라미터**:
- `/app/incident/agentcore/agent_runtime_arn`
- `/app/incident/agentcore/machine_client_id`
- `/app/incident/agentcore/machine_client_secret`
- `/app/incident/agentcore/cognito_token_url`
- `/app/incident/agentcore/cognito_auth_scope`

---

## Step 4: 에이전트 인시던트 분석 실행

**트리거**: AgentCore Runtime API 호출

**컴포넌트**: `IncidentAnalysisAgent` (Bedrock AgentCore + Strands AI Agent)

**모델**: Claude Opus 4.6 (`global.anthropic.claude-opus-4-6-v1`)

**MCP Gateway 도구**:

| 카테고리 | 도구명 | 기능 |
|----------|--------|------|
| Container Insight | container-insight-pod-metrics | 파드 CPU/Memory/Network 메트릭 |
| Container Insight | container-insight-node-metrics | 노드 리소스 사용률 |
| Container Insight | container-insight-cluster-overview | 클러스터 전체 상태 |
| OpenSearch | opensearch-search-logs | 키워드/패턴 로그 검색 |
| OpenSearch | opensearch-anomaly-detection | 로그 볼륨 이상 감지 |
| OpenSearch | opensearch-get-error-summary | 에러 유형별 통계 |
| Datadog (선택) | datadog-query-metrics | 시계열 메트릭 조회 |
| Datadog (선택) | datadog-get-traces | APM 트레이스 조회 |
| GitHub | github-create-issue | 인시던트 이슈 생성 |
| GitHub | github-add-comment | 이슈 코멘트 추가 |
| GitHub | github-list-issues | 이슈 목록 조회 |
| Chaos | chaos-cleanup | Chaos 파드 정리 (자동 복구) |

### 에이전트 워크플로우 (6단계)

#### 4-1. 인시던트 정보 파악
- 인시던트 유형 식별 (서비스 장애, 성능 저하, 에러율 급증)
- 영향받는 서비스/컴포넌트 파악
- 인시던트 타임프레임 결정

#### 4-2. GitHub Issue 생성 (한글)
- 제목 예시: `[인시던트] netaiops-cpu-spike 알람 발생`
- 본문: 인시던트 개요, 알람 정보 (한글)
- 라벨: `incident`, `severity:high`, `auto-analysis` (영문 유지)
- `issue_number` 기록 → 이후 코멘트에 사용

#### 4-3. 지표 수집 (병렬 실행)
1. **Container Insight** — 파드/노드 CPU, Memory, Network 메트릭 (필수)
2. **OpenSearch** — `eks-app-logs` 인덱스에서 에러 로그 검색
3. **Datadog** — APM 트레이스, 서비스 메트릭 (미설정 시 스킵)

#### 4-4. 상관관계 분석
- 인시던트 시점 전후 ±30분 이상 패턴 감지
- 소스 간 메트릭 상관 분석 (CPU 급증 → 지연 증가 → 에러율)
- 메모리 기반 과거 유사 인시던트 비교

#### 4-5. 근본 원인 추정 + 분석 코멘트
- 가능한 원인을 확률 순으로 나열
- 근거 데이터 매핑
- GitHub Issue에 한글 분석 코멘트 작성:
  ```markdown
  ## 근본 원인 분석 결과
  - Chaos pod (chaos-cpu-stress) 감지됨
  - 실행 중인 명령: stress --cpu 4 --timeout 300
  - CPU 사용률: 95% (정상 < 30%)
  ```

#### 4-6. 대응 가이드 + 자동 복구
- GitHub Issue에 한글 대응 가이드 코멘트 작성
- **자동 복구 조건 감지 시**:
  - `stress-ng` 또는 `chaos-stress` 파드 → `chaos-cleanup` 호출
  - `invalid-image:latest` 이미지 → `chaos-cleanup` 호출
  - 비정상적 0 레플리카 스케일 → `chaos-cleanup` 호출
- 복구 결과를 GitHub Issue에 한글로 최종 코멘트
- 복구 성공 시 이슈 닫기

---

## Step 5: 결과 확인

**GitHub Issue 최종 형태**:

```
Issue #42: [인시던트] netaiops-cpu-spike 알람 발생
Labels: incident, severity:high, auto-analysis

본문: 인시던트 개요 (한글)
  ├── Comment #1: 지표 수집 및 근본 원인 분석 결과 (한글)
  ├── Comment #2: 대응 가이드 (한글)
  ├── Comment #3: 자동 복구 실행 결과 (한글)
  └── Status: Closed (복구 성공 시)
```

---

## 인프라 구성 요약

### Lambda 함수 (us-east-1)

| 함수명 | ECR 리포지토리 | 용도 |
|--------|---------------|------|
| `incident-chaos-tools` | incident-chaos-tools-repo | EKS Chaos 파드 배포/정리 |
| `incident-alarm-trigger` | incident-alarm-trigger-repo | SNS → 에이전트 호출 |
| `incident-github-tools` | incident-github-tools-repo | GitHub Issue 생성/코멘트 |
| `incident-container-insight-tools` | incident-container-insight-tools-repo | CloudWatch 메트릭 조회 |
| `incident-opensearch-tools` | incident-opensearch-tools-repo | OpenSearch 로그 검색 |
| `incident-datadog-tools` | incident-datadog-tools-repo | Datadog APM 조회 |

### SSM 파라미터

| 경로 | 용도 |
|------|------|
| `/app/incident/agentcore/*` | AgentCore 인증 및 설정 |
| `/app/incident/github/pat` | GitHub Personal Access Token |
| `/app/incident/github/repo` | GitHub 리포지토리 (owner/repo) |
| `/app/incident/opensearch/endpoint` | OpenSearch 도메인 엔드포인트 |
| `/app/incident/datadog/*` | Datadog API/APP 키 |

### IAM Role

- **역할명**: `incident-tools-lambda-role`
- **권한**: CloudWatch 읽기, OpenSearch 접근, SSM 파라미터 조회, EKS Describe, STS

### 언어 정책

- GitHub Issue 제목/본문/댓글: **한글**
- 메트릭 이름, 도구 이름: **영문**
- Issue 라벨: **영문**
