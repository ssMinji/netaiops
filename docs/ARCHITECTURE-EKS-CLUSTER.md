# NetAIOps EKS Cluster Architecture

## Overview

NetAIOps 프로젝트의 핵심 진단 대상인 Amazon EKS 클러스터 아키텍처.
`netaiops-eks-cluster`는 us-west-2에 배포되며, Module 5/6/7의 AI Agent들이 진단하는 워크로드 플랫폼 역할을 수행한다.

---

## 1. Cluster Specification

```
┌──────────────────────────────────────────────────────────────────┐
│                    netaiops-eks-cluster                           │
│                    Region: us-west-2                              │
│                    Kubernetes: 1.31                               │
│                    Provisioning: eksctl                           │
├──────────────────────────────────────────────────────────────────┤
│  Control Plane (AWS Managed)                                     │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────┐  │
│  │  API Server │ │ Controller │ │  Scheduler   │ │   etcd     │  │
│  │            │ │  Manager   │ │              │ │            │  │
│  └────────────┘ └────────────┘ └──────────────┘ └────────────┘  │
│                                                                  │
│  Logging: api, audit, authenticator, controllerManager, scheduler│
├──────────────────────────────────────────────────────────────────┤
│  Managed Node Group: ng-default                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  m5.large    │  │  m5.large    │  │  m5.large    │           │
│  │  30GB EBS    │  │  30GB EBS    │  │  30GB EBS    │           │
│  │  role:workers│  │  role:workers│  │  (auto-scale)│           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  Min: 2 / Desired: 2 / Max: 3                                   │
└──────────────────────────────────────────────────────────────────┘
```

| Item | Value |
|------|-------|
| Cluster Name | `netaiops-eks-cluster` |
| Region | `us-west-2` |
| Kubernetes Version | `1.31` |
| Node Group | `ng-default` (Managed) |
| Instance Type | `m5.large` (2 vCPU, 8GB RAM) |
| Node Count | 2~3 (Auto Scaling) |
| Volume | 30GB gp3 per node |
| IAM OIDC | Enabled (IRSA support) |
| VPC | eksctl auto-created, Single NAT Gateway |

---

## 2. VPC & Network Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  VPC (eksctl auto-created, us-west-2)                                   │
│                                                                         │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐       │
│  │  Public Subnet (AZ-a)       │  │  Public Subnet (AZ-b)       │       │
│  │  ┌───────────────────────┐  │  │                             │       │
│  │  │ NAT Gateway (Single)  │  │  │                             │       │
│  │  └───────────────────────┘  │  │                             │       │
│  │  ┌───────────────────────┐  │  │  ┌───────────────────────┐  │       │
│  │  │ ELB (UI Service)      │  │  │  │ ELB (Istio Ingress)   │  │       │
│  │  └───────────────────────┘  │  │  └───────────────────────┘  │       │
│  │  ┌────────┐  ┌────────┐    │  │  ┌────────┐                 │       │
│  │  │ Node 1 │  │ Node 3 │    │  │  │ Node 2 │                 │       │
│  │  │m5.large│  │(scale) │    │  │  │m5.large│                 │       │
│  │  └────────┘  └────────┘    │  │  └────────┘                 │       │
│  └─────────────────────────────┘  └─────────────────────────────┘       │
│                                                                         │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐       │
│  │  Private Subnet (AZ-a)      │  │  Private Subnet (AZ-b)      │       │
│  │  (unused by node group)     │  │  (unused by node group)     │       │
│  └─────────────────────────────┘  └─────────────────────────────┘       │
│                                                                         │
│  Internet Gateway ←→ Public Subnets (Nodes + ELBs)                     │
│  NAT Gateway      ←→ Private Subnets (created but not used by nodes)   │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Worker Node는 Public Subnet에 배치** (`privateNetworking: true`가 미설정 → eksctl 기본값 `false`)
- eksctl은 Public/Private Subnet + NAT Gateway를 모두 생성하지만, 노드 그룹은 Public Subnet 사용
- LoadBalancer 타입 Service의 ELB도 Public Subnet에 생성
- eksctl이 2-AZ 구성을 자동으로 생성

> **Note:** 프로덕션 환경에서는 `managedNodeGroups[].privateNetworking: true`를
> 설정하여 워커 노드를 Private Subnet에 배치하는 것이 권장됩니다.

---

## 3. Namespace & Workload Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│                     netaiops-eks-cluster                             │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Namespace: default (retail-store)                             │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │  │
│  │  │    UI    │ │ Catalog  │ │   Cart   │ │  Orders  │        │  │
│  │  │ (Next.js)│ │ Service  │ │ Service  │ │ Service  │        │  │
│  │  │  :80 LB  │ │          │ │          │ │          │        │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘        │  │
│  │       │            │            │            │               │  │
│  │       │       ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐        │  │
│  │       │       │Catalog DB│ │  Cart DB │ │Orders DB │        │  │
│  │       │       │ (MySQL)  │ │(DynamoDB)│ │ (MySQL)  │        │  │
│  │       │       └──────────┘ └──────────┘ └──────────┘        │  │
│  │       │                         │                            │  │
│  │       │                    ┌────▼─────┐                      │  │
│  │       └───────────────────►│ Checkout │                      │  │
│  │                            │ Service  │                      │  │
│  │                            └──────────┘                      │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Namespace: istio-sample (Bookinfo)          [mTLS: STRICT]   │  │
│  │                                                               │  │
│  │  Istio IngressGateway (:80 LB)                                │  │
│  │       │                                                       │  │
│  │       ▼                                                       │  │
│  │  ┌─────────────┐                                              │  │
│  │  │ productpage │ (v1)   :9080                                 │  │
│  │  └──┬───┬───┬──┘                                              │  │
│  │     │   │   │                                                 │  │
│  │     ▼   │   ▼                                                 │  │
│  │  ┌──────┐ │ ┌─────────┐   Weighted Routing:                   │  │
│  │  │details│ │ │ reviews │   v1=80%, v2=10%, v3=10%             │  │
│  │  │ (v1) │ │ ├─────────┤                                       │  │
│  │  └──────┘ │ │ v1 (no ★)│                                      │  │
│  │           │ │ v2 (★★★ black)│                                  │  │
│  │           │ │ v3 (★★★ red)  │                                  │  │
│  │           │ └─────┬───┘                                       │  │
│  │           │       ▼                                           │  │
│  │           │  ┌─────────┐                                      │  │
│  │           └─►│ ratings │ (v1)   :9080                         │  │
│  │              └─────────┘                                      │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Namespace: istio-system                                      │  │
│  │  ┌────────┐  ┌─────────────────┐  ┌─────────────────┐        │  │
│  │  │ istiod │  │ ingressgateway  │  │  egressgateway  │        │  │
│  │  │(Pilot) │  │   (Envoy LB)   │  │    (Envoy)      │        │  │
│  │  └────────┘  └─────────────────┘  └─────────────────┘        │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Namespace: opentelemetry                                     │  │
│  │  ┌────────────────────────────────────────────────────┐       │  │
│  │  │  ADOT Collector (DaemonSet)                         │       │  │
│  │  │  - Scrapes istio-proxy :15090 metrics              │       │  │
│  │  │  - Scrapes istiod http-monitoring metrics           │       │  │
│  │  │  - Remote Write → AMP (us-east-1)                  │       │  │
│  │  │  Image: aws-otel-collector:v0.40.0                 │       │  │
│  │  │  IRSA: adot-collector-istio-role                   │       │  │
│  │  └────────────────────────────────────────────────────┘       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Namespace: amazon-cloudwatch                                 │  │
│  │  ┌────────────────────────────────────────────────────┐       │  │
│  │  │  CloudWatch Container Insights (EKS Addon)          │       │  │
│  │  │  - Node/Pod/Container metrics                      │       │  │
│  │  │  - Performance monitoring                          │       │  │
│  │  └────────────────────────────────────────────────────┘       │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Workload Details

### 4.1 Retail Store Sample App (default namespace)

AWS 공식 [retail-store-sample-app](https://github.com/aws-containers/retail-store-sample-app) 마이크로서비스.
Module 5/6에서 K8s 진단 및 인시던트 분석의 대상 워크로드.

| Service | Role | Database | Port |
|---------|------|----------|------|
| UI | Web Frontend (Next.js) | - | 80 (LoadBalancer) |
| Catalog | Product catalog | MySQL (in-cluster) | Internal |
| Cart | Shopping cart | DynamoDB (in-cluster) | Internal |
| Orders | Order processing | MySQL (in-cluster) | Internal |
| Checkout | Payment processing | - | Internal |

### 4.2 Istio Bookinfo App (istio-sample namespace)

Istio 공식 [Bookinfo](https://istio.io/latest/docs/examples/bookinfo/) 샘플 앱.
Module 7에서 서비스 메시 진단의 대상 워크로드.

| Service | Versions | Port | Resource Requests | Resource Limits |
|---------|----------|------|-------------------|-----------------|
| productpage | v1 | 9080 | 50m CPU, 64Mi | 200m CPU, 128Mi |
| details | v1 | 9080 | 50m CPU, 64Mi | 200m CPU, 128Mi |
| reviews | v1, v2, v3 | 9080 | 50m CPU, 128Mi | 200m CPU, 256Mi |
| ratings | v1 | 9080 | 50m CPU, 64Mi | 200m CPU, 128Mi |

**Total Pods**: 6 (productpage-v1, details-v1, reviews-v1/v2/v3, ratings-v1)

---

## 5. Istio Service Mesh Configuration

### 5.1 Installation

```
Istio Version: 1.24.2
Profile: demo (istiod + ingressgateway + egressgateway)
Sidecar Injection:
  - default namespace:      enabled (retail-store → mesh observability)
  - istio-sample namespace: enabled (Bookinfo → full mesh features)
```

### 5.2 Traffic Management

```
                     Istio IngressGateway
                            │
                            ▼
                    ┌───────────────┐
                    │  Gateway       │   hosts: "*", port: 80
                    │  istio-sample  │
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │ VirtualService │   /productpage, /static,
                    │ (ingress)      │   /login, /logout, /api/v1
                    └───────┬───────┘
                            │
                            ▼
                      productpage:9080
                       │        │
              ┌────────┘        └────────┐
              ▼                          ▼
         details:9080              reviews:9080
         (v1: 100%)           ┌──────┼──────┐
                              ▼      ▼      ▼
                          v1:80%  v2:10%  v3:10%
                                         │
                                         ▼
                                   ratings:9080
                                   (v1: 100%)
```

### 5.3 DestinationRules (Connection Pools)

| Service | maxConnections (TCP) | http1MaxPendingRequests | http2MaxRequests |
|---------|---------------------|------------------------|-----------------|
| productpage | 100 | 100 | 100 |
| reviews | 100 | 100 | - |
| ratings | 100 | - | - |
| details | (default) | - | - |

### 5.4 Security

```
PeerAuthentication:
  Namespace: istio-sample
  Mode: STRICT (mTLS enforced for all service-to-service traffic)
```

### 5.5 Fault Injection Scenarios

Module 7 워크숍에서 AI Agent의 진단 능력을 테스트하기 위한 장애 시나리오.

| Scenario | Target | Type | Configuration |
|----------|--------|------|---------------|
| Delay Injection | reviews-v2 | Latency | 7s fixed delay (100%, header: `end-user: jason`) |
| Abort Injection | ratings-v1 | HTTP Error | 503 Service Unavailable (50%) |
| Circuit Breaker | reviews | Outlier Detection | 3 consecutive 5xx → 30s ejection, max 50% |

**Circuit Breaker Detail:**
```yaml
outlierDetection:
  consecutive5xxErrors: 3    # 3연속 5xx 에러 시
  interval: 10s              # 10초 간격으로 체크
  baseEjectionTime: 30s      # 30초간 제외
  maxEjectionPercent: 50     # 최대 50% 엔드포인트 제외
connectionPool:
  tcp.maxConnections: 10
  http.http1MaxPendingRequests: 5
  http.http2MaxRequests: 10
  http.maxRequestsPerConnection: 5
```

---

## 6. Observability Stack

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Observability Architecture                     │
│                                                                      │
│  ┌─────────────── EKS Cluster (us-west-2) ───────────────────────┐  │
│  │                                                                │  │
│  │  ┌──────────────┐   scrape     ┌────────────────────────┐     │  │
│  │  │ istio-proxy  │ ──────────── │  ADOT Collector        │     │  │
│  │  │ (sidecars)   │  :15090      │  (DaemonSet)           │     │  │
│  │  │              │              │  opentelemetry ns       │     │  │
│  │  └──────────────┘              └───────────┬────────────┘     │  │
│  │                                            │                  │  │
│  │  ┌──────────────┐   scrape                 │                  │  │
│  │  │   istiod     │ ──────────── ┘            │                  │  │
│  │  │              │  http-monitoring          │                  │  │
│  │  └──────────────┘                          │                  │  │
│  │                                            │ Remote Write     │  │
│  │  ┌──────────────────────────┐              │ (SigV4 Auth)    │  │
│  │  │ CloudWatch Container     │              │                  │  │
│  │  │ Insights (EKS Addon)     │              │                  │  │
│  │  └──────────┬───────────────┘              │                  │  │
│  └─────────────┼──────────────────────────────┼──────────────────┘  │
│                │                              │                      │
│                ▼                              ▼                      │
│  ┌─────────────────────┐     ┌──────────────────────────────┐       │
│  │  CloudWatch          │     │  Amazon Managed Prometheus    │       │
│  │  (us-west-2)         │     │  (us-east-1)                 │       │
│  │                      │     │  Workspace: istio-metrics    │       │
│  │  - Container metrics │     │                              │       │
│  │  - Control plane logs│     │  Istio Metrics:              │       │
│  │  - Pod/Node metrics  │     │  - istio_requests_total      │       │
│  │                      │     │  - istio_request_duration    │       │
│  └──────────┬───────────┘     │  - istio_tcp_connections     │       │
│             │                 │  - pilot_* (control plane)   │       │
│             │                 └──────────────┬───────────────┘       │
│             │                                │                      │
│             ▼                                ▼                      │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │           AI Agent Diagnostic Access                      │       │
│  │                                                          │       │
│  │  Module 5: K8s Agent → EKS MCP Server                    │       │
│  │    └→ get_cloudwatch_logs, get_cloudwatch_metrics         │       │
│  │                                                          │       │
│  │  Module 6: Incident Agent → Lambda MCP Tools              │       │
│  │    └→ CloudWatch Alarm → SNS → Auto-trigger               │       │
│  │                                                          │       │
│  │  Module 7: Istio Agent → Lambda (Prometheus Query)        │       │
│  │    └→ PromQL via AMP API                                 │       │
│  └──────────────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────┘
```

### Control Plane Logging

CloudWatch Logs에 전송되는 EKS 컨트롤 플레인 로그:

| Log Type | Description |
|----------|-------------|
| `api` | API Server 요청/응답 로그 |
| `audit` | K8s Audit 로그 (누가/무엇을/언제) |
| `authenticator` | IAM 인증 로그 |
| `controllerManager` | 컨트롤러 매니저 동작 로그 |
| `scheduler` | 스케줄러 결정 로그 |

### Metrics Pipeline

| Source | Collector | Destination | Metrics |
|--------|-----------|-------------|---------|
| istio-proxy sidecars | ADOT DaemonSet | AMP (us-east-1) | Envoy L7 metrics |
| istiod | ADOT DaemonSet | AMP (us-east-1) | Pilot control plane metrics |
| Nodes/Pods/Containers | Container Insights Addon | CloudWatch (us-west-2) | CPU, Memory, Network, Disk |

---

## 7. IAM & Security

### 7.1 OIDC & IRSA

```
EKS OIDC Provider
    │
    ├── ServiceAccount: adot-collector (opentelemetry ns)
    │   └── IAM Role: adot-collector-istio-role
    │       └── Policy: AmazonPrometheusRemoteWriteAccess
    │
    └── (Additional IRSA bindings per workload as needed)
```

### 7.2 Network Security

```
┌─────────────────────────────┐
│  Inbound (Public Subnet)     │
│  - UI LoadBalancer :80       │
│  - Istio IngressGateway :80  │
│  - Worker Nodes (Public IP)  │
├─────────────────────────────┤
│  Internal (Cluster)          │
│  - Service-to-Service: mTLS  │
│  - Pod-to-Pod: CNI (VPC)     │
│  - Security Groups로 접근 제어│
├─────────────────────────────┤
│  Outbound (Internet GW)     │
│  - ECR image pull            │
│  - AMP remote write          │
│  - CloudWatch API            │
│  - STS / SSM API calls       │
└─────────────────────────────┘
```

> **Note:** 현재 구성에서는 노드가 Public Subnet에 있어 Internet Gateway를 통해
> 직접 outbound 통신합니다. `privateNetworking: true` 설정 시 NAT Gateway 경유로 변경됩니다.

---

## 8. AI Agent Integration Points

이 EKS 클러스터는 3개의 AI Agent 모듈이 진단 대상으로 접근한다.

```
┌─────────────────────────────────────────────────────────────────┐
│                    AgentCore Platform (us-east-1)                │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Module 5        │  │  Module 6        │  │  Module 7        │ │
│  │  K8s Diagnostics │  │  Incident Agent  │  │  Istio Agent     │ │
│  │  Agent           │  │                  │  │                  │ │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬────────┘ │
│           │                     │                      │         │
│  ┌────────▼─────────┐          │           ┌──────────▼────────┐ │
│  │  MCP Gateway      │          │           │  MCP Gateway      │ │
│  │  (mcpServer)      │          │           │  (mcpServer +     │ │
│  │                   │          │           │   Lambda targets) │ │
│  └────────┬──────────┘          │           └──┬──────────┬────┘ │
│           │                     │              │          │      │
│  ┌────────▼──────────┐  ┌──────▼──────────┐   │   ┌──────▼────┐ │
│  │  EKS MCP Server   │  │  Lambda MCP     │   │   │ Lambda    │ │
│  │  Runtime           │  │  Tools (x6)     │   │   │ Prometheus│ │
│  └────────┬──────────┘  └──────┬──────────┘   │   │ Query     │ │
└───────────┼─────────────────────┼──────────────┼───┴─────┬────┘─┘
            │                     │              │         │
            ▼                     ▼              ▼         ▼
┌───────────────────────────────────────────────────────────────────┐
│                   netaiops-eks-cluster (us-west-2)                 │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐   │
│  │  EKS API │  │CloudWatch│  │  K8s     │  │  AMP           │   │
│  │ (kubectl)│  │  Logs &  │  │ Events & │  │ (PromQL)       │   │
│  │          │  │  Metrics │  │  Pods    │  │                │   │
│  └──────────┘  └──────────┘  └──────────┘  └────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

### Module별 접근 방식

| Module | Agent | Access Path | Target Data |
|--------|-------|-------------|-------------|
| 5 | K8s Diagnostics | EKS MCP Server → EKS API | Pods, Deployments, Events, Logs, CloudWatch Metrics |
| 6 | Incident Auto-Analysis | Lambda MCP Tools → CloudWatch/EKS API | Alarms, Logs, Metrics, Pod status |
| 7 | Istio Diagnostics | EKS MCP Server + Lambda → AMP/EKS API | Istio metrics (PromQL), K8s resources, Envoy config |

---

## 9. Deployment Workflow

### Phase 1: Cluster Creation

```
eksctl create cluster -f cluster-config.yaml
    │
    ├── 1. VPC 생성 (2-AZ, Public/Private Subnets, NAT GW)
    ├── 2. EKS Control Plane 프로비저닝
    ├── 3. Managed Node Group 생성 (m5.large x 2)
    ├── 4. IAM OIDC Provider 설정
    ├── 5. CloudWatch Container Insights Addon 설치
    └── 6. Control Plane Logging 활성화
```

### Phase 2: Workload Deployment (Module 5/6)

```
deploy-eks-workload.sh deploy-app
    │
    ├── 1. retail-store-sample-app manifest 적용
    ├── 2. 5개 Deployment Ready 대기
    └── 3. UI Service LoadBalancer URL 확인
```

### Phase 3: Istio Setup (Module 7)

```
setup-istio.sh
    │
    ├── 1. istioctl 다운로드 (v1.24.2)
    ├── 2. Istio demo profile 설치
    ├── 3. default 네임스페이스 sidecar injection 활성화
    ├── 4. 설치 검증
    └── 5. Istio 버전 SSM 저장

setup-amp.sh
    │
    ├── 1. AMP Workspace 생성 (istio-metrics)
    ├── 2. IRSA 설정 (ADOT → AMP Remote Write)
    ├── 3. ADOT Collector DaemonSet 배포
    ├── 4. 검증
    └── 5. AMP 엔드포인트 SSM 저장

setup-sample-app.sh
    │
    ├── Part A: retail-store sidecar injection
    │   ├── 1. default ns에 istio-injection=enabled
    │   ├── 2. 기존 Pod rollout restart
    │   └── 3. Sidecar 주입 확인
    │
    └── Part B: Bookinfo 배포
        ├── 1. istio-sample ns 생성 + injection 활성화
        ├── 2. Bookinfo manifest 적용
        ├── 3. Gateway, VirtualService, DestinationRule, PeerAuth 적용
        ├── 4. IngressGateway 엔드포인트 확인
        └── 5. 초기 트래픽 생성 (100 requests)
```

---

## 10. Cost Estimate

| Resource | Unit Cost | Quantity | Hourly Cost |
|----------|-----------|----------|-------------|
| EKS Control Plane | $0.10/hr | 1 | $0.10 |
| m5.large Nodes | $0.096/hr | 2~3 | $0.192~$0.288 |
| NAT Gateway | $0.045/hr | 1 | $0.045 |
| ELB (UI + Istio) | $0.025/hr | 2 | $0.050 |
| AMP (ingestion) | $0.03/10K samples | variable | ~$0.01 |
| **Total** | | | **~$0.40~$0.50/hr** |

---

## 11. Cross-Region Architecture Summary

```
┌─────────────── us-east-1 ──────────────────────────────────────┐
│                                                                 │
│  AgentCore Runtimes    MCP Gateway    AMP Workspace             │
│  ┌──────────────┐     ┌───────────┐  ┌─────────────────┐       │
│  │ K8s Agent     │────►│           │  │ istio-metrics   │       │
│  │ Incident Agent│────►│  Gateway  │  │ (Prometheus)    │       │
│  │ Istio Agent   │────►│           │  │                 │       │
│  └──────────────┘     └─────┬─────┘  └────────▲────────┘       │
│                             │                  │                │
│  ┌──────────────┐           │                  │                │
│  │ EKS MCP      │◄──────────┘                  │                │
│  │ Server       │                              │                │
│  └──────┬───────┘                              │                │
│         │                                      │                │
└─────────┼──────────────────────────────────────┼────────────────┘
          │ EKS API (HTTPS)                      │ Remote Write
          │                                      │ (SigV4)
┌─────────▼──────────── us-west-2 ───────────────┼────────────────┐
│                                                │                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            netaiops-eks-cluster                           │   │
│  │                                                          │   │
│  │  [default]        [istio-sample]     [opentelemetry]     │   │
│  │  retail-store     Bookinfo           ADOT Collector ─────┼───┘
│  │  (5 services)     (6 pods)           (DaemonSet)         │
│  │                                                          │   │
│  │  [istio-system]   [amazon-cloudwatch]                    │   │
│  │  Istio Control    Container Insights ──────► CloudWatch  │   │
│  │  Plane                                      (us-west-2)  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 12. Key SSM Parameters

EKS 클러스터와 관련된 SSM Parameter Store 키 (us-east-1):

| Parameter | Description |
|-----------|-------------|
| `/a2a/app/k8s/agentcore/gateway_url` | MCP Gateway 엔드포인트 |
| `/a2a/app/k8s/agentcore/memory_id` | AgentCore Memory ID |
| `/a2a/app/k8s/agentcore/user_id` | Agent 사용자 ID |
| `/app/istio/version` | Istio 설치 버전 |
| `/app/istio/agentcore/amp_workspace_id` | AMP Workspace ID |
| `/app/istio/agentcore/amp_endpoint` | AMP Remote Write 엔드포인트 |
| `/app/istio/agentcore/amp_query_endpoint` | AMP PromQL 쿼리 엔드포인트 |
