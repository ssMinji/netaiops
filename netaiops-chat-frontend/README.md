# NetAIOps Chat Frontend

AWS Bedrock AgentCore 기반 네트워크 AI 트러블슈팅 채팅 인터페이스

---

## 개요

NetAIOps Chat Frontend는 Streamlit 기반의 웹 채팅 인터페이스로,
배포된 AgentCore Runtime 에이전트와 대화형으로 상호작용할 수 있습니다.

**주요 기능:**
- AgentCore Runtime 연결 및 메시지 전송
- Claude 모델 선택 (Opus 4.6, Opus 4.5, Sonnet 4)
- 대화 기록 관리 및 내보내기
- 응답 피드백 제출
- 사용된 도구 및 메타데이터 표시

---

## 디렉토리 구조

```
netaiops-chat-frontend/
├── README.md                 # 이 문서
├── requirements.txt          # Python 의존성
├── Dockerfile               # 컨테이너 빌드 설정
└── src/
    ├── app.py               # Streamlit 메인 앱
    ├── components/
    │   ├── chat.py          # 채팅 UI 컴포넌트
    │   └── config.py        # AgentCore 설정 UI
    ├── models/
    │   └── message.py       # 메시지 모델
    └── services/
        └── agentcore_client.py  # AgentCore API 클라이언트
```

---

## 빠른 시작

### 사전 요구사항

- Python 3.11+
- 배포된 AgentCore Runtime (ARN 필요)
- Cognito JWT 토큰

### 로컬 실행

```bash
cd netaiops-chat-frontend

# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 앱 실행
cd src
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속

### Docker 실행

```bash
cd netaiops-chat-frontend

# 이미지 빌드
docker build -t netaiops-chat .

# 컨테이너 실행
docker run -p 8501:8501 netaiops-chat
```

---

## 설정 방법

### 1. Agent Runtime ARN 확인

```bash
# 배포된 런타임 목록 확인
bedrock-agentcore list-runtimes

# 출력 예시:
# arn:aws:bedrock-agentcore:ap-northeast-2:123456789012:runtime/my-agent-abc123
```

### 2. JWT 토큰 발급

**방법 1: AWS CLI 사용**
```bash
# Cognito 클라이언트 ID 확인
CLIENT_ID=$(aws ssm get-parameter \
  --name "/a2a/app/performance/agentcore/netaiops-cognito/machine_client_id" \
  --query "Parameter.Value" --output text)

# 토큰 발급 (사용자 인증 필요)
aws cognito-idp initiate-auth \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id $CLIENT_ID \
  --auth-parameters USERNAME=<user>,PASSWORD=<pass>
```

**방법 2: Client Credentials Flow**
```bash
# 토큰 URL 확인
TOKEN_URL=$(aws ssm get-parameter \
  --name "/a2a/app/performance/agentcore/netaiops-cognito/cognito_token_url" \
  --query "Parameter.Value" --output text)

# 클라이언트 시크릿 확인
CLIENT_SECRET=$(aws ssm get-parameter \
  --name "/a2a/app/performance/agentcore/netaiops-cognito/machine_client_secret" \
  --query "Parameter.Value" --output text)

# 토큰 요청
curl -X POST $TOKEN_URL \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET"
```

---

## 사용 예시

### 네트워크 트러블슈팅 질문 예시

```
- "10.0.1.100에서 10.0.2.50으로 연결이 안됩니다. 원인을 분석해주세요."
- "DNS 조회 실패의 원인을 분석해주세요."
- "VPC 피어링 연결 상태를 확인해주세요."
- "보안 그룹 규칙에서 포트 443이 열려있는지 확인해주세요."
- "최근 1시간 동안의 네트워크 플로우 로그를 분석해주세요."
```

---

## 지원 모델

| 모델 | 모델 ID | 특성 |
|------|---------|------|
| Claude Opus 4.6 | global.anthropic.claude-opus-4-6-v1 | 최신, 최고 성능 |
| Claude Opus 4.5 | global.anthropic.claude-opus-4-5-20251101-v1:0 | 고성능 |
| Claude Sonnet 4 | global.anthropic.claude-sonnet-4-20250514-v1:0 | 빠른 응답, 비용 효율 |

---

## 지원 리전

| 리전 | 설명 |
|------|------|
| ap-northeast-2 | 서울 (기본값) |
| us-east-1 | 버지니아 북부 |
| us-west-2 | 오레곤 |
| eu-west-1 | 아일랜드 |
| ap-northeast-1 | 도쿄 |
| ap-southeast-1 | 싱가포르 |

---

## 문제 해결

| 증상 | 원인 | 해결 방법 |
|------|------|-----------|
| 연결 오류 | Runtime ARN 오류 | ARN 형식 확인, bedrock-agentcore list-runtimes 실행 |
| 401 Unauthorized | JWT 토큰 만료 | 새 토큰 발급 |
| 타임아웃 | 에이전트 응답 지연 | 재시도 또는 더 간단한 질문 시도 |
| 빈 응답 | 에이전트 미배포 | bedrock-agentcore deploy 확인 |

---

## 라이선스

이 프로젝트는 NetAIOps 워크샵의 일부입니다.
