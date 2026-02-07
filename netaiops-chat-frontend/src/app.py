"""
NetAIOps Chat Frontend - Main Streamlit Application
NetAIOps 채팅 프론트엔드 - 메인 Streamlit 애플리케이션

This application provides a chat interface for interacting with
NetAIOps AgentCore Runtime agents for network troubleshooting.
이 애플리케이션은 네트워크 트러블슈팅을 위한 NetAIOps AgentCore
Runtime 에이전트와 상호작용하는 채팅 인터페이스를 제공합니다.
"""

import uuid
from datetime import datetime

import streamlit as st

from components.chat import render_message, render_sidebar
from components.config import render_agentcore_config
from models.message import Message
from services.agentcore_client import AgentCoreClient


def init_session_state():
    """
    Initialize session state variables.
    세션 상태 변수 초기화.
    """
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "user_id" not in st.session_state:
        st.session_state.user_id = f"user_{str(uuid.uuid4())[:8]}"
    if "agent_runtime_arn" not in st.session_state:
        st.session_state.agent_runtime_arn = ""
    if "region" not in st.session_state:
        st.session_state.region = "ap-northeast-2"
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = ""


def main():
    """
    Main application entry point.
    메인 애플리케이션 진입점.
    """
    st.set_page_config(
        page_title="NetAIOps Chat",
        page_icon="🌐",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS for better design (향상된 디자인을 위한 커스텀 CSS)
    st.markdown(
        """
    <style>
    .stButton > button {
        border-radius: 20px;
        border: 1px solid #e0e0e0;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .feedback-section {
        background-color: #f8f9fa;
        padding: 10px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .main-header {
        background: linear-gradient(90deg, #1a5f7a 0%, #159895 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: bold;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    st.markdown('<p class="main-header">NetAIOps Chat</p>', unsafe_allow_html=True)
    st.caption("AWS Bedrock AgentCore 기반 네트워크 AI 트러블슈팅")

    init_session_state()

    # Render configuration (설정 렌더링)
    config_valid = render_agentcore_config()
    model = render_sidebar()

    # Initialize client based on configuration (설정에 따라 클라이언트 초기화)
    if config_valid:
        auth_token = st.session_state.get("auth_token", "")
        client = AgentCoreClient(
            agent_runtime_arn=st.session_state.agent_runtime_arn,
            region=st.session_state.region,
            auth_token=auth_token,
        )
        if auth_token:
            st.success("🚀 AgentCore Runtime 연결됨")
        else:
            st.warning("⚠️ JWT 토큰이 필요합니다")
    else:
        client = None
        st.error("⚠️ AgentCore 설정을 완료해주세요")

    # Display chat messages (채팅 메시지 표시)
    for message in st.session_state.messages:
        render_message(message, client)

    # Chat input (채팅 입력)
    if prompt := st.chat_input("메시지를 입력하세요... (예: DNS 조회 실패 원인 분석)"):
        if not config_valid or not client:
            st.error("AgentCore 설정을 먼저 완료해주세요")
            return

        # Generate new conversation ID if needed (필요시 새 대화 ID 생성)
        if not st.session_state.conversation_id:
            st.session_state.conversation_id = str(uuid.uuid4())

        # Add user message (사용자 메시지 추가)
        user_message = Message(role="user", content=prompt, timestamp=datetime.now())
        st.session_state.messages.append(user_message)
        render_message(user_message)

        # Send message and get response (메시지 전송 및 응답 수신)
        with st.spinner("분석 중..."):
            response = client.send_message(
                st.session_state.conversation_id,
                prompt,
                model,
                st.session_state.user_id,
            )

            if response:
                # Add assistant message (어시스턴트 메시지 추가)
                metadata = {
                    "model": model,
                    "status": response.get("status", "success"),
                }

                # Add tools_used to metadata if available (도구 사용 정보 추가)
                if "tools_used" in response and response["tools_used"]:
                    metadata["tools_used"] = ",".join(response["tools_used"])

                # Add all metadata from API response (API 응답의 모든 메타데이터 추가)
                if "metadata" in response and response["metadata"]:
                    metadata.update(response["metadata"])

                assistant_message = Message(
                    role="assistant",
                    content=response.get("response", response.get("message", "")),
                    timestamp=datetime.now(),
                    metadata=metadata,
                )
                st.session_state.messages.append(assistant_message)
                render_message(assistant_message, client)

        st.rerun()


if __name__ == "__main__":
    main()
