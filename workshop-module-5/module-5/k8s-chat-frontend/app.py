"""
NetAIOps Agent Hub - Streamlit Chat Frontend
=============================================
Unified chat UI for multiple AgentCore agents.

- Agent Menu: Switch between K8s Diagnostics and Incident Analysis agents
- Auto JWT: M2M client_credentials flow per agent (no manual token paste)
- Auto ARN: Discovered from config YAML or SSM Parameter Store
- SSE Streaming: Real-time streamed responses
"""

import json
import os
import time
import uuid
import urllib.parse
from typing import Optional

import boto3
import requests
import streamlit as st
import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AGENT_REGION = os.environ.get("AGENT_REGION", "us-east-1")

# Agent definitions
AGENTS = {
    "k8s": {
        "name": "K8s Diagnostics Agent",
        "icon": "☸",
        "description": "EKS 클러스터 진단 에이전트 — 리전을 동적으로 전환하며 분석합니다.",
        "ssm_prefix": "/a2a/app/k8s/agentcore",
        "config_path": os.environ.get(
            "K8S_AGENT_CONFIG_PATH",
            os.path.join(os.path.dirname(__file__), "..", "agentcore-k8s-agent", ".bedrock_agentcore.yaml"),
        ),
        "placeholder": "Ask about your EKS clusters...",
        "scenarios": {},
    },
    "incident": {
        "name": "Incident Analysis Agent",
        "icon": "🔍",
        "description": "인시던트 자동 분석 에이전트 — Datadog, OpenSearch, Container Insight 통합 분석.",
        "ssm_prefix": "/app/incident/agentcore",
        "config_path": os.environ.get(
            "INCIDENT_AGENT_CONFIG_PATH",
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "workshop-module-6", "module-6", "agentcore-incident-agent", ".bedrock_agentcore.yaml"),
        ),
        "placeholder": "인시던트 상황을 설명하세요... (예: API 에러율이 5%를 초과했습니다)",
        "scenarios": {
            "CPU 급증 분석": "서비스 web-api의 CPU 사용률이 90%를 넘었습니다. 원인을 분석해주세요.",
            "에러율 증가": "지난 1시간 동안 payment 서비스의 에러율이 5%를 초과했습니다. 로그와 메트릭을 분석해주세요.",
            "지연 시간 급증": "API 응답 지연이 P99 기준 2초를 넘었습니다. APM 트레이스와 컨테이너 상태를 확인해주세요.",
            "파드 재시작 반복": "EKS 클러스터에서 checkout-service 파드가 반복적으로 재시작됩니다. 진단해주세요.",
        },
    },
}

MODELS = [
    ("global.anthropic.claude-opus-4-6-v1", "Claude Opus 4.6"),
    ("global.anthropic.claude-sonnet-4-20250514-v1:0", "Claude Sonnet 4"),
]


# ---------------------------------------------------------------------------
# AWS helpers
# ---------------------------------------------------------------------------
_ssm_client = None


def _get_ssm():
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm", region_name=AGENT_REGION)
    return _ssm_client


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
        resp = requests.post(
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


def get_agent_arn(config_path: str, ssm_prefix: str) -> Optional[str]:
    """Discover agent runtime ARN from YAML config or SSM."""
    # Try local YAML first
    path = os.path.normpath(config_path)
    if os.path.exists(path):
        try:
            with open(path) as f:
                cfg = yaml.safe_load(f)
            default_agent = cfg.get("default_agent", "")
            agents = cfg.get("agents", {})
            agent_cfg = agents.get(default_agent, {})
            arn = agent_cfg.get("bedrock_agentcore", {}).get("agent_arn")
            if arn:
                return arn
        except Exception:
            pass

    # Fallback to SSM
    return get_ssm_parameter(f"{ssm_prefix}/agent_runtime_arn")


# ---------------------------------------------------------------------------
# AgentCore invocation (streaming SSE)
# ---------------------------------------------------------------------------
def invoke_agent(agent_arn: str, token: str, session_id: str, prompt: str):
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

    try:
        resp = requests.post(
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

    except requests.exceptions.Timeout:
        yield "Request timed out (5 min limit)."
    except requests.exceptions.ConnectionError:
        yield "Connection error. Is the agent runtime running?"
    except Exception as e:
        yield f"Error: {e}"


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
def _key(base: str) -> str:
    """Return a session state key scoped to the current agent."""
    return f"{st.session_state.active_agent}_{base}"


def _ensure_agent_state():
    """Initialize per-agent session state if not present."""
    for field, default_fn in [
        ("messages", list),
        ("session_id", lambda: str(uuid.uuid4())),
        ("token", lambda: None),
        ("token_ts", lambda: 0),
        ("agent_arn", lambda: None),
    ]:
        k = _key(field)
        if k not in st.session_state:
            st.session_state[k] = default_fn()


# ---------------------------------------------------------------------------
# Streamlit App
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="NetAIOps Agent Hub",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Global session state
if "active_agent" not in st.session_state:
    st.session_state.active_agent = "k8s"
if "model_id" not in st.session_state:
    st.session_state.model_id = MODELS[0][0]
if "scenario_prompt" not in st.session_state:
    st.session_state.scenario_prompt = None

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🤖 NetAIOps Agent Hub")

    # Agent selector
    agent_keys = list(AGENTS.keys())
    agent_labels = [f"{AGENTS[k]['icon']} {AGENTS[k]['name']}" for k in agent_keys]
    selected_idx = st.radio(
        "에이전트 선택",
        range(len(agent_keys)),
        format_func=lambda i: agent_labels[i],
        index=agent_keys.index(st.session_state.active_agent),
        key="agent_selector",
    )
    new_agent = agent_keys[selected_idx]
    if new_agent != st.session_state.active_agent:
        st.session_state.active_agent = new_agent
        st.session_state.scenario_prompt = None
        st.rerun()

    _ensure_agent_state()
    agent_cfg = AGENTS[st.session_state.active_agent]

    st.divider()

    # Model selector
    model_labels = [label for _, label in MODELS]
    idx = st.selectbox("Model", range(len(MODELS)), format_func=lambda i: model_labels[i])
    st.session_state.model_id = MODELS[idx][0]
    st.caption(f"`{st.session_state.model_id}`")

    st.divider()

    # Agent ARN (auto-discovered or manual override)
    current_arn = st.session_state[_key("agent_arn")]
    if not current_arn:
        current_arn = get_agent_arn(agent_cfg["config_path"], agent_cfg["ssm_prefix"])
        if current_arn:
            st.session_state[_key("agent_arn")] = current_arn

    arn_input = st.text_input(
        "Agent Runtime ARN",
        value=current_arn or "",
        help="Auto-discovered from config. Override if needed.",
        key=f"arn_input_{st.session_state.active_agent}",
    )
    if arn_input:
        st.session_state[_key("agent_arn")] = arn_input

    st.divider()

    # Token status
    token = st.session_state[_key("token")]
    token_ts = st.session_state[_key("token_ts")]
    token_age = time.time() - token_ts if token else 0
    token_valid = token and token_age < 3500

    if token_valid:
        remaining = int(3600 - token_age)
        st.success(f"Token valid ({remaining // 60}m {remaining % 60}s remaining)")
    else:
        st.warning("No valid token")

    if st.button("Refresh Token", use_container_width=True, key="refresh_token"):
        with st.spinner("Fetching M2M token..."):
            tok = get_m2m_access_token(agent_cfg["ssm_prefix"])
            if tok:
                st.session_state[_key("token")] = tok
                st.session_state[_key("token_ts")] = time.time()
                st.success("Token refreshed")
                st.rerun()
            else:
                st.error("Failed to get token. Check SSM parameters and Cognito config.")

    st.divider()

    # Scenario buttons (agent-specific)
    if agent_cfg["scenarios"]:
        st.subheader("테스트 시나리오")
        for name, prompt in agent_cfg["scenarios"].items():
            if st.button(name, use_container_width=True, key=f"scenario_{name}"):
                st.session_state.scenario_prompt = prompt
                st.rerun()
        st.divider()

    # Session info
    st.caption(f"Session: `{st.session_state[_key('session_id')][:8]}...`")
    st.caption(f"Region: `{AGENT_REGION}`")
    st.caption(f"Messages: {len(st.session_state[_key('messages')])}")

    if st.button("New Conversation", use_container_width=True, key="new_conv"):
        st.session_state[_key("messages")] = []
        st.session_state[_key("session_id")] = str(uuid.uuid4())
        st.rerun()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title(f"{agent_cfg['icon']} {agent_cfg['name']}")
st.caption(agent_cfg["description"])

# ---------------------------------------------------------------------------
# Auto-acquire token on first load
# ---------------------------------------------------------------------------
token = st.session_state[_key("token")]
token_ts = st.session_state[_key("token_ts")]
token_age = time.time() - token_ts if token else 0

if not token or token_age >= 3500:
    with st.spinner("Acquiring authentication token..."):
        tok = get_m2m_access_token(agent_cfg["ssm_prefix"])
        if tok:
            st.session_state[_key("token")] = tok
            st.session_state[_key("token_ts")] = time.time()
        else:
            st.warning(
                "Could not auto-acquire token. "
                "Click **Refresh Token** in the sidebar after verifying SSM parameters."
            )

# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------
for msg in st.session_state[_key("messages")]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------
# Check for scenario prompt first
scenario_prompt = st.session_state.get("scenario_prompt")
if scenario_prompt:
    st.session_state.scenario_prompt = None
    prompt = scenario_prompt
else:
    prompt = st.chat_input(agent_cfg["placeholder"])

if prompt:
    agent_arn = st.session_state[_key("agent_arn")]
    token = st.session_state[_key("token")]

    if not agent_arn:
        st.error("Agent Runtime ARN is not set. Configure it in the sidebar.")
        st.stop()

    if not token:
        st.error("No authentication token. Click **Refresh Token** in the sidebar.")
        st.stop()

    # Show user message
    st.session_state[_key("messages")].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Stream agent response
    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""

        for chunk in invoke_agent(
            agent_arn=agent_arn,
            token=token,
            session_id=st.session_state[_key("session_id")],
            prompt=prompt,
        ):
            full_response += chunk
            placeholder.markdown(full_response + "▌")

        placeholder.markdown(full_response)

    st.session_state[_key("messages")].append({"role": "assistant", "content": full_response})
