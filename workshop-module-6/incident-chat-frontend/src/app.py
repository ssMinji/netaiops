"""
=============================================================================
NetAIOps Incident Analysis - Streamlit Test Frontend (Module 6)
NetAIOps 인시던트 분석 - Streamlit 테스트 프론트엔드 (모듈 6)
=============================================================================

Description (설명):
    Test interface for the Incident Analysis Agent.
    인시던트 분석 에이전트를 위한 테스트 인터페이스입니다.
"""

import uuid
from datetime import datetime

import streamlit as st

from components.chat import render_message, render_sidebar
from components.config import render_agentcore_config
from models.message import Message
from services.agentcore_client import AgentCoreClient


def init_session_state():
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "user_id" not in st.session_state:
        st.session_state.user_id = f"user_{str(uuid.uuid4())[:8]}"
    if "agent_runtime_arn" not in st.session_state:
        st.session_state.agent_runtime_arn = ""
    if "region" not in st.session_state:
        st.session_state.region = "us-east-1"
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = ""
    if "scenario_prompt" not in st.session_state:
        st.session_state.scenario_prompt = None


def main():
    st.set_page_config(page_title="NetAIOps Incident Analysis", page_icon="🔍", layout="wide", initial_sidebar_state="expanded")

    st.markdown("""
    <style>
    .main-header { background: linear-gradient(90deg, #dc3545 0%, #fd7e14 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.5rem; font-weight: bold; }
    .stButton > button { border-radius: 20px; border: 1px solid #e0e0e0; transition: all 0.3s ease; }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<p class="main-header">NetAIOps Incident Analysis</p>', unsafe_allow_html=True)
    st.caption("AI 기반 인시던트 자동 분석 에이전트 테스트 UI")

    init_session_state()
    config_valid = render_agentcore_config()
    model = render_sidebar()

    if config_valid:
        auth_token = st.session_state.get("auth_token", "")
        client = AgentCoreClient(agent_runtime_arn=st.session_state.agent_runtime_arn, region=st.session_state.region, auth_token=auth_token)
        if auth_token:
            st.success("Incident Analysis Agent 연결됨")
        else:
            st.warning("JWT 토큰이 필요합니다")
    else:
        client = None
        st.error("AgentCore 설정을 완료해주세요")

    for message in st.session_state.messages:
        render_message(message, client)

    # Handle scenario prompt from sidebar
    scenario_prompt = st.session_state.get("scenario_prompt")
    if scenario_prompt:
        st.session_state.scenario_prompt = None
        prompt = scenario_prompt
    else:
        prompt = st.chat_input("인시던트 상황을 설명하세요... (예: API 에러율이 5%를 초과했습니다)")

    if prompt:
        if not config_valid or not client:
            st.error("AgentCore 설정을 먼저 완료해주세요")
            return

        if not st.session_state.conversation_id:
            st.session_state.conversation_id = str(uuid.uuid4())

        user_message = Message(role="user", content=prompt, timestamp=datetime.now())
        st.session_state.messages.append(user_message)
        render_message(user_message)

        with st.spinner("인시던트 분석 중..."):
            response = client.send_message(st.session_state.conversation_id, prompt, model, st.session_state.user_id)
            if response:
                metadata = {"model": model, "status": response.get("status", "success")}
                if "tools_used" in response and response["tools_used"]:
                    metadata["tools_used"] = ",".join(response["tools_used"])
                if "metadata" in response and response["metadata"]:
                    metadata.update(response["metadata"])
                assistant_message = Message(role="assistant", content=response.get("response", response.get("message", "")), timestamp=datetime.now(), metadata=metadata)
                st.session_state.messages.append(assistant_message)
                render_message(assistant_message, client)

        st.rerun()


if __name__ == "__main__":
    main()
