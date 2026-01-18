# NetAIOps CloudFormation 스택

이 디렉토리에는 NetAIOps 플랫폼을 위한 AWS CloudFormation 템플릿이 포함되어 있습니다.

## 개요

NetAIOps는 AWS Bedrock AgentCore 기반의 지능형 네트워크 트러블슈팅 및 모니터링 플랫폼입니다. 이 CloudFormation 스택들은 플랫폼 운영에 필요한 전체 인프라를 배포합니다.

## 스택 목록

| 파일 | 설명 | 배포 순서 |
|------|------|-----------|
| `sample-appication.yaml` | 기본 애플리케이션 인프라 (VPC, EC2, RDS, Lambda, API Gateway, S3) | 1단계 |
| `network-flow-monitor-enable.yaml` | Network Flow Monitor 서비스 활성화 | 2a단계 |
| `a2a-performance-agentcore-cognito.yaml` | A2A Performance Agent용 Cognito 인증 | 2b단계 |
| `module3-combined-setup.yaml` | 모듈 3 & 4 설치 (S3에서 다운로드) | 2c단계 |
| `network-flow-monitor-setup.yaml` | Network Flow Monitor 에이전트 설치 및 모니터 생성 | 3단계 |
| `trffice-mirroring-setup.yaml` | 트래픽 미러링 인프라 | 4단계 |

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    1단계: sample-appication                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ App VPC  │  │Reporting │  │   RDS    │  │ Lambda Functions │ │
│  │ Bastion  │  │   VPC    │  │ Database │  │   API Gateway    │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────┬───────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ 2a: NFM       │ │ 2b: Cognito   │ │ 2c: Modules   │
│ Enable        │ │ Auth          │ │ Setup         │
└───────┬───────┘ └───────────────┘ └───────────────┘
        │
        ▼
┌───────────────────────────────────────────────────┐
│           3단계: network-flow-monitor-setup        │
│  Network Flow Monitor 에이전트 설치 및 모니터 생성   │
└───────────────────────┬───────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────┐
│           4단계: trffice-mirroring-setup           │
│            트래픽 미러링 인프라 구성                 │
└───────────────────────────────────────────────────┘
```

## 배포 방법

### 방법 1: 배포 스크립트 사용 (권장)

```bash
cd /home/ec2-user/code/netaiops_v1/cfn_stack

# 전체 배포
./deploy.sh deploy-all

# 개별 배포
./deploy.sh deploy-base              # 기본 인프라만
./deploy.sh deploy-nfm               # Network Flow Monitor
./deploy.sh deploy-cognito           # Cognito 인증
./deploy.sh deploy-modules           # 모듈 설치
./deploy.sh deploy-traffic           # Traffic Mirroring

# 상태 확인
./deploy.sh status

# 전체 삭제
./deploy.sh delete-all
```

### 방법 2: AWS CLI 직접 사용

#### 1단계: 기본 애플리케이션 인프라

```bash
aws cloudformation deploy \
  --template-file sample-appication.yaml \
  --stack-name netaiops-sample-app \
  --parameter-overrides DBPassword=<your-password> \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --region us-east-1
```

#### 2a단계: Network Flow Monitor 서비스 활성화

```bash
aws cloudformation deploy \
  --template-file network-flow-monitor-enable.yaml \
  --stack-name netaiops-nfm-enable \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

#### 2b단계: Cognito 인증 (병렬 배포 가능)

```bash
aws cloudformation deploy \
  --template-file a2a-performance-agentcore-cognito.yaml \
  --stack-name netaiops-cognito \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

#### 2c단계: 모듈 설치 (병렬 배포 가능)

```bash
aws cloudformation deploy \
  --template-file module3-combined-setup.yaml \
  --stack-name netaiops-modules \
  --parameter-overrides SampleApplicationStackName=netaiops-sample-app \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

#### 3단계: Network Flow Monitor 설정

```bash
aws cloudformation deploy \
  --template-file network-flow-monitor-setup.yaml \
  --stack-name netaiops-nfm-setup \
  --parameter-overrides \
    SampleApplicationStackName=netaiops-sample-app \
    NetworkFlowMonitorEnableStackName=netaiops-nfm-enable \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

#### 4단계: 트래픽 미러링

```bash
aws cloudformation deploy \
  --template-file trffice-mirroring-setup.yaml \
  --stack-name netaiops-traffic-mirror \
  --parameter-overrides \
    SampleApplicationStackName=netaiops-sample-app \
    NetworkFlowMonitorStackName=netaiops-nfm-setup \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

## 파라미터 설명

### sample-appication.yaml

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `DBUsername` | `admin` | RDS 데이터베이스 관리자 사용자명 |
| `DBPassword` | `ReInvent2025!` | RDS 데이터베이스 관리자 비밀번호 |

### network-flow-monitor-setup.yaml

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `SampleApplicationStackName` | `sample-application` | 기본 인프라 스택 이름 |
| `NetworkFlowMonitorEnableStackName` | `network-flow-monitor-enable` | NFM 활성화 스택 이름 |
| `MonitorName` | `examplecorp-vpc-network-monitor` | 모니터 기본 이름 |
| `AppVPCId` | (자동) | App VPC ID (비워두면 스택에서 가져옴) |
| `ReportingVPCId` | (자동) | Reporting VPC ID |
| `BastionInstanceId` | (자동) | Bastion EC2 인스턴스 ID |
| `ReportingServerInstanceId` | (자동) | Reporting 서버 인스턴스 ID |

### a2a-performance-agentcore-cognito.yaml

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `UserPoolName` | `PerformancePool` | Cognito User Pool 이름 |
| `MachineAppClientName` | `PerformanceMachineClient` | 머신 앱 클라이언트 이름 |
| `WebAppClientName` | `PerformanceWebClient` | 웹 앱 클라이언트 이름 |

### module3-combined-setup.yaml

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `SampleApplicationStackName` | `sample-application` | 기본 인프라 스택 이름 |
| `S3BucketName` | `ws-assets-prod-iad-r-iad-ed304a55c2ca1aee` | 모듈 파일이 있는 S3 버킷 |
| `S3KeyPath` | `175c4803.../module-3.zip` | module-3.zip S3 경로 |
| `S3KeyPathModule4` | `175c4803.../module-4.zip` | module-4.zip S3 경로 |
| `TargetDirectory` | `/root` | 모듈 설치 대상 디렉토리 |

### trffice-mirroring-setup.yaml

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `SampleApplicationStackName` | `sample-application` | 기본 인프라 스택 이름 |
| `NetworkFlowMonitorStackName` | `network-flow-monitor` | NFM 설정 스택 이름 |
| `BastionInstanceId` | (자동) | 미러링할 Bastion 인스턴스 ID |
| `ReportingInstanceId` | (자동) | 미러링할 Reporting 인스턴스 ID |
| `TargetSubnetId` | (자동) | 미러링 타겟 인스턴스 서브넷 ID |

## 생성되는 주요 리소스

### sample-appication.yaml
- **네트워킹**: App VPC, Reporting VPC, Transit Gateway, 서브넷, NAT Gateway
- **컴퓨팅**: Bastion EC2, Reporting Server EC2
- **데이터베이스**: RDS MySQL
- **스토리지**: S3 버킷 (이미지 저장용)
- **서버리스**: Lambda 함수들, API Gateway
- **보안**: Security Groups, IAM 역할

### network-flow-monitor-enable.yaml
- Network Flow Monitor 서비스 연결 역할
- 서비스 활성화 Lambda 함수

### network-flow-monitor-setup.yaml
- Network Flow Monitor 스코프 및 모니터
- 에이전트 설치 Step Functions
- 모니터링 Lambda 함수

### a2a-performance-agentcore-cognito.yaml
- Cognito User Pool
- User Pool Client (Web, Machine)
- Resource Server
- IAM 역할 (BedrockAgentCore 권한 포함)

### module3-combined-setup.yaml
- 모듈 다운로드 및 설치 Lambda 함수
- SSM 명령 실행 리소스

### trffice-mirroring-setup.yaml
- Traffic Mirror Filter
- Traffic Mirror Target (EC2 인스턴스)
- Traffic Mirror Sessions
- 패킷 분석 S3 버킷

## 스택 삭제

스택을 삭제할 때는 **역순**으로 삭제해야 합니다:

```bash
# 배포 스크립트 사용
./deploy.sh delete-all

# 또는 수동 삭제
aws cloudformation delete-stack --stack-name netaiops-traffic-mirror
aws cloudformation delete-stack --stack-name netaiops-nfm-setup
aws cloudformation delete-stack --stack-name netaiops-modules
aws cloudformation delete-stack --stack-name netaiops-cognito
aws cloudformation delete-stack --stack-name netaiops-nfm-enable
aws cloudformation delete-stack --stack-name netaiops-sample-app
```

## 문제 해결

### 스택 배포 실패 시

1. CloudFormation 콘솔에서 이벤트 확인
2. 리소스 제한 확인 (VPC, EIP 등)
3. IAM 권한 확인

### 일반적인 오류

| 오류 | 원인 | 해결 방법 |
|------|------|-----------|
| `VPC limit exceeded` | VPC 개수 제한 | 기존 VPC 삭제 또는 한도 증가 요청 |
| `EIP limit exceeded` | Elastic IP 제한 | 기존 EIP 해제 또는 한도 증가 요청 |
| `Role already exists` | IAM 역할 중복 | 기존 역할 삭제 후 재시도 |
| `Stack dependency` | 의존성 스택 없음 | 선행 스택 먼저 배포 |

## 관련 문서

- [AWS CloudFormation 문서](https://docs.aws.amazon.com/cloudformation/)
- [AWS Bedrock AgentCore 문서](https://docs.aws.amazon.com/bedrock/)
- [Network Flow Monitor 문서](https://docs.aws.amazon.com/vpc/latest/network-flow-monitor/)

## 라이선스

이 프로젝트는 내부 사용을 위해 제작되었습니다.
