"""
=============================================================================
Lambda Function - Chaos Engineering MCP Tools (Module 6)
Lambda 함수 - 카오스 엔지니어링 MCP 도구 (모듈 6)
=============================================================================

Description (설명):
    Provides MCP tools for triggering chaos engineering scenarios on the EKS cluster.
    EKS 클러스터에서 카오스 엔지니어링 시나리오를 트리거하는 MCP 도구를 제공합니다.

Tools (도구):
    - chaos-cpu-stress: Deploy a stress pod that spikes CPU (CPU 스파이크 파드 배포)
    - chaos-error-injection: Deploy a pod that generates ERROR logs (에러 로그 생성 파드)
    - chaos-latency-injection: Deploy a pod that simulates high latency (지연 시뮬레이션 파드)
    - chaos-pod-crash: Deploy a pod configured to CrashLoopBackOff (크래시 파드 배포)
    - chaos-cleanup: Delete all chaos pods with label app=chaos-test (모든 카오스 파드 삭제)

Environment Variables (환경변수):
    TARGET_REGION: AWS region (default: us-west-2)
    AWS_REGION: Fallback region if TARGET_REGION not set

Author: NetAIOps Team
Module: workshop-module-6
=============================================================================
"""

import json
import os
import logging
import base64
import re
import boto3
from datetime import datetime
from botocore.signers import RequestSigner

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# =============================================================================
# Configuration (설정)
# =============================================================================
REGION = os.environ.get("TARGET_REGION", os.environ.get("AWS_REGION", "us-west-2"))
CLUSTER_NAME = "netaiops-eks-cluster"
NAMESPACE = "default"

# =============================================================================
# Tool Schema Definitions (도구 스키마 정의)
# =============================================================================
TOOL_SCHEMAS = [
    {
        "name": "chaos-cpu-stress",
        "description": "Deploy a stress pod that spikes CPU usage. CPU 부하를 생성하는 파드를 배포합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "chaos-error-injection",
        "description": "Deploy a pod that generates ERROR logs to stdout. 에러 로그를 생성하는 파드를 배포합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "chaos-latency-injection",
        "description": "Deploy a pod that simulates high latency with warning logs. 지연 경고 로그를 생성하는 파드를 배포합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "chaos-pod-crash",
        "description": "Deploy a pod configured to CrashLoopBackOff. CrashLoopBackOff 파드를 배포합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "chaos-cleanup",
        "description": "Delete all chaos pods with label app=chaos-test. app=chaos-test 레이블의 모든 파드를 삭제합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


# =============================================================================
# Kubernetes Client Setup (쿠버네티스 클라이언트 설정)
# =============================================================================
def _get_eks_token():
    """Generate a presigned token for EKS authentication.
    EKS 인증을 위한 사전 서명 토큰을 생성합니다."""
    STS_TOKEN_EXPIRES_IN = 60
    session = boto3.session.Session()

    sts_client = session.client("sts", region_name=REGION)
    service_id = sts_client.meta.service_model.service_id

    signer = RequestSigner(
        service_id,
        REGION,
        "sts",
        "v4",
        session.get_credentials(),
        session.events
    )

    params = {
        "method": "GET",
        "url": f"https://sts.{REGION}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
        "body": {},
        "headers": {"x-k8s-aws-id": CLUSTER_NAME},
        "context": {},
    }

    signed_url = signer.generate_presigned_url(
        params,
        region_name=REGION,
        expires_in=STS_TOKEN_EXPIRES_IN,
        operation_name="",
    )

    base64_url = base64.urlsafe_b64encode(signed_url.encode("utf-8")).decode("utf-8")
    # Remove base64 padding
    return "k8s-aws-v1." + re.sub(r"=*", "", base64_url)


def _get_k8s_client():
    """Get an authenticated Kubernetes API client for the EKS cluster.
    EKS 클러스터용 인증된 쿠버네티스 API 클라이언트를 가져옵니다."""
    from kubernetes import client as k8s_client
    from kubernetes.client import Configuration

    # Get EKS cluster info (EKS 클러스터 정보 가져오기)
    eks_client = boto3.client("eks", region_name=REGION)
    cluster_info = eks_client.describe_cluster(name=CLUSTER_NAME)
    cluster = cluster_info["cluster"]

    # Configure kubernetes client (쿠버네티스 클라이언트 설정)
    configuration = Configuration()
    configuration.host = cluster["endpoint"]
    configuration.verify_ssl = True

    # Write CA cert to temp file (CA 인증서를 임시 파일에 작성)
    ca_data = base64.b64decode(cluster["certificateAuthority"]["data"])
    ca_file = "/tmp/eks_ca.crt"
    with open(ca_file, "wb") as f:
        f.write(ca_data)
    configuration.ssl_ca_cert = ca_file

    # Get token (토큰 가져오기)
    configuration.api_key = {"authorization": f"Bearer {_get_eks_token()}"}

    api_client = k8s_client.ApiClient(configuration)
    return api_client


# =============================================================================
# Main Handler (메인 핸들러)
# =============================================================================
def _extract_tool_info(event):
    """Extract tool name and arguments from various event formats.
    다양한 이벤트 형식에서 도구 이름과 인자를 추출합니다.

    MCP Gateway sends only arguments to Lambda - for chaos tools, we require
    the event to have a "name" key to specify which chaos tool to run.
    MCP 게이트웨이는 인자만 Lambda에 전송하므로, chaos 도구의 경우
    실행할 도구를 지정하려면 "name" 키가 필요합니다."""
    tool_name = ""
    arguments = {}

    # MCP protocol format: {"method": "tools/call", "params": {"name": "...", "arguments": {...}}}
    method = event.get("method", "")
    if method == "tools/list":
        return "__list_tools__", {}
    if method == "tools/call":
        params = event.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
    # Direct invocation: {"tool_name": "...", "parameters": {...}}
    elif "tool_name" in event:
        tool_name = event["tool_name"]
        arguments = event.get("parameters", {})
    # Simplified: {"name": "...", "arguments": {...}}
    elif "name" in event:
        tool_name = event["name"]
        arguments = event.get("arguments", {})
    # Legacy: {"action": "list_tools"}
    elif event.get("action") == "list_tools":
        return "__list_tools__", {}
    else:
        # MCP Gateway Lambda integration: event IS the arguments directly
        # For chaos tools, we cannot infer which tool from arguments alone
        # Return error asking for explicit tool name
        # chaos 도구의 경우 인자만으로 도구를 추론할 수 없으므로
        # 명시적인 도구 이름을 요청하는 오류 반환
        arguments = event
        return "", arguments

    # Strip MCP Gateway target prefix (TargetName___tool-name → tool-name)
    if "___" in tool_name:
        tool_name = tool_name.split("___", 1)[1]

    return tool_name, arguments


def lambda_handler(event, context):
    """Main Lambda handler. 메인 Lambda 핸들러."""
    print(f"RAW_EVENT: {json.dumps(event, default=str)[:2000]}")
    tool_name, parameters = _extract_tool_info(event)
    print(f"EXTRACTED: tool_name={tool_name}, parameters={json.dumps(parameters, default=str)[:500]}")

    if tool_name == "__list_tools__":
        return {"tools": TOOL_SCHEMAS}

    handlers = {
        "chaos-cpu-stress": handle_cpu_stress,
        "chaos-error-injection": handle_error_injection,
        "chaos-latency-injection": handle_latency_injection,
        "chaos-pod-crash": handle_pod_crash,
        "chaos-cleanup": handle_cleanup,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {
            "error": f"Unknown tool: {tool_name}. Please specify tool name using 'name' field.",
            "available_tools": list(handlers.keys()),
            "hint": "Use payload format: {\"name\": \"chaos-cpu-stress\", \"arguments\": {}}"
        }

    try:
        return handler(parameters)
    except Exception as e:
        logger.error(f"Tool execution failed: {str(e)}", exc_info=True)
        return {"error": f"Tool execution failed: {str(e)}", "tool": tool_name}


# =============================================================================
# Tool Handlers (도구 핸들러)
# =============================================================================
def handle_cpu_stress(params):
    """Deploy a stress deployment that spikes CPU. CPU 부하 Deployment를 배포합니다."""
    from kubernetes import client as k8s_client

    api_client = _get_k8s_client()
    apps_v1 = k8s_client.AppsV1Api(api_client)
    core_v1 = k8s_client.CoreV1Api(api_client)

    deploy_name = "chaos-cpu-stress"
    labels = {"app": "chaos-test", "chaos-type": "cpu-stress"}

    # Delete existing deployment if present (기존 Deployment가 있으면 삭제)
    try:
        apps_v1.delete_namespaced_deployment(name=deploy_name, namespace=NAMESPACE)
        logger.info(f"Deleted existing deployment: {deploy_name}")
    except k8s_client.exceptions.ApiException as e:
        if e.status != 404:
            raise

    # Delete leftover standalone pod if present (레거시 standalone 파드 정리)
    try:
        core_v1.delete_namespaced_pod(name=deploy_name, namespace=NAMESPACE)
    except k8s_client.exceptions.ApiException:
        pass

    # Create stress deployment (스트레스 Deployment 생성)
    # Uses Deployment so Container Insights collects pod_cpu_utilization metrics
    # Deployment 사용으로 Container Insights가 pod_cpu_utilization 메트릭 수집
    deployment = k8s_client.V1Deployment(
        metadata=k8s_client.V1ObjectMeta(
            name=deploy_name,
            namespace=NAMESPACE,
            labels=labels,
        ),
        spec=k8s_client.V1DeploymentSpec(
            replicas=1,
            selector=k8s_client.V1LabelSelector(match_labels=labels),
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(labels=labels),
                spec=k8s_client.V1PodSpec(
                    containers=[
                        k8s_client.V1Container(
                            name="stress",
                            image="public.ecr.aws/amazonlinux/amazonlinux:2",
                            command=["sh", "-c",
                                     "# CPU stress using bash busy loop (no install needed)\n"
                                     "for i in $(seq 1 4); do while :; do :; done & done\n"
                                     "sleep 600\n"
                                     "kill 0"],
                            resources=k8s_client.V1ResourceRequirements(
                                requests={"cpu": "500m", "memory": "64Mi"},
                                limits={"cpu": "2", "memory": "128Mi"},
                            ),
                        )
                    ],
                ),
            ),
        ),
    )

    apps_v1.create_namespaced_deployment(namespace=NAMESPACE, body=deployment)

    return {
        "status": "success",
        "message": f"Deployed CPU stress deployment '{deploy_name}' in namespace '{NAMESPACE}'",
        "deployment_name": deploy_name,
        "namespace": NAMESPACE,
        "cluster": CLUSTER_NAME,
        "duration_seconds": 600,
    }


def handle_error_injection(params):
    """Deploy a pod that generates ERROR logs. 에러 로그 생성 파드를 배포합니다."""
    from kubernetes import client as k8s_client

    api_client = _get_k8s_client()
    core_v1 = k8s_client.CoreV1Api(api_client)

    pod_name = "chaos-error-injection"

    # Delete existing pod if present (기존 파드가 있으면 삭제)
    try:
        core_v1.delete_namespaced_pod(name=pod_name, namespace=NAMESPACE)
        logger.info(f"Deleted existing pod: {pod_name}")
    except k8s_client.exceptions.ApiException as e:
        if e.status != 404:
            raise

    # Create error injection pod that prints JSON ERROR logs
    # JSON 형식 ERROR 로그를 출력하는 에러 주입 파드 생성
    error_script = '''
while true; do
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "{\\"timestamp\\":\\"$timestamp\\",\\"level\\":\\"ERROR\\",\\"message\\":\\"Connection refused to database\\",\\"service\\":\\"web-api\\",\\"error_code\\":\\"ECONNREFUSED\\"}"
  sleep 2
done
'''

    pod = k8s_client.V1Pod(
        metadata=k8s_client.V1ObjectMeta(
            name=pod_name,
            namespace=NAMESPACE,
            labels={"app": "chaos-test", "chaos-type": "error-injection"},
        ),
        spec=k8s_client.V1PodSpec(
            restart_policy="Always",
            containers=[
                k8s_client.V1Container(
                    name="error-generator",
                    image="busybox",
                    command=["sh", "-c", error_script],
                    resources=k8s_client.V1ResourceRequirements(
                        requests={"cpu": "50m", "memory": "32Mi"},
                        limits={"cpu": "100m", "memory": "64Mi"},
                    ),
                )
            ],
        ),
    )

    core_v1.create_namespaced_pod(namespace=NAMESPACE, body=pod)

    return {
        "status": "success",
        "message": f"Deployed ERROR log generator pod '{pod_name}' in namespace '{NAMESPACE}'",
        "pod_name": pod_name,
        "namespace": NAMESPACE,
        "cluster": CLUSTER_NAME,
        "log_format": "JSON with ERROR level every 2 seconds",
    }


def handle_latency_injection(params):
    """Deploy a pod that simulates high latency. 지연 시뮬레이션 파드를 배포합니다."""
    from kubernetes import client as k8s_client

    api_client = _get_k8s_client()
    core_v1 = k8s_client.CoreV1Api(api_client)

    pod_name = "chaos-latency-injection"

    # Delete existing pod if present (기존 파드가 있으면 삭제)
    try:
        core_v1.delete_namespaced_pod(name=pod_name, namespace=NAMESPACE)
        logger.info(f"Deleted existing pod: {pod_name}")
    except k8s_client.exceptions.ApiException as e:
        if e.status != 404:
            raise

    # Create latency injection pod that prints WARN logs about high latency
    # 높은 지연에 대한 WARN 로그를 출력하는 지연 주입 파드 생성
    latency_script = '''
while true; do
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  latency=$((RANDOM % 500 + 500))
  echo "{\\"timestamp\\":\\"$timestamp\\",\\"level\\":\\"WARN\\",\\"message\\":\\"High latency detected: ${latency}ms\\",\\"service\\":\\"api-gateway\\",\\"latency_ms\\":$latency}"
  sleep 3
done
'''

    pod = k8s_client.V1Pod(
        metadata=k8s_client.V1ObjectMeta(
            name=pod_name,
            namespace=NAMESPACE,
            labels={"app": "chaos-test", "chaos-type": "latency-injection"},
        ),
        spec=k8s_client.V1PodSpec(
            restart_policy="Always",
            containers=[
                k8s_client.V1Container(
                    name="latency-simulator",
                    image="busybox",
                    command=["sh", "-c", latency_script],
                    resources=k8s_client.V1ResourceRequirements(
                        requests={"cpu": "50m", "memory": "32Mi"},
                        limits={"cpu": "100m", "memory": "64Mi"},
                    ),
                )
            ],
        ),
    )

    core_v1.create_namespaced_pod(namespace=NAMESPACE, body=pod)

    return {
        "status": "success",
        "message": f"Deployed latency simulator pod '{pod_name}' in namespace '{NAMESPACE}'",
        "pod_name": pod_name,
        "namespace": NAMESPACE,
        "cluster": CLUSTER_NAME,
        "log_format": "JSON with WARN level about high latency every 3 seconds",
    }


def handle_pod_crash(params):
    """Deploy a pod configured to CrashLoopBackOff. CrashLoopBackOff 파드를 배포합니다."""
    from kubernetes import client as k8s_client

    api_client = _get_k8s_client()
    core_v1 = k8s_client.CoreV1Api(api_client)

    pod_name = "chaos-pod-crash"

    # Delete existing pod if present (기존 파드가 있으면 삭제)
    try:
        core_v1.delete_namespaced_pod(name=pod_name, namespace=NAMESPACE)
        logger.info(f"Deleted existing pod: {pod_name}")
    except k8s_client.exceptions.ApiException as e:
        if e.status != 404:
            raise

    # Create crash pod that exits immediately
    # 즉시 종료되는 크래시 파드 생성
    pod = k8s_client.V1Pod(
        metadata=k8s_client.V1ObjectMeta(
            name=pod_name,
            namespace=NAMESPACE,
            labels={"app": "chaos-test", "chaos-type": "pod-crash"},
        ),
        spec=k8s_client.V1PodSpec(
            restart_policy="Always",  # Always restart to cause CrashLoopBackOff
            containers=[
                k8s_client.V1Container(
                    name="crasher",
                    image="busybox",
                    command=["sh", "-c", "exit 1"],
                    resources=k8s_client.V1ResourceRequirements(
                        requests={"cpu": "50m", "memory": "32Mi"},
                        limits={"cpu": "100m", "memory": "64Mi"},
                    ),
                )
            ],
        ),
    )

    core_v1.create_namespaced_pod(namespace=NAMESPACE, body=pod)

    return {
        "status": "success",
        "message": f"Deployed crash pod '{pod_name}' in namespace '{NAMESPACE}' (will enter CrashLoopBackOff)",
        "pod_name": pod_name,
        "namespace": NAMESPACE,
        "cluster": CLUSTER_NAME,
        "expected_state": "CrashLoopBackOff",
    }


def handle_cleanup(params):
    """Delete all chaos deployments and pods with label app=chaos-test.
    app=chaos-test 레이블의 모든 Deployment와 파드를 삭제합니다."""
    from kubernetes import client as k8s_client

    api_client = _get_k8s_client()
    core_v1 = k8s_client.CoreV1Api(api_client)
    apps_v1 = k8s_client.AppsV1Api(api_client)

    deleted = []
    errors = []

    # Delete deployments with label app=chaos-test (Deployment 삭제)
    try:
        deploy_list = apps_v1.list_namespaced_deployment(
            namespace=NAMESPACE,
            label_selector="app=chaos-test"
        )
        for deploy in deploy_list.items:
            deploy_name = deploy.metadata.name
            chaos_type = deploy.metadata.labels.get("chaos-type", "unknown")
            try:
                apps_v1.delete_namespaced_deployment(
                    name=deploy_name,
                    namespace=NAMESPACE
                )
                deleted.append(f"{chaos_type} (deploy/{deploy_name})")
                logger.info(f"Deleted chaos deployment: {deploy_name}")
            except Exception as e:
                error_msg = f"Failed to delete deploy/{deploy_name}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
    except Exception as e:
        logger.warning(f"Failed to list chaos deployments: {str(e)}")

    # Delete standalone pods with label app=chaos-test (standalone 파드 삭제)
    try:
        pod_list = core_v1.list_namespaced_pod(
            namespace=NAMESPACE,
            label_selector="app=chaos-test"
        )
        for pod in pod_list.items:
            pod_name = pod.metadata.name
            # Skip pods owned by a ReplicaSet (managed by Deployment)
            # Deployment가 관리하는 파드는 Deployment 삭제 시 자동 정리됨
            owners = pod.metadata.owner_references or []
            if any(o.kind == "ReplicaSet" for o in owners):
                continue
            chaos_type = pod.metadata.labels.get("chaos-type", "unknown")
            try:
                core_v1.delete_namespaced_pod(
                    name=pod_name,
                    namespace=NAMESPACE
                )
                deleted.append(f"{chaos_type} ({pod_name})")
                logger.info(f"Deleted chaos pod: {pod_name}")
            except Exception as e:
                error_msg = f"Failed to delete {pod_name}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
    except Exception as e:
        logger.warning(f"Failed to list chaos pods: {str(e)}")

    if not deleted and not errors:
        return {
            "status": "success",
            "message": "No chaos resources found to clean up",
            "reverted": [],
            "namespace": NAMESPACE,
            "cluster": CLUSTER_NAME,
        }

    result = {
        "status": "success" if not errors else "partial",
        "message": f"Cleaned up {len(deleted)} chaos resource(s)",
        "reverted": deleted,
        "namespace": NAMESPACE,
        "cluster": CLUSTER_NAME,
    }

    if errors:
        result["errors"] = errors

    return result
