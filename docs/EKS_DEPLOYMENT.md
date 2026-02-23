# NetAIOps EKS Sample Workload - Deployment Summary

## Overview

AWS [retail-store-sample-app](https://github.com/aws-containers/retail-store-sample-app) v1.4.0을 EKS 클러스터에 배포하여 Module 5 K8s Diagnostics Agent의 대상 워크로드로 사용합니다.

---

## Cluster Information

| 항목 | 값 |
|------|-----|
| Cluster Name | `netaiops-eks-cluster` |
| Region | `us-west-2` (Oregon) |
| AWS Profile | `netaiops-deploy` |
| AWS Account | `175678592674` |
| Kubernetes Version | `1.31` (Platform: eks.50) |
| API Endpoint | `https://3EB6B3BFFA50A489CA7A8D500EB81C5D.gr7.us-west-2.eks.amazonaws.com` |
| VPC | `vpc-0503f5f42a68c097e` (192.168.0.0/16) |
| API Public Access | Enabled |

## Node Group

| 항목 | 값 |
|------|-----|
| Node Group Name | `ng-default` |
| Instance Type | `m5.large` (2 vCPU, 8 GiB) |
| Desired / Min / Max | 2 / 2 / 3 |
| Volume Size | 30 GiB |
| OS | Amazon Linux 2023 |

### Nodes

| Node | AZ | Status |
|------|----|--------|
| `ip-192-168-21-60.us-west-2.compute.internal` | us-west-2c | Ready |
| `ip-192-168-86-155.us-west-2.compute.internal` | us-west-2d | Ready |

## Network

### Subnets (6개 - 3 Public, 3 Private)

| Subnet ID | Type |
|-----------|------|
| `subnet-054a62dadbf0145d5` | Public (us-west-2b) |
| `subnet-0fb9ec981906b1549` | Public (us-west-2c) |
| `subnet-0d296d3899cf92367` | Public (us-west-2d) |
| `subnet-06b79fe3062ac507e` | Private (us-west-2b) |
| `subnet-07417b74e2a30c4b9` | Private (us-west-2c) |
| `subnet-0ac0cfa12c95874a6` | Private (us-west-2d) |

NAT Gateway: Single (비용 최적화)

### Security Groups

| Security Group | ID |
|---------------|-----|
| Control Plane SG | `sg-03543cf55aacc1206` |
| Cluster SG | `sg-093d912730a436490` |
| Shared Node SG | `sg-06c59c90c514e1db7` |

---

## EKS Addons

| Addon | Version | Status | 용도 |
|-------|---------|--------|------|
| vpc-cni | v1.20.4-eksbuild.2 | ACTIVE | Pod 네트워킹 (ENI) |
| coredns | v1.11.3-eksbuild.1 | ACTIVE | 클러스터 내부 DNS |
| kube-proxy | v1.31.10-eksbuild.12 | ACTIVE | Service 프록시 |
| metrics-server | v0.8.1-eksbuild.1 | ACTIVE | 리소스 메트릭 수집 |
| amazon-cloudwatch-observability | v4.10.0-eksbuild.1 | ACTIVE | Container Insights |

---

## Application: retail-store-sample-app v1.4.0

### Architecture

```
                          Internet
                             |
                      [Classic ELB]
                        (port 80)
                             |
                         +---+---+
                         |  UI   |  (Java)
                         +---+---+
                             |
              +--------------+--------------+
              |              |              |
         +----+----+   +----+----+   +-----+-----+
         | Catalog |   |  Cart   |   |  Checkout  |
         |  (Go)   |   | (Java)  |   |  (Node.js) |
         +----+----+   +----+----+   +-----+------+
              |              |              |
         +----+----+   +----+----+   +-----+-----+
         |  MySQL  |   |DynamoDB |   |   Redis    |
         |  (8.0)  |   | (Local) |   | (6.0-alp.) |
         +---------+   +---------+   +-----------+
                                          |
                                    +-----+-----+
                                    |  Orders   |
                                    |  (Java)   |
                                    +-----+-----+
                                          |
                                   +------+------+
                                   |      |      |
                              +----+--+ +-+------+-+
                              |Postgre| | RabbitMQ |
                              |SQL 16 | |   3-mgmt |
                              +-------+ +----------+
```

### Pods (10개)

| Pod | Image | Status |
|-----|-------|--------|
| `ui` | `retail-store-sample-ui:1.4.0` | Running |
| `catalog` | `retail-store-sample-catalog:1.4.0` | Running |
| `catalog-mysql` | `mysql:8.0` | Running |
| `carts` | `retail-store-sample-cart:1.4.0` | Running |
| `carts-dynamodb` | `aws-dynamodb-local:1.25.1` | Running |
| `checkout` | `retail-store-sample-checkout:1.4.0` | Running |
| `checkout-redis` | `redis:6.0-alpine` | Running |
| `orders` | `retail-store-sample-orders:1.4.0` | Running |
| `orders-postgresql` | `postgres:16.1` | Running |
| `orders-rabbitmq` | `rabbitmq:3-management` | Running |

### Services (10개)

| Service | Type | Port | External Access |
|---------|------|------|----------------|
| `ui` | **LoadBalancer** | 80 | `a434dd143bac0442c90be2527e8ca477-1206726356.us-west-2.elb.amazonaws.com` |
| `catalog` | ClusterIP | 80 | Internal only |
| `catalog-mysql` | ClusterIP | 3306 | Internal only |
| `carts` | ClusterIP | 80 | Internal only |
| `carts-dynamodb` | ClusterIP | 8000 | Internal only |
| `checkout` | ClusterIP | 80 | Internal only |
| `checkout-redis` | ClusterIP | 6379 | Internal only |
| `orders` | ClusterIP | 80 | Internal only |
| `orders-postgresql` | ClusterIP | 5432 | Internal only |
| `orders-rabbitmq` | ClusterIP | 5672, 15672 | Internal only |

### UI Access

```
http://a434dd143bac0442c90be2527e8ca477-1206726356.us-west-2.elb.amazonaws.com
```

---

## Security

### Container Security Context

| 컨테이너 | runAsNonRoot | readOnlyRootFS | drop ALL caps | 비고 |
|-----------|:-----------:|:--------------:|:------------:|------|
| ui | O | O | O | NET_BIND_SERVICE 추가 |
| catalog | O | O | O | |
| carts | O | O | O | |
| checkout | O | O | O | |
| orders | O | O | O | |
| catalog-mysql | - | - | - | DB 컨테이너 (기본값) |
| carts-dynamodb | - | - | - | DB 컨테이너 (기본값) |
| checkout-redis | - | - | - | DB 컨테이너 (기본값) |
| orders-postgresql | - | - | - | DB 컨테이너 (기본값) |
| orders-rabbitmq | - | - | - | DB 컨테이너 (기본값) |

### Security Notes

- UI 서비스만 외부 노출 (Classic ELB, internet-facing, HTTP 80)
- 모든 DB/캐시 서비스는 ClusterIP으로 외부 접근 불가
- NetworkPolicy 미적용 (pod 간 트래픽 제한 없음)
- TLS/HTTPS 미적용 (HTTP only)
- IAM OIDC Provider 연결 완료 (IRSA 사용 가능)
- EKS API Endpoint: Public Access만 활성화

---

## CloudFormation Stacks

| Stack Name | Status |
|------------|--------|
| `eksctl-netaiops-eks-cluster-cluster` | CREATE_COMPLETE |
| `eksctl-netaiops-eks-cluster-nodegroup-ng-default` | CREATE_COMPLETE |

---

## Observability

### Container Insights (CloudWatch)

CloudWatch Container Insights가 활성화되어 pod/node/cluster 메트릭과 로그를 수집합니다.

| 구성 요소 | 상태 | 버전 |
|-----------|------|------|
| CloudWatch Agent (DaemonSet) | Running (2/2) | v1.300064.0b1337 |
| Fluent Bit (DaemonSet) | Running (2/2) | v4.2 (aws-for-fluent-bit 3.2.0) |
| amazon-cloudwatch-observability addon | ACTIVE | v4.10.0-eksbuild.1 |
| Metrics Server addon | ACTIVE | v0.8.1-eksbuild.1 |

**CloudWatch Log Groups:**

| Log Group | 내용 |
|-----------|------|
| `/aws/containerinsights/netaiops-eks-cluster/application` | 앱 컨테이너 로그 |
| `/aws/containerinsights/netaiops-eks-cluster/dataplane` | aws-node, kube-proxy 로그 |
| `/aws/containerinsights/netaiops-eks-cluster/host` | 호스트 시스템 로그 |
| `/aws/containerinsights/netaiops-eks-cluster/performance` | 성능 메트릭 (EMF) |
| `/aws/eks/netaiops-eks-cluster/cluster` | EKS 컨트롤 플레인 로그 |

**수집 메트릭 (ContainerInsights namespace):**
- `pod_cpu_utilization`, `pod_memory_request`, `pod_memory_limit`
- `pod_interface_network_tx_dropped` 등

### OpenSearch

로그 검색 및 분석을 위한 OpenSearch 도메인이 구성되어 있습니다.

| 항목 | 값 |
|------|-----|
| Domain Name | `netaiops-logs` |
| Engine Version | OpenSearch 2.13 |
| Instance Type | `t3.small.search` x 1 |
| Storage | 20 GiB (gp3) |
| Endpoint | `https://search-netaiops-logs-2chawa5gyptw2gtikmgkb4odcq.us-west-2.es.amazonaws.com` |
| Fine-Grained Access | Enabled (admin/NetAIOps2026!) |
| Encryption | Node-to-node + At-rest + HTTPS enforced (TLS 1.2+) |

**Fluent Bit → OpenSearch 파이프라인:**
- Fluent Bit이 앱 컨테이너 로그를 CloudWatch와 OpenSearch **동시에** 전송
- OpenSearch 인덱스: `eks-app-logs`
- Kubernetes 메타데이터 포함 (pod_name, namespace, cluster, workload, host 등)

**OpenSearch 접속:**
```bash
# 인덱스 목록
curl -s "https://search-netaiops-logs-2chawa5gyptw2gtikmgkb4odcq.us-west-2.es.amazonaws.com/_cat/indices?v" \
  -H "Authorization: Basic $(echo -n 'admin:NetAIOps2026!' | base64)"

# 로그 검색
curl -s "https://search-netaiops-logs-2chawa5gyptw2gtikmgkb4odcq.us-west-2.es.amazonaws.com/eks-app-logs/_search?pretty&size=5" \
  -H "Authorization: Basic $(echo -n 'admin:NetAIOps2026!' | base64)"
```

### IAM Permissions (Node Role)

노드 IAM Role: `eksctl-netaiops-eks-cluster-nodegr-NodeInstanceRole-udVWgLHmPt6u`

| Policy | 용도 |
|--------|------|
| AmazonEKSWorkerNodePolicy | EKS 노드 기본 |
| AmazonEKS_CNI_Policy | VPC CNI 네트워킹 |
| AmazonEC2ContainerRegistryPullOnly | ECR 이미지 풀 |
| AmazonSSMManagedInstanceCore | SSM 접근 |
| CloudWatchAgentServerPolicy | CloudWatch Agent 메트릭/로그 |
| CloudWatchFullAccessV2 | Container Insights 전체 |
| AmazonOpenSearchServiceFullAccess | OpenSearch 로그 전송 |

---

## Module 5/6 Integration

이 EKS 클러스터는 Module 5 K8s Diagnostics Agent와 Module 6 Incident Analysis Agent의 대상 워크로드입니다.

**Module 5 (K8s Diagnostics):**
- **Container Insights** → CloudWatch에서 pod/node/cluster 메트릭 조회
- **Metrics Server** → `kubectl top` 리소스 사용량 확인
- **EKS MCP Server** 연동 가능 (`workshop-module-5/module-5/agentcore-k8s-agent/prerequisite/eks-mcp-server/`)

**Module 6 (Incident Analysis):**
- **OpenSearch** → `eks-app-logs` 인덱스에서 로그 검색, 이상 탐지
- **Container Insights** → CloudWatch Container Insights에서 Pod 리소스 메트릭 확인

---

## Management Commands

```bash
cd workshop-module-5/eks-sample-workload

# 상태 확인
./deploy-eks-workload.sh status

# 앱만 삭제
./deploy-eks-workload.sh delete-app

# 앱 재배포
./deploy-eks-workload.sh deploy-app

# 전체 삭제 (앱 + 클러스터)
./deploy-eks-workload.sh delete-all
```

### kubectl 직접 사용

```bash
# kubeconfig 설정
aws eks update-kubeconfig --name netaiops-eks-cluster --region us-west-2 --profile netaiops-deploy

# Pod 상태
kubectl get pods -n default

# 서비스 확인
kubectl get svc -n default

# 리소스 사용량
kubectl top pods -n default
kubectl top nodes

# 로그 확인
kubectl logs -f deployment/ui -n default
```

---

## Cost Estimate

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| EKS Control Plane | ~$73 |
| EC2 m5.large x 2 | ~$140 |
| NAT Gateway | ~$32 + data transfer |
| Classic ELB | ~$18 + data transfer |
| CloudWatch (Container Insights) | ~$10-30 (usage dependent) |
| OpenSearch (t3.small.search) | ~$25 + storage |
| EBS (30GB x 2) | ~$6 |
| **Total** | **~$305-330/month** |

> 사용하지 않을 때는 `./deploy-eks-workload.sh delete-all`로 삭제하여 비용을 절약하세요.
