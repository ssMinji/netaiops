# NetAIOps Workshop - Multi-Region Deployment Guide

## Environment Configuration

| 항목 | 값 |
|------|-----|
| AWS Profile | `netaiops-deploy` |
| AWS Account | `175678592674` |
| Agent Region (Virginia) | `us-east-1` |
| EKS Region (Oregon) | `us-west-2` |
| EKS Cluster | `netaiops-eks-cluster` |
| Bedrock Model | `global.anthropic.claude-opus-4-6-v1` |

## Region Split Strategy

```
us-east-1 (Virginia)                    us-west-2 (Oregon)
├── Bedrock AgentCore Runtime           ├── EKS Cluster (netaiops-eks-cluster)
├── Cognito User Pool                   ├── EKS Workloads (retail-store, istio-sample)
├── MCP Gateway                         ├── CloudWatch Container Insights
├── Lambda Functions                    ├── CloudWatch Alarms
├── IAM Roles                           ├── SNS Topic
├── SSM Parameters                      ├── OpenSearch (netaiops-logs)
└── S3 (CFn templates)                  └── AMP Workspace (Module 7)
```

## Common Setup

```bash
# AWS Profile 설정
export AWS_PROFILE=netaiops-deploy

# kubectl 연결 (Oregon EKS)
aws eks update-kubeconfig --name netaiops-eks-cluster --region us-west-2 --profile netaiops-deploy

# 확인
aws sts get-caller-identity --query Account --output text  # → 175678592674
kubectl get nodes                                           # → 2 nodes Ready
```

---

## Module 5: K8s Diagnostics Agent

### SSM Prefix: `/a2a/app/k8s/agentcore/`

### 배포 순서

```bash
export AWS_PROFILE=netaiops-deploy

# 1. Cognito + IAM (Virginia)
aws cloudformation deploy \
  --template-file workshop-module-5/module-5/agentcore-k8s-agent/prerequisite/k8s-agentcore-cognito.yaml \
  --stack-name k8s-agentcore-cognito \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 2. EKS MCP Server 배포 (Virginia - AgentCore Runtime)
cd workshop-module-5/module-5/agentcore-k8s-agent/prerequisite/eks-mcp-server
bash deploy-eks-mcp-server.sh

# 3. EKS 워크로드 배포 (Oregon)
cd workshop-module-5/eks-sample-workload
bash deploy-eks-workload.sh

# 4. K8s Agent 배포 (Virginia - AgentCore Runtime)
cd workshop-module-5/module-5/agentcore-k8s-agent
agentcore deploy

# 5. Gateway 생성 (Virginia)
python scripts/agentcore_gateway.py create
```

---

## Module 6: Incident Analysis Agent

### SSM Prefix: `/app/incident/agentcore/`

### 배포 순서

```bash
export AWS_PROFILE=netaiops-deploy

# 1. Cognito + IAM (Virginia)
aws cloudformation deploy \
  --template-file workshop-module-6/module-6/agentcore-incident-agent/prerequisite/incident-agentcore-cognito.yaml \
  --stack-name incident-agentcore-cognito \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# 2. Lambda 배포 (Virginia)
cd workshop-module-6/module-6/prerequisite
bash deploy-incident-lambdas.sh

# 3. CloudWatch Alarms 설정 (Oregon)
bash setup-alarms.sh

# 4. Incident Agent 배포 (Virginia - AgentCore Runtime)
cd workshop-module-6/module-6/agentcore-incident-agent
agentcore deploy

# 5. Gateway 생성 (Virginia)
python scripts/agentcore_gateway.py create
```

---

## Module 7: Istio Service Mesh Diagnostics Agent

### SSM Prefix: `/app/istio/agentcore/`

### 전제 조건
- Module 5의 EKS MCP Server가 이미 배포되어 있어야 함 (Gateway의 mcpServer 타겟으로 재사용)
- EKS 클러스터에 kubectl 연결 가능

### 배포 순서

```bash
export AWS_PROFILE=netaiops-deploy

# ===== Step 1: Cognito + IAM (Virginia, us-east-1) =====
aws cloudformation deploy \
  --template-file workshop-module-7/module-7/prerequisite/istio-agentcore-cognito.yaml \
  --stack-name istio-agentcore-cognito \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# ===== Step 2: Istio 설치 (Oregon EKS, us-west-2) =====
bash workshop-module-7/module-7/prerequisite/setup-istio.sh

# ===== Step 3: AMP + ADOT Collector (Oregon, us-west-2) =====
bash workshop-module-7/module-7/prerequisite/setup-amp.sh

# ===== Step 4: 샘플 워크로드 배포 (Oregon EKS) =====
# retail-store 사이드카 주입 + istio-sample-app (Bookinfo) 배포
bash workshop-module-7/module-7/prerequisite/setup-sample-app.sh

# ===== Step 5: Prometheus Lambda 배포 (Virginia, us-east-1) =====
bash workshop-module-7/module-7/prerequisite/deploy-istio-lambdas.sh

# ===== Step 6: Agent 배포 (Virginia - AgentCore Runtime) =====
cd workshop-module-7/module-7/agentcore-istio-agent
agentcore deploy

# ===== Step 7: Gateway 생성 (Virginia) =====
# mcpServer 타겟 (EKS MCP Server 재사용) + Lambda 타겟 (Prometheus) 하이브리드
python scripts/agentcore_gateway.py create

# ===== Step 8: Frontend 재빌드 =====
cd app/frontend && npm run build
```

### 검증

```bash
# Istio 설치 확인
istioctl verify-install
kubectl get pods -n istio-system

# AMP 메트릭 확인
AMP_ENDPOINT=$(aws ssm get-parameter --name /app/istio/agentcore/amp_query_endpoint \
  --query 'Parameter.Value' --output text --region us-east-1)
# awscurl "$AMP_ENDPOINT/api/v1/query?query=istio_requests_total"

# 샘플 앱 확인
kubectl get pods -n istio-sample
kubectl get pods -n retail-store

# Lambda 확인
aws lambda invoke --function-name istio-prometheus-tools \
  --payload '{"method":"tools/list"}' /tmp/out.json --region us-east-1
cat /tmp/out.json

# Gateway 타겟 확인
python scripts/agentcore_gateway.py list-targets
```

### Fault Injection 테스트

```bash
# 적용
kubectl apply -f workshop-module-7/sample-workload/fault-injection/fault-delay-reviews.yaml
kubectl apply -f workshop-module-7/sample-workload/fault-injection/fault-abort-ratings.yaml
kubectl apply -f workshop-module-7/sample-workload/fault-injection/circuit-breaker.yaml

# 제거
kubectl delete -f workshop-module-7/sample-workload/fault-injection/ --ignore-not-found
```

---

## Frontend (통합 Agent Hub)

위치: `app/`

```bash
# 개발 모드
cd app/frontend && npm run dev    # React dev server (port 5173)
cd app/backend && uvicorn main:app --reload --port 8000  # FastAPI

# 프로덕션 빌드
cd app/frontend && npm run build
# static 파일이 app/backend/static/ 으로 복사됨
# uvicorn main:app --host 0.0.0.0 --port 8000
```

### 지원 에이전트

| Agent | Icon | SSM Prefix | Module |
|-------|------|-----------|--------|
| K8s Diagnostics | ☸ | `/a2a/app/k8s/agentcore` | 5 |
| Incident Analysis | 🔍 | `/app/incident/agentcore` | 6 |
| Istio Mesh Diagnostics | ⚡ | `/app/istio/agentcore` | 7 |

---

## SSM Parameter Convention

각 모듈은 고유한 SSM prefix를 사용합니다:

```
/{prefix}/
  cognito_pool_id          # Cognito User Pool ID
  cognito_domain           # Cognito 도메인
  cognito_provider         # Cognito Provider 이름
  cognito_discovery_url    # OIDC Discovery URL
  cognito_token_url        # Token 엔드포인트
  machine_client_id        # M2M Client ID
  machine_client_secret    # M2M Client Secret
  web_client_id            # Web Client ID
  cognito_auth_scope       # OAuth2 Scope
  gateway_id               # MCP Gateway ID
  gateway_name             # MCP Gateway 이름
  gateway_arn              # MCP Gateway ARN
  gateway_url              # MCP Gateway URL
  gateway_iam_role         # Gateway 실행 IAM Role ARN
  agent_runtime_arn        # AgentCore Runtime ARN
  memory_id                # AgentCore Memory ID
  user_id                  # 기본 User ID
```

## Troubleshooting

```bash
# AWS 계정 확인
aws sts get-caller-identity --profile netaiops-deploy

# EKS 연결 갱신
aws eks update-kubeconfig --name netaiops-eks-cluster --region us-west-2 --profile netaiops-deploy

# SSM 파라미터 조회
aws ssm get-parameters-by-path --path /app/istio/agentcore --recursive --region us-east-1 --profile netaiops-deploy

# AgentCore 런타임 상태
agentcore status

# CloudFormation 스택 상태
aws cloudformation describe-stacks --stack-name istio-agentcore-cognito --region us-east-1 --query 'Stacks[0].StackStatus'
```
