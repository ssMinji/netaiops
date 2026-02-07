"""
NetAIOps Chat Frontend - Chat Components
NetAIOps 채팅 프론트엔드 - 채팅 컴포넌트

This module provides chat UI components including message rendering
and sidebar configuration.
이 모듈은 메시지 렌더링 및 사이드바 설정을 포함한 채팅 UI 컴포넌트를 제공합니다.
"""

import streamlit as st

from models.message import Message
from services.agentcore_client import AgentCoreClient
from typing import Optional

# =============================================================================
# Supported Claude Models for NetAIOps
# NetAIOps용 지원 Claude 모델
# =============================================================================
SUPPORTED_MODELS = [
    ("global.anthropic.claude-opus-4-6-v1", "Claude Opus 4.6 (최신, 최고 성능)"),
    ("global.anthropic.claude-opus-4-5-20251101-v1:0", "Claude Opus 4.5 (고성능)"),
    ("global.anthropic.claude-sonnet-4-20250514-v1:0", "Claude Sonnet 4 (빠른 응답)"),
]


def render_message(message: Message, client: Optional[AgentCoreClient] = None):
    """
    Render a single chat message.
    단일 채팅 메시지 렌더링.

    Args:
        message: Message object to render (렌더링할 메시지 객체)
        client: AgentCore client for feedback submission (피드백 제출용 클라이언트)
    """
    with st.chat_message(message.role, avatar="🧑‍💻" if message.role == "user" else "🤖"):
        st.write(message.content)

        # Add feedback buttons for assistant messages (어시스턴트 메시지에 피드백 버튼 추가)
        if message.role == "assistant" and client:
            unique_id = f"{message.timestamp.isoformat()}_{hash(message.content)}"
            message_id = str(message.metadata.get("message_id", unique_id))

            # Check if feedback already given (이미 피드백이 제출되었는지 확인)
            feedback_key = f"feedback_given_{message_id}"
            if feedback_key not in st.session_state:
                st.session_state[feedback_key] = False

            if not st.session_state[feedback_key]:
                st.markdown("---")
                st.markdown("**응답이 도움이 되었나요?**")

                col1, col2, col3 = st.columns([2, 2, 6])

                with col1:
                    if st.button(
                        "👍 도움됨",
                        key=f"up_{message_id}",
                        use_container_width=True,
                    ):
                        if client.submit_feedback(
                            message_id,
                            st.session_state.get("conversation_id", "default"),
                            1.0,
                            "Helpful",
                        ):
                            st.session_state[feedback_key] = True
                            st.success("✓ 피드백 감사합니다!")
                            st.rerun()

                with col2:
                    if st.button(
                        "👎 개선 필요",
                        key=f"down_{message_id}",
                        use_container_width=True,
                    ):
                        st.session_state[f"show_feedback_form_{message_id}"] = True
                        st.rerun()

                # Show feedback form if requested (요청 시 피드백 폼 표시)
                if st.session_state.get(f"show_feedback_form_{message_id}", False):
                    feedback_text = st.text_area(
                        "개선 사항을 알려주세요:",
                        key=f"feedback_text_{message_id}",
                        placeholder="어떤 부분이 개선되면 좋을까요?",
                        height=80,
                    )
                    col_submit, col_cancel = st.columns([1, 1])
                    with col_submit:
                        if st.button("제출", key=f"submit_{message_id}", type="primary"):
                            if client.submit_feedback(
                                message_id,
                                st.session_state.get("conversation_id", "default"),
                                0.0,
                                feedback_text,
                            ):
                                st.session_state[feedback_key] = True
                                st.session_state[f"show_feedback_form_{message_id}"] = False
                                st.success("✓ 피드백 감사합니다!")
                                st.rerun()
                    with col_cancel:
                        if st.button("취소", key=f"cancel_{message_id}"):
                            st.session_state[f"show_feedback_form_{message_id}"] = False
                            st.rerun()
            else:
                st.markdown(
                    "<div style='color: #28a745; font-size: 0.9em;'>✓ 피드백 제출됨</div>",
                    unsafe_allow_html=True,
                )

        # Show tool calls if available (사용된 도구 표시)
        if message.metadata and "tools_used" in message.metadata:
            tools_str = message.metadata["tools_used"]
            if tools_str:
                tools_used = [tool.strip() for tool in tools_str.split(",") if tool.strip()]
                if tools_used:
                    st.markdown("**🔧 사용된 도구:**")
                    for tool in tools_used:
                        st.markdown(f"• `{tool}`")

        # Show metadata if available (메타데이터 표시)
        if message.metadata:
            with st.expander("상세 정보", expanded=False):
                st.json(message.metadata)


def render_sidebar():
    """
    Render sidebar with model selection and conversation controls.
    모델 선택 및 대화 제어가 포함된 사이드바 렌더링.

    Returns:
        str: Selected model ID (선택된 모델 ID)
    """
    with st.sidebar:
        st.divider()
        st.header("🤖 모델 선택")

        # Model selection (모델 선택)
        model_options = [m[0] for m in SUPPORTED_MODELS]
        model_labels = [m[1] for m in SUPPORTED_MODELS]

        selected_index = st.selectbox(
            "Claude 모델",
            options=range(len(SUPPORTED_MODELS)),
            format_func=lambda i: model_labels[i],
            index=0,
            help="분석에 사용할 Claude 모델을 선택하세요",
        )
        model = model_options[selected_index]

        # Show model info (모델 정보 표시)
        st.caption(f"Model ID: `{model[:40]}...`")

        st.divider()
        st.header("💬 대화 관리")

        # User ID (사용자 ID)
        user_id = st.text_input(
            "사용자 ID",
            value=st.session_state.user_id,
            help="대화 기록 추적용 사용자 ID",
        )
        st.session_state.user_id = user_id

        # Conversation controls (대화 제어)
        if st.button("🆕 새 대화 시작", type="primary", use_container_width=True):
            st.session_state.conversation_id = None
            st.session_state.messages = []
            st.rerun()

        if st.session_state.conversation_id:
            st.success(f"대화 ID: {st.session_state.conversation_id[:8]}...")
            st.caption(f"메시지 수: {len(st.session_state.messages)}")

        # Export conversation (대화 내보내기)
        st.divider()
        if st.session_state.messages:
            if st.button("📥 대화 내보내기", use_container_width=True):
                export_data = {
                    "conversation_id": st.session_state.conversation_id,
                    "user_id": st.session_state.user_id,
                    "messages": [
                        {
                            "role": m.role,
                            "content": m.content,
                            "timestamp": m.timestamp.isoformat(),
                            "metadata": m.metadata,
                        }
                        for m in st.session_state.messages
                    ],
                }
                import json
                st.download_button(
                    "💾 JSON 다운로드",
                    data=json.dumps(export_data, ensure_ascii=False, indent=2),
                    file_name=f"netaiops_chat_{st.session_state.conversation_id[:8]}.json",
                    mime="application/json",
                    use_container_width=True,
                )

        return model
