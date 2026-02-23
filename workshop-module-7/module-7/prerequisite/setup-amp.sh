#!/bin/bash
# =============================================================================
# Amazon Managed Prometheus (AMP) + ADOT Collector Setup (Module 7)
# AMP 워크스페이스 + ADOT 컬렉터 설정 (모듈 7)
# =============================================================================
set -e

PROFILE="${AWS_PROFILE:-netaiops-deploy}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
EKS_CLUSTER="${EKS_CLUSTER_NAME:-netaiops-eks-cluster}"
EKS_REGION="${EKS_CLUSTER_REGION:-us-west-2}"
AMP_WORKSPACE_ALIAS="istio-metrics"
ADOT_NAMESPACE="opentelemetry"

echo "==========================================="
echo " AMP + ADOT Collector Setup"
echo "==========================================="
echo "  EKS Cluster: ${EKS_CLUSTER} (${EKS_REGION})"
echo "  AMP Region:  ${REGION}"

# -----------------------------------------------
# 1. Create AMP workspace
# -----------------------------------------------
echo ""
echo "[1/6] Creating AMP workspace..."

EXISTING_WORKSPACE=$(aws amp list-workspaces \
    --alias "${AMP_WORKSPACE_ALIAS}" \
    --region ${REGION} \
    --profile ${PROFILE} \
    --query 'workspaces[0].workspaceId' \
    --output text 2>/dev/null || echo "None")

if [ "$EXISTING_WORKSPACE" != "None" ] && [ -n "$EXISTING_WORKSPACE" ]; then
    AMP_WORKSPACE_ID="$EXISTING_WORKSPACE"
    echo "  Using existing workspace: ${AMP_WORKSPACE_ID}"
else
    AMP_WORKSPACE_ID=$(aws amp create-workspace \
        --alias "${AMP_WORKSPACE_ALIAS}" \
        --region ${REGION} \
        --profile ${PROFILE} \
        --query 'workspaceId' \
        --output text)
    echo "  Created workspace: ${AMP_WORKSPACE_ID}"

    echo "  Waiting for workspace to be active..."
    aws amp wait workspace-active \
        --workspace-id ${AMP_WORKSPACE_ID} \
        --region ${REGION} \
        --profile ${PROFILE} 2>/dev/null || sleep 30
fi

AMP_ENDPOINT="https://aps-workspaces.${REGION}.amazonaws.com/workspaces/${AMP_WORKSPACE_ID}"
AMP_QUERY_ENDPOINT="${AMP_ENDPOINT}/api/v1"

echo "  Endpoint: ${AMP_ENDPOINT}"

# -----------------------------------------------
# 2. Create IRSA for ADOT Collector
# -----------------------------------------------
echo ""
echo "[2/6] Setting up IRSA for ADOT Collector..."

ACCOUNT_ID=$(aws sts get-caller-identity --profile ${PROFILE} --query Account --output text)
OIDC_PROVIDER=$(aws eks describe-cluster \
    --name ${EKS_CLUSTER} \
    --region ${EKS_REGION} \
    --profile ${PROFILE} \
    --query "cluster.identity.oidc.issuer" \
    --output text | sed 's|https://||')

ADOT_ROLE_NAME="adot-collector-istio-role"

# Create trust policy
cat > /tmp/adot-trust-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/${OIDC_PROVIDER}"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "${OIDC_PROVIDER}:aud": "sts.amazonaws.com",
                    "${OIDC_PROVIDER}:sub": "system:serviceaccount:${ADOT_NAMESPACE}:adot-collector"
                }
            }
        }
    ]
}
EOF

aws iam create-role \
    --role-name ${ADOT_ROLE_NAME} \
    --assume-role-policy-document file:///tmp/adot-trust-policy.json \
    --profile ${PROFILE} 2>/dev/null || echo "  Role already exists"

aws iam attach-role-policy \
    --role-name ${ADOT_ROLE_NAME} \
    --policy-arn arn:aws:iam::aws:policy/AmazonPrometheusRemoteWriteAccess \
    --profile ${PROFILE} 2>/dev/null || true

ADOT_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ADOT_ROLE_NAME}"
echo "  ADOT Role: ${ADOT_ROLE_ARN}"

# -----------------------------------------------
# 3. Deploy ADOT Collector as DaemonSet
# -----------------------------------------------
echo ""
echo "[3/6] Deploying ADOT Collector..."

kubectl create namespace ${ADOT_NAMESPACE} 2>/dev/null || true

# Create ADOT collector config (use $$ to escape $1 for ADOT confmap resolver)
cat > /tmp/otel-config.yaml << 'OTELCFG'
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: "istio-proxy"
          metrics_path: /stats/prometheus
          kubernetes_sd_configs:
            - role: pod
          relabel_configs:
            - source_labels: [__meta_kubernetes_pod_container_name]
              action: keep
              regex: istio-proxy
            - source_labels: [__meta_kubernetes_pod_ip]
              action: replace
              target_label: __address__
              replacement: "$$1:15090"
            - source_labels: [__meta_kubernetes_namespace]
              action: replace
              target_label: namespace
            - source_labels: [__meta_kubernetes_pod_name]
              action: replace
              target_label: pod
        - job_name: "istiod"
          kubernetes_sd_configs:
            - role: endpoints
              namespaces:
                names:
                  - istio-system
          relabel_configs:
            - source_labels: [__meta_kubernetes_service_name, __meta_kubernetes_endpoint_port_name]
              action: keep
              regex: istiod;http-monitoring
exporters:
  prometheusremotewrite:
    endpoint: "AMP_REMOTE_WRITE_PLACEHOLDER"
    auth:
      authenticator: sigv4auth
extensions:
  health_check:
    endpoint: 0.0.0.0:13133
  sigv4auth:
    region: "AMP_REGION_PLACEHOLDER"
    service: "aps"
service:
  extensions: [health_check, sigv4auth]
  pipelines:
    metrics:
      receivers: [prometheus]
      exporters: [prometheusremotewrite]
OTELCFG

# Replace placeholders with actual values
sed -i "s|AMP_REMOTE_WRITE_PLACEHOLDER|${AMP_ENDPOINT}/api/v1/remote_write|" /tmp/otel-config.yaml
sed -i "s|AMP_REGION_PLACEHOLDER|${REGION}|" /tmp/otel-config.yaml

kubectl delete configmap adot-istio-config -n ${ADOT_NAMESPACE} 2>/dev/null || true
kubectl create configmap adot-istio-config -n ${ADOT_NAMESPACE} --from-file=config.yaml=/tmp/otel-config.yaml

# Deploy ServiceAccount, RBAC, DaemonSet
cat << EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: adot-collector
  namespace: ${ADOT_NAMESPACE}
  annotations:
    eks.amazonaws.com/role-arn: ${ADOT_ROLE_ARN}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: adot-collector
rules:
  - apiGroups: [""]
    resources: [nodes, nodes/proxy, nodes/metrics, services, endpoints, pods]
    verbs: [get, list, watch]
  - apiGroups: ["extensions", "networking.k8s.io"]
    resources: [ingresses]
    verbs: [get, list, watch]
  - nonResourceURLs: ["/metrics", "/metrics/cadvisor"]
    verbs: [get]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: adot-collector
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: adot-collector
subjects:
  - kind: ServiceAccount
    name: adot-collector
    namespace: ${ADOT_NAMESPACE}
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: adot-collector
  namespace: ${ADOT_NAMESPACE}
spec:
  selector:
    matchLabels:
      app: adot-collector
  template:
    metadata:
      labels:
        app: adot-collector
    spec:
      serviceAccountName: adot-collector
      containers:
        - name: collector
          image: public.ecr.aws/aws-observability/aws-otel-collector:v0.40.0
          args: ["--config", "/conf/config.yaml"]
          ports:
            - containerPort: 13133
          livenessProbe:
            httpGet:
              path: /
              port: 13133
            initialDelaySeconds: 15
          readinessProbe:
            httpGet:
              path: /
              port: 13133
            initialDelaySeconds: 10
          volumeMounts:
            - name: config
              mountPath: /conf
      volumes:
        - name: config
          configMap:
            name: adot-istio-config
EOF

echo "  Waiting for ADOT Collector pods..."
kubectl rollout status daemonset/adot-collector -n ${ADOT_NAMESPACE} --timeout=120s 2>/dev/null || true
echo "  ADOT Collector deployed"

# -----------------------------------------------
# 4. Verify ADOT collector pods
# -----------------------------------------------
echo ""
echo "[4/6] Verifying ADOT Collector..."
kubectl get pods -n ${ADOT_NAMESPACE} -l app.kubernetes.io/name=opentelemetry-collector 2>/dev/null || \
    echo "  ADOT pods not yet ready (may need a few minutes)"

# -----------------------------------------------
# 5. Store parameters in SSM
# -----------------------------------------------
echo ""
echo "[5/6] Storing AMP parameters in SSM..."

aws ssm put-parameter \
    --name "/app/istio/agentcore/amp_workspace_id" \
    --value "${AMP_WORKSPACE_ID}" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}

aws ssm put-parameter \
    --name "/app/istio/agentcore/amp_endpoint" \
    --value "${AMP_ENDPOINT}" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}

aws ssm put-parameter \
    --name "/app/istio/agentcore/amp_query_endpoint" \
    --value "${AMP_QUERY_ENDPOINT}" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}

echo "  SSM parameters stored"

# -----------------------------------------------
# 6. Summary
# -----------------------------------------------
echo ""
echo "[6/6] Setup complete!"
echo ""
echo "==========================================="
echo " AMP + ADOT Setup Complete!"
echo "==========================================="
echo ""
echo "  AMP Workspace ID:  ${AMP_WORKSPACE_ID}"
echo "  AMP Endpoint:      ${AMP_ENDPOINT}"
echo "  AMP Query:         ${AMP_QUERY_ENDPOINT}"
echo "  ADOT Namespace:    ${ADOT_NAMESPACE}"
echo "  ADOT Role:         ${ADOT_ROLE_ARN}"
echo ""
echo "SSM Parameters:"
echo "  /app/istio/agentcore/amp_workspace_id"
echo "  /app/istio/agentcore/amp_endpoint"
echo "  /app/istio/agentcore/amp_query_endpoint"
echo ""
echo "Verify metrics:"
echo "  awscurl --service aps --region ${REGION} '${AMP_QUERY_ENDPOINT}/query?query=istio_requests_total'"
echo ""
echo "Next Steps:"
echo "  1. Deploy Bookinfo: ./setup-sample-app.sh"
