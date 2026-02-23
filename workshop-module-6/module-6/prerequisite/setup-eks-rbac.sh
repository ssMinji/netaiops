#!/bin/bash

# =============================================================================
# EKS RBAC Setup for Chaos Lambda
# 카오스 Lambda용 EKS RBAC 설정
# =============================================================================
# Creates:
#   1. K8s ServiceAccount for chaos Lambda
#   2. ClusterRole with pod/deployment permissions
#   3. ClusterRoleBinding
#   4. Updates aws-auth ConfigMap to map Lambda role
#
# Prerequisites:
#   - kubectl configured for netaiops-eks-cluster
#   - deploy-incident-lambdas.sh must be run first (creates IAM role)
#
# Usage: ./setup-eks-rbac.sh
# =============================================================================

set -e

PROFILE="netaiops-deploy"
EKS_CLUSTER_NAME="netaiops-eks-cluster"
EKS_REGION="us-west-2"
LAMBDA_ROLE_NAME="incident-tools-lambda-role"
K8S_NAMESPACE="default"

echo "==========================================="
echo " EKS RBAC Setup for Chaos Lambda"
echo "==========================================="

# -----------------------------------------------
# 1. Get Account ID and Role ARN
# -----------------------------------------------
ACCOUNT_ID=$(aws sts get-caller-identity --profile ${PROFILE} --query Account --output text)
LAMBDA_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}"
echo "Account: $ACCOUNT_ID"
echo "Lambda Role: $LAMBDA_ROLE_ARN"
echo "Cluster: $EKS_CLUSTER_NAME (${EKS_REGION})"

# -----------------------------------------------
# 2. Update kubeconfig
# -----------------------------------------------
echo ""
echo "Updating kubeconfig..."
aws eks update-kubeconfig \
    --name ${EKS_CLUSTER_NAME} \
    --region ${EKS_REGION} \
    --profile ${PROFILE}

# -----------------------------------------------
# 3. Create ClusterRole for chaos operations
# -----------------------------------------------
echo ""
echo "Creating ClusterRole: chaos-lambda-role..."
cat <<'EOF' | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: chaos-lambda-role
rules:
  # Pod operations (for stress-ng pod creation/deletion)
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "create", "delete"]
  # Deployment operations (for scaling, image changes, resource limits)
  - apiGroups: ["apps"]
    resources: ["deployments", "deployments/scale"]
    verbs: ["get", "list", "patch", "update"]
  # ReplicaSet read (for deployment status)
  - apiGroups: ["apps"]
    resources: ["replicasets"]
    verbs: ["get", "list"]
EOF

# -----------------------------------------------
# 4. Create ClusterRoleBinding
# -----------------------------------------------
echo ""
echo "Creating ClusterRoleBinding: chaos-lambda-binding..."
cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: chaos-lambda-binding
subjects:
  - kind: Group
    name: chaos-lambda-group
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: chaos-lambda-role
  apiGroup: rbac.authorization.k8s.io
EOF

# -----------------------------------------------
# 5. Update aws-auth ConfigMap
# -----------------------------------------------
echo ""
echo "Updating aws-auth ConfigMap..."

# Check if the role mapping already exists
EXISTING_AUTH=$(kubectl get configmap aws-auth -n kube-system -o yaml 2>/dev/null || echo "")

if echo "$EXISTING_AUTH" | grep -q "$LAMBDA_ROLE_ARN"; then
    echo "Lambda role already mapped in aws-auth ConfigMap"
else
    echo "Adding Lambda role to aws-auth ConfigMap..."

    # Use eksctl if available, otherwise patch directly
    if command -v eksctl &> /dev/null; then
        eksctl create iamidentitymapping \
            --cluster ${EKS_CLUSTER_NAME} \
            --region ${EKS_REGION} \
            --arn ${LAMBDA_ROLE_ARN} \
            --group chaos-lambda-group \
            --username chaos-lambda \
            --profile ${PROFILE}
    else
        # Manual patch using kubectl
        # Get current mapRoles
        CURRENT_MAP_ROLES=$(kubectl get configmap aws-auth -n kube-system -o jsonpath='{.data.mapRoles}')

        # Append new role mapping
        NEW_ENTRY="
- rolearn: ${LAMBDA_ROLE_ARN}
  username: chaos-lambda
  groups:
    - chaos-lambda-group"

        UPDATED_MAP_ROLES="${CURRENT_MAP_ROLES}${NEW_ENTRY}"

        # Apply the update
        kubectl get configmap aws-auth -n kube-system -o yaml | \
            python3 -c "
import sys, yaml
data = yaml.safe_load(sys.stdin)
current = data['data'].get('mapRoles', '')
new_entry = '''
- rolearn: ${LAMBDA_ROLE_ARN}
  username: chaos-lambda
  groups:
    - chaos-lambda-group'''
data['data']['mapRoles'] = current + new_entry
print(yaml.dump(data, default_flow_style=False))
" | kubectl apply -f -
    fi

    echo "Lambda role mapped to chaos-lambda-group in aws-auth"
fi

# -----------------------------------------------
# 6. Verify
# -----------------------------------------------
echo ""
echo "Verifying RBAC setup..."
echo ""
echo "ClusterRole:"
kubectl get clusterrole chaos-lambda-role -o wide 2>/dev/null || echo "  NOT FOUND"
echo ""
echo "ClusterRoleBinding:"
kubectl get clusterrolebinding chaos-lambda-binding -o wide 2>/dev/null || echo "  NOT FOUND"
echo ""
echo "aws-auth ConfigMap (mapRoles):"
kubectl get configmap aws-auth -n kube-system -o jsonpath='{.data.mapRoles}' 2>/dev/null | head -30
echo ""

# -----------------------------------------------
# 7. Summary
# -----------------------------------------------
echo ""
echo "==========================================="
echo " EKS RBAC Setup Complete!"
echo "==========================================="
echo ""
echo "ClusterRole: chaos-lambda-role"
echo "  - Pods: get, list, create, delete"
echo "  - Deployments: get, list, patch, update"
echo "  - Deployments/scale: get, list, patch, update"
echo "  - ReplicaSets: get, list"
echo ""
echo "ClusterRoleBinding: chaos-lambda-binding"
echo "  - Group: chaos-lambda-group → chaos-lambda-role"
echo ""
echo "aws-auth mapping:"
echo "  - ${LAMBDA_ROLE_ARN} → chaos-lambda-group"
echo ""
echo "The Chaos Lambda can now manage pods and deployments"
echo "in the '${K8S_NAMESPACE}' namespace of ${EKS_CLUSTER_NAME}."
echo ""
