"""
NetAIOps Agent Hub - FastAPI Backend
=====================================
REST + SSE API for multiple AgentCore agents.
Ported from the Streamlit frontend.
"""

import json
import os
import subprocess
import time
import uuid
import urllib.parse
from typing import Optional

import boto3
import requests as http_requests
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AGENT_REGION = os.environ.get("AGENT_REGION", "us-east-1")
CHAOS_LAMBDA_NAME = os.environ.get("CHAOS_LAMBDA_NAME", "incident-chaos-tools")

AGENTS = {
    "k8s": {
        "id": "k8s",
        "name": "K8s Diagnostics Agent",
        "icon": "☸",
        "description": "EKS 클러스터 진단 에이전트 — 리전을 동적으로 전환하며 분석합니다.",
        "ssm_prefix": "/a2a/app/k8s/agentcore",
        "config_path": os.environ.get(
            "K8S_AGENT_CONFIG_PATH",
            os.path.join(
                os.path.dirname(__file__), "..", "..",
                "workshop-module-5", "module-5", "agentcore-k8s-agent",
                ".bedrock_agentcore.yaml",
            ),
        ),
        "placeholder": "Ask about your EKS clusters...",
        "scenarios": [],
    },
    "incident": {
        "id": "incident",
        "name": "Incident Analysis Agent",
        "icon": "🔍",
        "description": "인시던트 자동 분석 에이전트 — Datadog, OpenSearch, Container Insight 통합 분석.",
        "ssm_prefix": "/app/incident/agentcore",
        "config_path": os.environ.get(
            "INCIDENT_AGENT_CONFIG_PATH",
            os.path.join(
                os.path.dirname(__file__), "..", "..",
                "workshop-module-6", "module-6", "agentcore-incident-agent",
                ".bedrock_agentcore.yaml",
            ),
        ),
        "placeholder": "인시던트 상황을 설명하세요... (예: API 에러율이 5%를 초과했습니다)",
        "scenarios": [
            {"id": "cpu", "name": "CPU 급증 분석", "prompt": "서비스 web-api의 CPU 사용률이 90%를 넘었습니다. 원인을 분석해주세요."},
            {"id": "error", "name": "에러율 증가", "prompt": "지난 1시간 동안 payment 서비스의 에러율이 5%를 초과했습니다. 로그와 메트릭을 분석해주세요."},
            {"id": "latency", "name": "지연 시간 급증", "prompt": "API 응답 지연이 P99 기준 2초를 넘었습니다. APM 트레이스와 컨테이너 상태를 확인해주세요."},
            {"id": "pod", "name": "파드 재시작 반복", "prompt": "EKS 클러스터에서 checkout-service 파드가 반복적으로 재시작됩니다. 진단해주세요."},
        ],
    },
    "istio": {
        "id": "istio",
        "name": "Istio Mesh Diagnostics Agent",
        "icon": "⚡",
        "description": "Istio 서비스 메시 진단 에이전트 — mTLS, 트래픽 라우팅, 컨트롤 플레인, Envoy 사이드카 분석.",
        "ssm_prefix": "/app/istio/agentcore",
        "config_path": os.environ.get(
            "ISTIO_AGENT_CONFIG_PATH",
            os.path.join(
                os.path.dirname(__file__), "..", "..",
                "workshop-module-7", "module-7", "agentcore-istio-agent",
                ".bedrock_agentcore.yaml",
            ),
        ),
        "placeholder": "Istio 메시 진단 요청을 입력하세요... (예: productpage에서 reviews로 503 에러 발생)",
        "scenarios": [
            {"id": "connectivity", "name": "서비스 연결 실패 진단", "prompt": "istio-sample 네임스페이스에서 productpage→reviews 요청 시 503 에러가 발생합니다. 토폴로지, 사이드카, VirtualService, mTLS 설정을 확인해주세요."},
            {"id": "mtls", "name": "mTLS 감사", "prompt": "메시 전체의 mTLS 설정 상태를 확인해주세요. retail-store, istio-sample 등 모든 네임스페이스의 PeerAuthentication 정책, 사이드카 미주입 파드, 보안 권고사항을 알려주세요."},
            {"id": "canary", "name": "카나리 배포 분석", "prompt": "istio-sample 네임스페이스의 reviews 서비스 트래픽 라우팅 상태를 확인해주세요. VirtualService 가중치 설정(v1=80%, v2=10%, v3=10%)과 실제 트래픽 비율을 비교 분석해주세요."},
            {"id": "controlplane", "name": "컨트롤 플레인 상태", "prompt": "istiod 컨트롤 플레인의 상태를 확인해주세요. xDS 푸시 지연, 에러, 설정 충돌, 연결된 프록시 수를 알려주세요."},
            {"id": "latency", "name": "지연 핫스팟 탐지", "prompt": "retail-store와 istio-sample 양쪽 네임스페이스의 P99 지연 시간을 스캔하고, 가장 느린 서비스를 식별해주세요. VirtualService fault injection 여부도 확인해주세요."},
        ],
    },
}

MODELS = [
    # Claude
    {"id": "global.anthropic.claude-opus-4-6-v1", "name": "Claude Opus 4.6"},
    {"id": "global.anthropic.claude-sonnet-4-6", "name": "Claude Sonnet 4.6"},
    {"id": "global.anthropic.claude-sonnet-4-5-20250929-v1:0", "name": "Claude Sonnet 4.5"},
    {"id": "global.anthropic.claude-haiku-4-5-20251001-v1:0", "name": "Claude Haiku 4.5"},
    # Qwen
    {"id": "qwen.qwen3-32b-v1:0", "name": "Qwen 3 32B"},
    # Nova
    {"id": "us.amazon.nova-pro-v1:0", "name": "Nova Pro"},
    {"id": "us.amazon.nova-lite-v1:0", "name": "Nova Lite"},
]

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_token_cache: dict = {}  # agent_id -> {"token": str, "timestamp": float}
_active_chaos: set = set()
_active_faults: set = set()  # active Istio fault injection labels
_arn_cache: dict = {}  # agent_id -> arn

# Istio fault injection YAML paths
FAULT_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..",
    "workshop-module-7", "sample-workload", "fault-injection",
))
FAULT_FILES = {
    "delay": os.path.join(FAULT_DIR, "fault-delay-reviews.yaml"),
    "abort": os.path.join(FAULT_DIR, "fault-abort-ratings.yaml"),
    "circuit-breaker": os.path.join(FAULT_DIR, "circuit-breaker.yaml"),
}

# ---------------------------------------------------------------------------
# AWS clients (lazy)
# ---------------------------------------------------------------------------
_ssm_client = None
_lambda_client = None

# AWS session: use AWS_PROFILE if set (local dev), otherwise instance role (EC2 deploy)
AWS_PROFILE = os.environ.get("AWS_PROFILE", "")
if AWS_PROFILE:
    _boto_session = boto3.Session(profile_name=AWS_PROFILE, region_name=AGENT_REGION)
else:
    _boto_session = boto3.Session(region_name=AGENT_REGION)


def _get_ssm():
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = _boto_session.client("ssm", region_name=AGENT_REGION)
    return _ssm_client


def _get_lambda():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = _boto_session.client("lambda", region_name=AGENT_REGION)
    return _lambda_client


# ---------------------------------------------------------------------------
# AWS helpers
# ---------------------------------------------------------------------------
def get_ssm_parameter(name: str) -> Optional[str]:
    try:
        resp = _get_ssm().get_parameter(Name=name, WithDecryption=True)
        return resp["Parameter"]["Value"]
    except Exception:
        return None


def get_m2m_access_token(ssm_prefix: str) -> Optional[str]:
    """Get access token using Cognito M2M client_credentials flow."""
    client_id = get_ssm_parameter(f"{ssm_prefix}/machine_client_id")
    client_secret = get_ssm_parameter(f"{ssm_prefix}/machine_client_secret")
    token_url = get_ssm_parameter(f"{ssm_prefix}/cognito_token_url")
    scopes = get_ssm_parameter(f"{ssm_prefix}/cognito_auth_scope")

    if not all([client_id, client_secret, token_url]):
        return None

    try:
        resp = http_requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": scopes or "",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
    except Exception:
        pass
    return None


def get_agent_arn(agent_id: str) -> Optional[str]:
    """Discover agent runtime ARN from YAML config or SSM."""
    if agent_id in _arn_cache:
        return _arn_cache[agent_id]

    agent_cfg = AGENTS[agent_id]
    config_path = agent_cfg["config_path"]
    ssm_prefix = agent_cfg["ssm_prefix"]

    # Try local YAML first
    path = os.path.normpath(config_path)
    if os.path.exists(path):
        try:
            with open(path) as f:
                cfg = yaml.safe_load(f)
            default_agent = cfg.get("default_agent", "")
            agents = cfg.get("agents", {})
            agent_c = agents.get(default_agent, {})
            arn = agent_c.get("bedrock_agentcore", {}).get("agent_arn")
            if arn:
                _arn_cache[agent_id] = arn
                return arn
        except Exception:
            pass

    # Fallback to SSM
    arn = get_ssm_parameter(f"{ssm_prefix}/agent_runtime_arn")
    if arn:
        _arn_cache[agent_id] = arn
    return arn


def ensure_token(agent_id: str) -> Optional[str]:
    """Return a valid cached token or fetch a new one."""
    cached = _token_cache.get(agent_id)
    if cached and (time.time() - cached["timestamp"]) < 3500:
        return cached["token"]

    agent_cfg = AGENTS[agent_id]
    token = get_m2m_access_token(agent_cfg["ssm_prefix"])
    if token:
        _token_cache[agent_id] = {"token": token, "timestamp": time.time()}
    return token


# ---------------------------------------------------------------------------
# AgentCore invocation (streaming SSE)
# ---------------------------------------------------------------------------
def invoke_agent(agent_arn: str, token: str, session_id: str, prompt: str, model_id: str = None):
    """Invoke AgentCore runtime and yield streamed text chunks."""
    escaped_arn = urllib.parse.quote(agent_arn, safe="")
    url = (
        f"https://bedrock-agentcore.{AGENT_REGION}.amazonaws.com"
        f"/runtimes/{escaped_arn}/invocations"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }

    body = {"prompt": prompt, "actor_id": "DEFAULT"}
    if model_id:
        body["model_id"] = model_id

    try:
        resp = http_requests.post(
            url,
            params={"qualifier": "DEFAULT"},
            headers=headers,
            json=body,
            timeout=300,
            stream=True,
        )

        if resp.status_code != 200:
            yield f"Error ({resp.status_code}): {resp.text}"
            return

        for line in resp.iter_lines(chunk_size=8192, decode_unicode=True):
            if not line:
                continue
            if line.strip() in ("data: [DONE]", "[DONE]"):
                break
            if line.startswith("data: "):
                content = line[6:].strip('"')
                content = content.replace("\\n", "\n")
                content = content.replace('\\"', '"')
                content = content.replace("\\\\", "\\")
                yield content
            elif line.startswith("event: "):
                continue

    except http_requests.exceptions.Timeout:
        yield "Request timed out (5 min limit)."
    except http_requests.exceptions.ConnectionError:
        yield "Connection error. Is the agent runtime running?"
    except Exception as e:
        yield f"Error: {e}"


# ---------------------------------------------------------------------------
# Chaos Engineering helpers
# ---------------------------------------------------------------------------
def trigger_chaos(scenario_name: str, params: dict = None) -> dict:
    payload = {"name": scenario_name, "arguments": params or {}}
    try:
        resp = _get_lambda().invoke(
            FunctionName=CHAOS_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        result = json.loads(resp["Payload"].read())
        return result
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="NetAIOps Agent Hub")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- Pydantic models -------------------------------------------------------
class ChatRequest(BaseModel):
    agent_id: str
    session_id: str
    message: str
    model_id: str = None


class ChaosRequest(BaseModel):
    scenario: str


class FaultRequest(BaseModel):
    fault_type: str  # "delay" | "abort" | "circuit-breaker"


# -- Endpoints --------------------------------------------------------------
@app.get("/api/config")
def get_config():
    """Return agent definitions, available models, and region."""
    agents = []
    for aid, acfg in AGENTS.items():
        agents.append({
            "id": aid,
            "name": acfg["name"],
            "icon": acfg["icon"],
            "description": acfg["description"],
            "placeholder": acfg["placeholder"],
            "scenarios": acfg["scenarios"],
        })
    return {"agents": agents, "models": MODELS, "region": AGENT_REGION}


@app.post("/api/chat")
def chat(req: ChatRequest):
    """Stream agent response as SSE."""
    if req.agent_id not in AGENTS:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {req.agent_id}")

    token = ensure_token(req.agent_id)
    if not token:
        raise HTTPException(status_code=503, detail="Failed to acquire authentication token")

    arn = get_agent_arn(req.agent_id)
    if not arn:
        raise HTTPException(status_code=503, detail="Agent ARN not found")

    def event_stream():
        # Flush proxy buffers (CloudFront/nginx typically buffer 4-8KB)
        yield f": {' ' * 4096}\n\n"
        for chunk in invoke_agent(arn, token, req.session_id, req.message, req.model_id):
            data = json.dumps({"content": chunk})
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/chaos/trigger")
def chaos_trigger(req: ChaosRequest):
    """Trigger a chaos scenario."""
    result = trigger_chaos(req.scenario)
    if result.get("status") == "success":
        _active_chaos.add(req.scenario)
    return result


@app.post("/api/chaos/cleanup")
def chaos_cleanup():
    """Cleanup all active chaos scenarios."""
    result = trigger_chaos("chaos-cleanup")
    if result.get("status") in ("success", "partial"):
        _active_chaos.clear()
    return result


@app.get("/api/chaos/status")
def chaos_status():
    """Return currently active chaos scenarios."""
    return {"active": list(_active_chaos)}


# -- Istio fault injection endpoints ----------------------------------------
def _run_kubectl(action: str, yaml_path: str) -> dict:
    """Run kubectl apply/delete on a YAML file."""
    if not os.path.exists(yaml_path):
        return {"status": "error", "error": f"File not found: {yaml_path}"}
    cmd = ["kubectl", action, "-f", yaml_path]
    if action == "delete":
        cmd.append("--ignore-not-found")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"status": "success", "output": result.stdout.strip()}
        return {"status": "error", "error": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "kubectl command timed out"}
    except FileNotFoundError:
        return {"status": "error", "error": "kubectl not found on this host"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/fault/apply")
def fault_apply(req: FaultRequest):
    """Apply an Istio fault injection YAML."""
    yaml_path = FAULT_FILES.get(req.fault_type)
    if not yaml_path:
        raise HTTPException(status_code=400, detail=f"Unknown fault type: {req.fault_type}")
    result = _run_kubectl("apply", yaml_path)
    if result["status"] == "success":
        _active_faults.add(req.fault_type)
    return result


@app.post("/api/fault/remove")
def fault_remove(req: FaultRequest):
    """Remove an Istio fault injection YAML."""
    yaml_path = FAULT_FILES.get(req.fault_type)
    if not yaml_path:
        raise HTTPException(status_code=400, detail=f"Unknown fault type: {req.fault_type}")
    result = _run_kubectl("delete", yaml_path)
    if result["status"] == "success":
        _active_faults.discard(req.fault_type)
    return result


@app.post("/api/fault/cleanup")
def fault_cleanup():
    """Remove all active Istio fault injections."""
    results = []
    for fault_type, yaml_path in FAULT_FILES.items():
        result = _run_kubectl("delete", yaml_path)
        results.append({"fault_type": fault_type, **result})
    _active_faults.clear()
    return {"status": "success", "results": results}


@app.get("/api/fault/status")
def fault_status():
    """Return currently active fault injections."""
    return {"active": list(_active_faults)}


# -- Static file serving (production build) ---------------------------------
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
