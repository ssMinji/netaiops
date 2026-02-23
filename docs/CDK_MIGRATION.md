# CDK Migration Guide: NetAIOps Modules 5 & 6

## 개요

Module 5(K8s Diagnostics)와 Module 6(Incident Analysis)의 인프라를 CloudFormation YAML + Shell 스크립트에서 **CDK TypeScript** 단일 프로젝트(`infra-cdk/`)로 전환했습니다.

### 전환 전

```
workshop-module-5/
  └── prerequisite/
      ├── k8s-agentcore-cognito.yaml          # CFN 템플릿 (수동 배포)
      └── setup_agentcore.py / agentcore_gateway.py  # Python 스크립트 (수동 실행)

workshop-module-6/
  └── prerequisite/
      ├── cognito.yaml                        # CFN 템플릿
      ├── deploy-incident-lambdas.sh          # Shell 스크립트 (Docker build + ECR push + Lambda 생성)
      ├── setup-alarms.sh                     # Shell 스크립트 (us-west-2 SNS + CloudWatch)
      └── agentcore_gateway.py                # Python 스크립트
```

**문제점**: 5~6단계 수동 실행, 순서 의존성 관리 불가, 롤백 어려움

### 전환 후

```
infra-cdk/
  └── cdk deploy --all                        # 단일 명령으로 전체 배포
```

**개선**: 의존성 자동 해결, Docker 이미지 자동 빌드/푸시, 롤백 지원, IaC 단일 소스

---

## 아키텍처

```
NetAIOpsInfraStack (Root)
├── Module5Stack (NestedStack) ─── 46 리소스
│   ├── Cognito (2 User Pool: K8sAgentPool + EksMcpServerPool)
│   ├── IAM (Gateway 실행 역할)
│   ├── Gateway (mcpServer 타겟 + OAuth2 자격 증명 공급자)
│   └── Runtime (AgentCore Runtime)
│
├── Module6Stack (NestedStack) ─── 54 리소스
│   ├── Cognito (1 User Pool: IncidentAnalysisPool)
│   ├── IAM (Gateway 실행 역할 + Lambda 실행 역할)
│   ├── Lambdas (6개 Docker Lambda)
│   ├── Gateway (3개 Lambda 타겟: Datadog, OpenSearch, ContainerInsight)
│   ├── Runtime (AgentCore Runtime)
│   └── Monitoring (Custom Resource → us-west-2 SNS + CloudWatch 알람)
│
└── SSM Parameters (모든 구성값 자동 저장)
```

---

## 파일 구조

```
infra-cdk/
├── package.json                             # 의존성 (aws-cdk-lib, constructs)
├── tsconfig.json                            # TypeScript 설정
├── cdk.json                                 # CDK 앱 설정
├── bin/
│   └── netaiops-infra.ts                    # CDK 앱 진입점
├── lib/
│   ├── config.ts                            # 상수 (계정, 리전, 클러스터명, SSM 경로, 도구 스키마)
│   ├── constructs/                          # 재사용 가능 L3 구성체
│   │   ├── cognito-auth.ts                  # Cognito UserPool + ResourceServer + 클라이언트 + SSM
│   │   ├── mcp-gateway.ts                   # Gateway + 타겟 (mcpServer/Lambda) + OAuth2 공급자
│   │   ├── docker-lambda.ts                 # DockerImageFunction 래퍼
│   │   └── cross-region-alarm.ts            # 교차 리전 SNS+알람 Custom Resource
│   └── stacks/
│       ├── root-stack.ts                    # 루트 스택 (Module5 + Module6 조합)
│       ├── module5/
│       │   ├── module5-stack.ts             # Module 5 NestedStack
│       │   ├── cognito-stack.ts             # 2개 User Pool + IAM 역할
│       │   ├── gateway-stack.ts             # mcpServer 타겟 + OAuth2
│       │   └── runtime-stack.ts             # AgentCore Runtime
│       └── module6/
│           ├── module6-stack.ts             # Module 6 NestedStack
│           ├── cognito-stack.ts             # 1개 User Pool + 2개 IAM 역할
│           ├── lambda-stack.ts              # 6개 Docker Lambda
│           ├── gateway-stack.ts             # 3개 Lambda 타겟 (도구 스키마 포함)
│           ├── runtime-stack.ts             # AgentCore Runtime
│           └── monitoring-stack.ts          # 교차 리전 알람/SNS
├── lambda-src/module6/                      # Lambda 소스 심볼릭 링크
│   ├── datadog -> workshop-module-6/.../lambda-datadog/python
│   ├── opensearch -> workshop-module-6/.../lambda-opensearch/python
│   ├── container-insight -> workshop-module-6/.../lambda-container-insight/python
│   ├── chaos -> workshop-module-6/.../lambda-chaos/python
│   ├── alarm-trigger -> workshop-module-6/.../lambda-alarm-trigger/python
│   └── github -> workshop-module-6/.../lambda-github/python
└── agent-src/                               # 에이전트 소스 심볼릭 링크
    ├── module5 -> workshop-module-5/.../agentcore-k8s-agent
    └── module6 -> workshop-module-6/.../agentcore-incident-agent
```

---

## 기존 리소스 매핑

### Module 5

| 기존 (CFN/Script) | CDK 구현 | 파일 |
|---|---|---|
| `k8s-agentcore-cognito.yaml` → UserPool | `CognitoAuth` 구성체 (K8sAgentPool) | `module5/cognito-stack.ts` |
| `k8s-agentcore-cognito.yaml` → RuntimeUserPool | `CognitoAuth` 구성체 (EksMcpServerPool) | `module5/cognito-stack.ts` |
| `k8s-agentcore-cognito.yaml` → AgentCoreExecutionRole | `iam.Role` (동일 정책) | `module5/cognito-stack.ts` |
| `agentcore_gateway.py` → create_gateway() | `McpGateway` 구성체 | `module5/gateway-stack.ts` |
| `agentcore_gateway.py` → OAuth2 Provider | `OAuth2CredentialProvider` 구성체 | `module5/gateway-stack.ts` |
| `setup_agentcore.py` → Runtime | `CfnResource(AWS::BedrockAgentCore::Runtime)` | `module5/runtime-stack.ts` |
| 24개 SSM 파라미터 | 자동 생성 (동일 경로) | 각 스택에 분산 |

### Module 6

| 기존 (CFN/Script) | CDK 구현 | 파일 |
|---|---|---|
| `cognito.yaml` → UserPool | `CognitoAuth` 구성체 (IncidentAnalysisPool) | `module6/cognito-stack.ts` |
| `cognito.yaml` → AgentCoreExecutionRole | `iam.Role` (동일 정책) | `module6/cognito-stack.ts` |
| `deploy-incident-lambdas.sh` → IAM 역할 | `iam.Role` (incident-tools-lambda-role) | `module6/cognito-stack.ts` |
| `deploy-incident-lambdas.sh` → 6개 Lambda | `DockerLambda` 구성체 × 6 | `module6/lambda-stack.ts` |
| `agentcore_gateway.py` → Gateway + 3 타겟 | `McpGateway` 구성체 (Lambda 타겟) | `module6/gateway-stack.ts` |
| `agentcore_gateway.py` → 도구 스키마 | `config.ts` → toolSchemas | `lib/config.ts` |
| `setup-alarms.sh` → SNS + 3 알람 | `CrossRegionAlarm` Custom Resource | `module6/monitoring-stack.ts` |

---

## 배포 방법

### 사전 요구사항

1. **CDK Bootstrap** (최초 1회):
   ```bash
   cd infra-cdk
   npx cdk bootstrap aws://175678592674/us-east-1 --profile netaiops-deploy
   npx cdk bootstrap aws://175678592674/us-west-2 --profile netaiops-deploy
   ```

2. **EKS MCP Server 배포** (CLI로 수동 배포 후 ARN을 SSM에 저장):
   ```bash
   aws ssm put-parameter \
     --name "/a2a/app/k8s/agentcore/eks_mcp_server_arn" \
     --value "arn:aws:bedrock-agentcore:us-east-1:175678592674:runtime/..." \
     --type String --overwrite \
     --region us-east-1 --profile netaiops-deploy
   ```

3. **외부 SSM 파라미터 설정**:
   ```bash
   # Datadog
   aws ssm put-parameter --name /app/incident/datadog/api_key --value YOUR_KEY --type SecureString
   aws ssm put-parameter --name /app/incident/datadog/app_key --value YOUR_KEY --type SecureString

   # OpenSearch
   aws ssm put-parameter --name /app/incident/opensearch/endpoint --value YOUR_ENDPOINT --type String

   # GitHub PAT
   aws ssm put-parameter --name /app/incident/github/pat --value YOUR_TOKEN --type SecureString
   ```

4. **EKS RBAC** (Chaos Lambda용):
   ```bash
   kubectl apply -f workshop-module-6/module-6/prerequisite/chaos-rbac.yaml
   ```

### 배포 실행

```bash
cd infra-cdk

# 전체 배포
npx cdk deploy --all --profile netaiops-deploy

# 특정 스택만 배포
npx cdk deploy NetAIOpsInfraStack/Module5 --profile netaiops-deploy
npx cdk deploy NetAIOpsInfraStack/Module6 --profile netaiops-deploy
```

### 배포 확인

```bash
# 템플릿 확인 (배포 전 검증)
npx cdk synth

# diff 확인
npx cdk diff --profile netaiops-deploy

# Module 5 - K8s 에이전트 호출
aws bedrock-agentcore invoke-runtime \
  --name a2a_k8s_agent_runtime \
  --payload '{"prompt": "EKS 클러스터 상태를 확인해줘"}' \
  --region us-east-1

# Module 6 - Chaos 시나리오 트리거
aws lambda invoke --function-name incident-chaos-tools \
  --payload '{"name":"chaos-cpu-stress","arguments":{}}' \
  --region us-east-1 /dev/stdout

# GitHub 이슈 확인
gh issue list --repo ssMinji/netaiops --label incident
```

### 삭제

```bash
npx cdk destroy --all --profile netaiops-deploy
```

---

## 재사용 가능 구성체

### CognitoAuth

Cognito User Pool + OAuth2 리소스 서버 + M2M/Web 클라이언트 + SSM 파라미터를 한 번에 생성합니다.

```typescript
new CognitoAuth(this, 'Auth', {
  poolName: 'MyPool',
  domainPrefix: 'my-app',
  resourceServerIdentifier: 'my-server',
  scopes: [{ name: 'invoke', description: 'Invoke' }],
  machineClientName: 'MyMachineClient',
  webClientName: 'MyWebClient',       // 선택
  webCallbackUrl: 'http://localhost/', // 선택
  ssmPrefix: '/app/my/agentcore',
  ssmKeyPrefix: '',                    // 선택 (키 접두사)
});
```

### McpGateway

mcpServer 타겟(OAuth2 인증)과 Lambda 타겟(IAM 인증) 모두 지원합니다.

```typescript
new McpGateway(this, 'Gateway', {
  gatewayName: 'my-gateway',
  description: 'My Gateway',
  executionRoleArn: role.roleArn,
  allowedClientId: auth.machineClient.userPoolClientId,
  discoveryUrl: '...',
  mcpServerTargets: [{ ... }],  // mcpServer 타겟 (Module 5)
  lambdaTargets: [{ ... }],     // Lambda 타겟 (Module 6)
  ssmPrefix: '/app/my/agentcore',
});
```

### CrossRegionAlarm

Custom Resource Lambda를 통해 다른 리전에 SNS 토픽 + CloudWatch 알람을 생성하고, 현재 리전의 Lambda를 구독합니다.

```typescript
new CrossRegionAlarm(this, 'Alarms', {
  alarmRegion: 'us-west-2',
  lambdaRegion: 'us-east-1',
  snsTopicName: 'my-alarm-topic',
  clusterName: 'my-cluster',
  alarmTriggerLambdaArn: lambda.functionArn,
  alarms: [{ name: 'my-alarm', metricName: 'pod_cpu_utilization', ... }],
  ssmPrefix: '/app/my/agentcore',
});
```

---

## SSM 파라미터 경로 (변경 없음)

기존 스크립트와 동일한 SSM 경로를 사용하므로, 에이전트 코드 변경이 불필요합니다.

### Module 5 (`/a2a/app/k8s/agentcore/`)

| 파라미터 | 용도 |
|---|---|
| `machine_client_id` / `machine_client_secret` | M2M OAuth2 클라이언트 |
| `web_client_id` | PKCE 웹 클라이언트 |
| `userpool_id` | Cognito User Pool ID |
| `cognito_provider` / `cognito_discovery_url` | BedrockAgentCore 인증 |
| `cognito_token_url` / `cognito_auth_url` / `cognito_domain` | OAuth2 엔드포인트 |
| `cognito_auth_scope` | OAuth2 스코프 |
| `eks_mcp_*` | Runtime User Pool (Gateway→MCP Server 인증) |
| `gateway_id` / `gateway_name` / `gateway_arn` / `gateway_url` | Gateway 정보 |
| `gateway_iam_role` | IAM 실행 역할 ARN |
| `runtime_arn` / `runtime_name` | AgentCore Runtime 정보 |

### Module 6 (`/app/incident/agentcore/`)

| 파라미터 | 용도 |
|---|---|
| `machine_client_id` / `machine_client_secret` | M2M OAuth2 클라이언트 |
| `web_client_id` | PKCE 웹 클라이언트 |
| `userpool_id` | Cognito User Pool ID |
| `cognito_*` | OAuth2 인증 엔드포인트 |
| `gateway_*` | Gateway 정보 |
| `*_lambda_arn` (6개) | Lambda 함수 ARN |
| `sns_topic_arn` | SNS 토픽 ARN (알람 트리거) |
| `runtime_arn` / `runtime_name` | AgentCore Runtime 정보 |

---

## 기존 스택에서 CDK로 전환하기

기존 CloudFormation 스택/스크립트로 배포된 환경이 있는 경우, 아래 3가지 시나리오 중 선택합니다.

### 시나리오 A: 클린 배포 (기존 스택 삭제 후 CDK 배포)

가장 단순한 방법입니다. 서비스 다운타임이 허용되는 개발/테스트 환경에 적합합니다.

**1단계: 기존 리소스 정리 (역순으로 삭제)**

```bash
PROFILE="netaiops-deploy"
REGION="us-east-1"
ALARM_REGION="us-west-2"

# --- Module 6 정리 ---

# 6-1. CloudWatch 알람 삭제 (us-west-2)
aws cloudwatch delete-alarms \
  --alarm-names netaiops-cpu-spike netaiops-pod-restarts netaiops-node-cpu-high \
  --region $ALARM_REGION --profile $PROFILE

# 6-2. SNS 토픽 삭제 (us-west-2)
SNS_ARN=$(aws ssm get-parameter --name /app/incident/agentcore/sns_topic_arn \
  --query Parameter.Value --output text --region $REGION --profile $PROFILE 2>/dev/null)
if [ -n "$SNS_ARN" ]; then
  aws sns delete-topic --topic-arn $SNS_ARN --region $ALARM_REGION --profile $PROFILE
fi

# 6-3. AgentCore Gateway 삭제 (Python 스크립트 또는 수동)
GATEWAY_ID=$(aws ssm get-parameter --name /app/incident/agentcore/gateway_id \
  --query Parameter.Value --output text --region $REGION --profile $PROFILE 2>/dev/null)
if [ -n "$GATEWAY_ID" ]; then
  # 타겟 먼저 삭제
  for TARGET_ID in $(aws bedrock-agentcore-control list-gateway-targets \
    --gateway-identifier $GATEWAY_ID --query 'items[].targetId' --output text \
    --region $REGION --profile $PROFILE 2>/dev/null); do
    aws bedrock-agentcore-control delete-gateway-target \
      --gateway-identifier $GATEWAY_ID --target-id $TARGET_ID \
      --region $REGION --profile $PROFILE
  done
  aws bedrock-agentcore-control delete-gateway \
    --gateway-identifier $GATEWAY_ID --region $REGION --profile $PROFILE
fi

# 6-4. AgentCore Runtime 삭제
RUNTIME_ARN=$(aws ssm get-parameter --name /app/incident/agentcore/runtime_arn \
  --query Parameter.Value --output text --region $REGION --profile $PROFILE 2>/dev/null)
if [ -n "$RUNTIME_ARN" ]; then
  aws bedrock-agentcore-control delete-runtime \
    --runtime-identifier $RUNTIME_ARN --region $REGION --profile $PROFILE
fi

# 6-5. Lambda 함수 삭제
for FN in incident-datadog-tools incident-opensearch-tools incident-container-insight-tools \
  incident-chaos-tools incident-alarm-trigger incident-github-tools; do
  aws lambda delete-function --function-name $FN --region $REGION --profile $PROFILE 2>/dev/null
done

# 6-6. IAM 역할 삭제
aws iam delete-role-policy --role-name incident-tools-lambda-role \
  --policy-name IncidentToolsCombinedPolicy --profile $PROFILE 2>/dev/null
aws iam detach-role-policy --role-name incident-tools-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
  --profile $PROFILE 2>/dev/null
aws iam delete-role --role-name incident-tools-lambda-role --profile $PROFILE 2>/dev/null

# 6-7. Cognito CFN 스택 삭제
aws cloudformation delete-stack --stack-name incident-analysis-cognito \
  --region $REGION --profile $PROFILE 2>/dev/null
aws cloudformation wait stack-delete-complete --stack-name incident-analysis-cognito \
  --region $REGION --profile $PROFILE 2>/dev/null

# 6-8. SSM 파라미터 삭제
aws ssm delete-parameters --names \
  /app/incident/agentcore/gateway_id /app/incident/agentcore/gateway_name \
  /app/incident/agentcore/gateway_arn /app/incident/agentcore/gateway_url \
  /app/incident/agentcore/runtime_arn /app/incident/agentcore/runtime_name \
  /app/incident/agentcore/datadog_lambda_arn /app/incident/agentcore/opensearch_lambda_arn \
  /app/incident/agentcore/container_insight_lambda_arn /app/incident/agentcore/chaos_lambda_arn \
  /app/incident/agentcore/alarm_trigger_lambda_arn /app/incident/agentcore/github_lambda_arn \
  /app/incident/agentcore/sns_topic_arn \
  --region $REGION --profile $PROFILE 2>/dev/null

# --- Module 5 정리 ---

# 5-1. AgentCore Gateway 삭제
GATEWAY_ID=$(aws ssm get-parameter --name /a2a/app/k8s/agentcore/gateway_id \
  --query Parameter.Value --output text --region $REGION --profile $PROFILE 2>/dev/null)
if [ -n "$GATEWAY_ID" ]; then
  for TARGET_ID in $(aws bedrock-agentcore-control list-gateway-targets \
    --gateway-identifier $GATEWAY_ID --query 'items[].targetId' --output text \
    --region $REGION --profile $PROFILE 2>/dev/null); do
    aws bedrock-agentcore-control delete-gateway-target \
      --gateway-identifier $GATEWAY_ID --target-id $TARGET_ID \
      --region $REGION --profile $PROFILE
  done
  aws bedrock-agentcore-control delete-gateway \
    --gateway-identifier $GATEWAY_ID --region $REGION --profile $PROFILE
fi

# 5-2. OAuth2 Credential Provider 삭제
aws bedrock-agentcore-control delete-oauth2-credential-provider \
  --oauth2-credential-provider-name eks-mcp-server-oauth \
  --region $REGION --profile $PROFILE 2>/dev/null

# 5-3. AgentCore Runtime 삭제 (에이전트만, EKS MCP Server는 유지)
RUNTIME_ARN=$(aws ssm get-parameter --name /a2a/app/k8s/agentcore/runtime_arn \
  --query Parameter.Value --output text --region $REGION --profile $PROFILE 2>/dev/null)
if [ -n "$RUNTIME_ARN" ]; then
  aws bedrock-agentcore-control delete-runtime \
    --runtime-identifier $RUNTIME_ARN --region $REGION --profile $PROFILE
fi

# 5-4. Cognito CFN 스택 삭제
aws cloudformation delete-stack --stack-name k8s-agentcore-cognito \
  --region $REGION --profile $PROFILE 2>/dev/null
aws cloudformation wait stack-delete-complete --stack-name k8s-agentcore-cognito \
  --region $REGION --profile $PROFILE 2>/dev/null

# 5-5. SSM 파라미터 삭제 (eks_mcp_server_arn은 유지 - EKS MCP Server는 CDK 외부 관리)
aws ssm delete-parameters --names \
  /a2a/app/k8s/agentcore/gateway_id /a2a/app/k8s/agentcore/gateway_name \
  /a2a/app/k8s/agentcore/gateway_arn /a2a/app/k8s/agentcore/gateway_url \
  /a2a/app/k8s/agentcore/runtime_arn /a2a/app/k8s/agentcore/runtime_name \
  --region $REGION --profile $PROFILE 2>/dev/null

echo "기존 리소스 정리 완료"
```

**2단계: CDK 배포**

```bash
cd infra-cdk
npx cdk deploy --all --profile netaiops-deploy
```

**3단계: 검증**

```bash
# SSM 파라미터가 재생성되었는지 확인
aws ssm get-parameters-by-path --path /a2a/app/k8s/agentcore/ --recursive \
  --query 'Parameters[].Name' --output table --region us-east-1 --profile netaiops-deploy

aws ssm get-parameters-by-path --path /app/incident/agentcore/ --recursive \
  --query 'Parameters[].Name' --output table --region us-east-1 --profile netaiops-deploy
```

---

### 시나리오 B: 무중단 전환 (리소스 이름 분리 → 트래픽 전환 → 기존 스택 삭제)

프로덕션 환경에서 다운타임 없이 전환할 때 사용합니다.

**1단계: CDK 리소스 이름에 접미사 추가**

`lib/config.ts`에서 충돌 리소스 이름을 변경합니다:

```typescript
// 변경 전
agentPool: { name: 'K8sAgentPool', ... }
// 변경 후
agentPool: { name: 'K8sAgentPool-v2', ... }
```

변경 대상:
- Cognito User Pool 이름: `K8sAgentPool` → `K8sAgentPool-v2`
- Cognito Domain: `k8sagent` → `k8sagent-v2`
- IAM Role 이름: `netaiops-m5-gateway-execution-role` → 이미 고유 (충돌 없음)
- Lambda 함수 이름: `incident-datadog-tools` → `incident-datadog-tools-v2`
- SSM 경로: `/a2a/app/k8s/agentcore/` → `/a2a/app/k8s/agentcore-v2/`

**2단계: CDK 배포 (기존과 병렬 운영)**

```bash
cd infra-cdk && npx cdk deploy --all --profile netaiops-deploy
```

**3단계: 에이전트 코드 SSM 경로 업데이트**

에이전트 코드(`agent_config/utils.py`, `agent_config/access_token.py`)에서 SSM 경로를 새 경로로 변경합니다.

**4단계: 검증 후 기존 스택 삭제**

새 리소스가 정상 동작하면 기존 CFN 스택/리소스를 삭제합니다.

> 이 방식은 SSM 경로 변경으로 인해 에이전트 코드 수정이 필요합니다.

---

### 시나리오 C: CDK Import (기존 리소스를 CDK 관리로 가져오기)

기존 리소스를 삭제하지 않고 CDK 스택으로 "입양"합니다. 리소스 재생성 없이 관리 주체만 CDK로 변경됩니다.

> `cdk import`는 모든 리소스 유형을 지원하지 않습니다. Cognito, IAM, SSM, Lambda는 지원되지만
> BedrockAgentCore Gateway/Runtime 등 신규 서비스는 미지원일 수 있습니다.

**1단계: CDK 스택 빈 상태로 배포**

각 리소스의 `removalPolicy: RETAIN`을 설정하고, CDK 스택을 비어있는 상태로 배포합니다.

**2단계: 리소스 Import**

```bash
cd infra-cdk

# import 실행 (인터랙티브 - 기존 리소스 ID 입력 필요)
npx cdk import NetAIOpsInfraStack/Module5 --profile netaiops-deploy
npx cdk import NetAIOpsInfraStack/Module6 --profile netaiops-deploy
```

**3단계: 기존 CFN 스택에서 리소스 분리**

기존 CFN 스택에서 리소스를 `DeletionPolicy: Retain`으로 변경 후 스택을 삭제합니다.
이렇게 하면 리소스는 유지되고 스택만 삭제됩니다.

```bash
# 기존 스택 업데이트 (DeletionPolicy: Retain 추가) 후 삭제
aws cloudformation delete-stack --stack-name k8s-agentcore-cognito \
  --region us-east-1 --profile netaiops-deploy
```

> 이 방식은 가장 안전하지만, 지원되는 리소스 유형에 제한이 있고 절차가 복잡합니다.

---

### 시나리오 비교

| | A. 클린 배포 | B. 무중단 전환 | C. CDK Import |
|---|---|---|---|
| **다운타임** | 있음 (삭제→재생성) | 없음 | 없음 |
| **복잡도** | 낮음 | 중간 | 높음 |
| **에이전트 코드 변경** | 불필요 | 필요 (SSM 경로) | 불필요 |
| **Cognito 사용자 유지** | 불가 (재생성) | 새 풀 사용 | 유지 |
| **적합 환경** | 개발/테스트 | 프로덕션 | 프로덕션 (고급) |
| **권장** | **워크숍/PoC** | 스테이징 | 실 프로덕션 |

---

### 전환 체크리스트

- [ ] 기존 스택 이름 확인: `aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE`
- [ ] 기존 리소스 목록 백업: Gateway ID, Runtime ARN, Lambda ARN, SSM 파라미터 값
- [ ] EKS MCP Server ARN이 SSM에 존재하는지 확인 (`/a2a/app/k8s/agentcore/eks_mcp_server_arn`)
- [ ] 외부 SSM 파라미터 존재 확인 (Datadog keys, OpenSearch endpoint, GitHub PAT)
- [ ] CDK Bootstrap 완료 (us-east-1 + us-west-2)
- [ ] Docker 실행 중 확인
- [ ] 전환 시나리오 선택 (A/B/C)
- [ ] 전환 실행
- [ ] SSM 파라미터 재생성 확인
- [ ] 에이전트 호출 테스트
- [ ] CloudWatch 알람 동작 확인 (us-west-2)
- [ ] 기존 스택/리소스 정리 완료

---

## 주의사항

1. **EKS MCP Server ARN**: CDK 배포 전에 SSM에 수동 등록 필요 (CLI로 배포되는 리소스)
2. **Docker 빌드**: `cdk deploy` 시 Lambda Docker 이미지를 자동 빌드합니다. Docker가 실행 중이어야 합니다.
3. **교차 리전**: Module 6 알람/SNS는 Custom Resource Lambda가 us-west-2에 생성합니다.
4. **Lambda 소스**: `lambda-src/module6/`는 심볼릭 링크입니다. 원본 코드를 수정하면 CDK 배포 시 자동 반영됩니다.
5. **ECR 이미지**: CDK는 Lambda Docker 이미지를 CDK 전용 ECR 리포지토리(`cdk-hnb659fds-container-assets-*`)에 푸시합니다. 기존 수동 ECR 리포지토리(`incident-*-tools-repo`)와는 별개입니다.
