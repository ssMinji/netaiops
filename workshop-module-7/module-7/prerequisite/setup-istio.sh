#!/bin/bash
# =============================================================================
# Istio Service Mesh Installation for EKS (Module 7)
# Istio 서비스 메시 설치 (모듈 7)
# =============================================================================
set -e

PROFILE="${AWS_PROFILE:-netaiops-deploy}"
ISTIO_VERSION="${ISTIO_VERSION:-1.24.2}"
NAMESPACE="default"

echo "==========================================="
echo " Istio Service Mesh Installation"
echo " Version: ${ISTIO_VERSION}"
echo "==========================================="

# -----------------------------------------------
# 1. Download istioctl
# -----------------------------------------------
echo ""
echo "[1/5] Downloading istioctl v${ISTIO_VERSION}..."

if command -v istioctl &>/dev/null; then
    CURRENT_VERSION=$(istioctl version --remote=false 2>/dev/null | head -1 || echo "unknown")
    echo "  istioctl already installed: ${CURRENT_VERSION}"
else
    curl -L https://istio.io/downloadIstio | ISTIO_VERSION=${ISTIO_VERSION} TARGET_ARCH=$(uname -m | sed 's/aarch64/arm64/;s/x86_64/amd64/') sh -
    sudo cp istio-${ISTIO_VERSION}/bin/istioctl /usr/local/bin/
    rm -rf istio-${ISTIO_VERSION}
    echo "  istioctl installed successfully"
fi

istioctl version --remote=false

# -----------------------------------------------
# 2. Install Istio with demo profile
# -----------------------------------------------
echo ""
echo "[2/5] Installing Istio with demo profile..."
istioctl install --set profile=demo -y

echo "  Waiting for Istio pods to be ready..."
kubectl wait --for=condition=ready pod -l app=istiod -n istio-system --timeout=120s
kubectl wait --for=condition=ready pod -l app=istio-ingressgateway -n istio-system --timeout=120s

# -----------------------------------------------
# 3. Enable sidecar injection for default namespace
# -----------------------------------------------
echo ""
echo "[3/5] Enabling sidecar injection for namespace: ${NAMESPACE}"
kubectl label namespace ${NAMESPACE} istio-injection=enabled --overwrite

# -----------------------------------------------
# 4. Verify installation
# -----------------------------------------------
echo ""
echo "[4/5] Verifying Istio installation..."
istioctl verify-install

echo ""
echo "Istio system pods:"
kubectl get pods -n istio-system

# -----------------------------------------------
# 5. Store version in SSM
# -----------------------------------------------
echo ""
echo "[5/5] Storing Istio version in SSM..."
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

aws ssm put-parameter \
    --name "/app/istio/version" \
    --value "${ISTIO_VERSION}" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE} 2>/dev/null || true

echo ""
echo "==========================================="
echo " Istio Installation Complete!"
echo "==========================================="
echo ""
echo "  Version:    ${ISTIO_VERSION}"
echo "  Namespace:  istio-system"
echo "  Injection:  ${NAMESPACE} (enabled)"
echo ""
echo "Next Steps:"
echo "  1. Setup AMP + ADOT: ./setup-amp.sh"
echo "  2. Deploy Bookinfo:  ./setup-sample-app.sh"
