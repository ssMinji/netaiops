"""
Configuration component for incident chat.
인시던트 채팅 설정 컴포넌트.
"""
import streamlit as st

def render_agentcore_config():
    with st.expander("AgentCore 설정", expanded=not st.session_state.get("agent_runtime_arn")):
        arn = st.text_input("Agent Runtime ARN", value=st.session_state.get("agent_runtime_arn", ""), help="bedrock-agentcore list-runtimes 명령으로 확인")
        region = st.selectbox("AWS Region", ["us-east-1", "us-west-2", "ap-northeast-1", "ap-northeast-2", "ap-southeast-1", "eu-west-1"], index=0)
        token = st.text_input("JWT Token", value=st.session_state.get("auth_token", ""), type="password", help="Cognito에서 발급받은 JWT 토큰")

        if arn:
            st.session_state.agent_runtime_arn = arn
            st.session_state.region = region
            st.session_state.auth_token = token
            return True
    return False
