#!/bin/bash
# =============================================================================
# Istio Sample Workload Deployment (Module 7)
# Istio 샘플 워크로드 배포 - retail-store 사이드카 주입 + Istio 공식 샘플 앱
# =============================================================================
# 두 가지 워크로드를 배포합니다:
#   1) retail-store-sample-app (기존 EKS 워크로드) - 사이드카 주입으로 메시에 편입
#   2) istio-sample-app (Istio 공식 Bookinfo) - 트래픽 분할, fault injection 등 고급 데모
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLE_DIR="${SCRIPT_DIR}/../../sample-workload"

# retail-store namespace (Module 5/6에서 사용 중인 기존 네임스페이스)
RETAIL_NS="${RETAIL_NAMESPACE:-retail-store}"
# Istio 샘플 앱 네임스페이스
ISTIO_SAMPLE_NS="istio-sample"

echo "============================================================"
echo " Istio Sample Workload Deployment (Module 7)"
echo " - retail-store: sidecar injection on existing workload"
echo " - istio-sample: Istio official sample app (Bookinfo)"
echo "============================================================"

# =============================================================
# Part A: retail-store-sample-app 사이드카 주입
# =============================================================
echo ""
echo "============================================"
echo " Part A: retail-store Sidecar Injection"
echo "============================================"

# -----------------------------------------------
# A-1. retail-store 네임스페이스에 사이드카 주입 활성화
# -----------------------------------------------
echo ""
echo "[A-1] Enabling sidecar injection for ${RETAIL_NS} namespace..."

# 네임스페이스 존재 여부 확인
if kubectl get namespace ${RETAIL_NS} &>/dev/null; then
    INJECTION=$(kubectl get namespace ${RETAIL_NS} -o jsonpath='{.metadata.labels.istio-injection}' 2>/dev/null || echo "")
    if [ "$INJECTION" != "enabled" ]; then
        kubectl label namespace ${RETAIL_NS} istio-injection=enabled --overwrite
        echo "  Sidecar injection enabled for ${RETAIL_NS}"
    else
        echo "  Sidecar injection already enabled for ${RETAIL_NS}"
    fi
else
    echo "  WARNING: Namespace ${RETAIL_NS} not found."
    echo "  retail-store-sample-app이 아직 배포되지 않았습니다."
    echo "  Module 5의 sample-app 스택을 먼저 배포해주세요."
    echo "  Skipping Part A..."
    SKIP_RETAIL=true
fi

# -----------------------------------------------
# A-2. 기존 Pod 재시작 (사이드카 주입 적용)
# -----------------------------------------------
if [ "${SKIP_RETAIL}" != "true" ]; then
    echo ""
    echo "[A-2] Restarting retail-store pods for sidecar injection..."

    # Deployment 목록 가져오기
    DEPLOYMENTS=$(kubectl get deployments -n ${RETAIL_NS} -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$DEPLOYMENTS" ]; then
        for dep in $DEPLOYMENTS; do
            echo "  Restarting deployment: ${dep}"
            kubectl rollout restart deployment/${dep} -n ${RETAIL_NS}
        done

        echo "  Waiting for rollout to complete..."
        for dep in $DEPLOYMENTS; do
            kubectl rollout status deployment/${dep} -n ${RETAIL_NS} --timeout=120s 2>/dev/null || true
        done
        echo "  retail-store pods restarted with Istio sidecar"
    else
        echo "  No deployments found in ${RETAIL_NS}"
    fi

    # -----------------------------------------------
    # A-3. 사이드카 주입 확인
    # -----------------------------------------------
    echo ""
    echo "[A-3] Verifying sidecar injection..."
    SIDECAR_COUNT=$(kubectl get pods -n ${RETAIL_NS} -o jsonpath='{range .items[*]}{.spec.containers[*].name}{"\n"}{end}' 2>/dev/null | grep -c "istio-proxy" || echo "0")
    TOTAL_PODS=$(kubectl get pods -n ${RETAIL_NS} --no-headers 2>/dev/null | wc -l || echo "0")
    echo "  Pods with istio-proxy sidecar: ${SIDECAR_COUNT}/${TOTAL_PODS}"
fi

# =============================================================
# Part B: Istio Official Sample App (istio-sample namespace)
# =============================================================
echo ""
echo "============================================"
echo " Part B: Istio Official Sample App"
echo "============================================"

# -----------------------------------------------
# B-1. istio-sample 네임스페이스 생성 + 사이드카 주입 활성화
# -----------------------------------------------
echo ""
echo "[B-1] Creating ${ISTIO_SAMPLE_NS} namespace with sidecar injection..."
kubectl create namespace ${ISTIO_SAMPLE_NS} --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace ${ISTIO_SAMPLE_NS} istio-injection=enabled --overwrite
echo "  Namespace ${ISTIO_SAMPLE_NS} ready with sidecar injection"

# -----------------------------------------------
# B-2. Istio 샘플 앱 배포 (Bookinfo)
# -----------------------------------------------
echo ""
echo "[B-2] Deploying Istio sample application (Bookinfo)..."
kubectl apply -f ${SAMPLE_DIR}/istio-sample-app/bookinfo.yaml

echo "  Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod -l app=productpage -n ${ISTIO_SAMPLE_NS} --timeout=120s 2>/dev/null || true
kubectl wait --for=condition=ready pod -l app=reviews -n ${ISTIO_SAMPLE_NS} --timeout=120s 2>/dev/null || true
kubectl wait --for=condition=ready pod -l app=ratings -n ${ISTIO_SAMPLE_NS} --timeout=120s 2>/dev/null || true
kubectl wait --for=condition=ready pod -l app=details -n ${ISTIO_SAMPLE_NS} --timeout=120s 2>/dev/null || true

# -----------------------------------------------
# B-3. Istio 네트워킹 리소스 적용
# -----------------------------------------------
echo ""
echo "[B-3] Applying Istio networking resources..."
kubectl apply -f ${SAMPLE_DIR}/istio-sample-app/bookinfo-gateway.yaml
kubectl apply -f ${SAMPLE_DIR}/istio-sample-app/destination-rules.yaml
kubectl apply -f ${SAMPLE_DIR}/istio-sample-app/virtual-services.yaml
kubectl apply -f ${SAMPLE_DIR}/istio-sample-app/peer-authentication.yaml

echo "  Gateway, VirtualServices, DestinationRules, PeerAuthentication applied"

# -----------------------------------------------
# B-4. Ingress Gateway 엔드포인트 확인
# -----------------------------------------------
echo ""
echo "[B-4] Getting Ingress Gateway endpoint..."

INGRESS_HOST=""
for i in {1..30}; do
    INGRESS_HOST=$(kubectl get svc istio-ingressgateway -n istio-system \
        -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
    if [ -z "$INGRESS_HOST" ]; then
        INGRESS_HOST=$(kubectl get svc istio-ingressgateway -n istio-system \
            -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    fi
    if [ -n "$INGRESS_HOST" ]; then
        break
    fi
    echo "  Waiting for LoadBalancer... (${i}/30)"
    sleep 10
done

INGRESS_PORT=$(kubectl get svc istio-ingressgateway -n istio-system \
    -o jsonpath='{.spec.ports[?(@.name=="http2")].port}' 2>/dev/null || echo "80")

GATEWAY_URL="${INGRESS_HOST}:${INGRESS_PORT}"
echo "  Gateway URL: http://${GATEWAY_URL}/productpage"

# -----------------------------------------------
# B-5. 초기 트래픽 생성 (메트릭 시딩)
# -----------------------------------------------
echo ""
echo "[B-5] Generating initial traffic for metric seeding..."

if [ -n "$INGRESS_HOST" ]; then
    echo "  Sending 100 requests to Istio sample app (productpage)..."
    for i in $(seq 1 100); do
        curl -s -o /dev/null -w "%{http_code}" "http://${GATEWAY_URL}/productpage" 2>/dev/null || true
        if [ $((i % 20)) -eq 0 ]; then
            echo "    ${i}/100 requests sent"
        fi
    done
    echo "  Traffic generation complete"
else
    echo "  WARNING: Could not determine Ingress Gateway IP"
    echo "  Generate traffic manually after LoadBalancer is ready:"
    echo "    for i in \$(seq 1 100); do curl -s http://\$GATEWAY_URL/productpage > /dev/null; done"
fi

# =============================================================
# Summary
# =============================================================
echo ""
echo "============================================================"
echo " Deployment Complete!"
echo "============================================================"

if [ "${SKIP_RETAIL}" != "true" ]; then
    echo ""
    echo "--- retail-store (${RETAIL_NS}) ---"
    echo "Pods with sidecar:"
    kubectl get pods -n ${RETAIL_NS} --no-headers 2>/dev/null | head -10 || true
fi

echo ""
echo "--- Istio Sample App (${ISTIO_SAMPLE_NS}) ---"
echo "Pods:"
kubectl get pods -n ${ISTIO_SAMPLE_NS} --no-headers 2>/dev/null || true
echo ""
echo "Istio Resources:"
kubectl get virtualservices,destinationrules,gateways,peerauthentication -n ${ISTIO_SAMPLE_NS} --no-headers 2>/dev/null || true

if [ -n "$INGRESS_HOST" ]; then
    echo ""
    echo "Access Istio Sample App: http://${GATEWAY_URL}/productpage"
fi

echo ""
echo "Fault Injection (istio-sample namespace):"
echo "  kubectl apply -f ${SAMPLE_DIR}/fault-injection/fault-delay-reviews.yaml"
echo "  kubectl apply -f ${SAMPLE_DIR}/fault-injection/fault-abort-ratings.yaml"
echo "  kubectl apply -f ${SAMPLE_DIR}/fault-injection/circuit-breaker.yaml"
echo ""
echo "Note: retail-store pods now have Istio sidecar for mesh observability."
echo "      istio-sample app supports traffic splitting, fault injection, circuit breaker demos."
