"""
NetAIOps Chat Frontend - AgentCore Configuration Component
NetAIOps 채팅 프론트엔드 - AgentCore 설정 컴포넌트

This module provides the configuration UI for connecting to
AWS Bedrock AgentCore Runtime.
이 모듈은 AWS Bedrock AgentCore Runtime 연결을 위한 설정 UI를 제공합니다.
"""

import streamlit as st

# =============================================================================
# Supported Regions (Bedrock AgentCore Available Regions)
# 지원 리전 (Bedrock AgentCore 사용 가능 리전)
# =============================================================================
SUPPORTED_REGIONS = [
    "ap-northeast-2",  # Seoul (서울) - Default
    "us-east-1",       # N. Virginia (버지니아 북부)
    "us-west-2",       # Oregon (오레곤)
    "eu-west-1",       # Ireland (아일랜드)
    "ap-northeast-1",  # Tokyo (도쿄)
    "ap-southeast-1",  # Singapore (싱가포르)
]

# =============================================================================
# Supported Agent Types
# 지원 에이전트 유형
# =============================================================================
AGENT_TYPES = {
    "troubleshooting": "Troubleshooting Agent (연결성 진단)",
    "performance": "Performance Agent (성능 분석)",
    "collaborator": "Collaborator Agent (멀티 에이전트 협업)",
}


def render_agentcore_config():
    """
    Render AgentCore configuration in sidebar.
    사이드바에 AgentCore 설정 렌더링.

    Returns:
        bool: True if configuration is valid, False otherwise
              설정이 유효하면 True, 아니면 False
    """
    with st.sidebar:
        st.header("⚙️ AgentCore 설정")

        # Agent Runtime ARN (에이전트 런타임 ARN)
        st.subheader("1. Agent Runtime ARN")
        agent_runtime_arn = st.text_input(
            "Runtime ARN",
            value=st.session_state.get("agent_runtime_arn", ""),
            placeholder="arn:aws:bedrock-agentcore:region:account:runtime/agent-id",
            help="배포된 AgentCore Runtime의 ARN을 입력하세요",
        )
        st.session_state.agent_runtime_arn = agent_runtime_arn

        # Show ARN format hint (ARN 형식 힌트 표시)
        with st.expander("ARN 형식 예시", expanded=False):
            st.code(
                "arn:aws:bedrock-agentcore:ap-northeast-2:123456789012:runtime/my-agent-abc123",
                language="text",
            )
            st.caption("bedrock-agentcore list-runtimes 명령으로 확인 가능")

        # Region Selection (리전 선택)
        st.subheader("2. AWS 리전")

        # Get current region index (현재 리전 인덱스 가져오기)
        current_region = st.session_state.get("region", "ap-northeast-2")
        try:
            region_index = SUPPORTED_REGIONS.index(current_region)
        except ValueError:
            region_index = 0

        region = st.selectbox(
            "리전 선택",
            options=SUPPORTED_REGIONS,
            index=region_index,
            format_func=lambda x: f"{x} {'(서울, 기본값)' if x == 'ap-northeast-2' else ''}",
        )
        st.session_state.region = region

        # JWT Auth Token (JWT 인증 토큰)
        st.subheader("3. 인증 토큰")
        auth_token = st.text_input(
            "JWT Token",
            value=st.session_state.get("auth_token", ""),
            type="password",
            placeholder="Cognito JWT 토큰 입력",
            help="Cognito User Pool에서 발급받은 JWT 토큰",
        )
        st.session_state.auth_token = auth_token

        # Token generation hint (토큰 생성 힌트)
        with st.expander("토큰 발급 방법", expanded=False):
            st.markdown("""
            **AWS CLI로 토큰 발급:**
            ```bash
            aws cognito-idp initiate-auth \\
              --auth-flow USER_PASSWORD_AUTH \\
              --client-id <client_id> \\
              --auth-parameters \\
                USERNAME=<username>,PASSWORD=<password>
            ```

            **SSM Parameter에서 확인:**
            ```bash
            aws ssm get-parameter \\
              --name "/a2a/app/performance/agentcore/netaiops-cognito/machine_client_id" \\
              --query "Parameter.Value" --output text
            ```
            """)

        # Validation (유효성 검사)
        st.divider()

        config_valid = True

        if not agent_runtime_arn.strip():
            st.error("⚠️ Agent Runtime ARN을 입력하세요")
            config_valid = False
        elif not agent_runtime_arn.startswith("arn:aws:bedrock-agentcore:"):
            st.warning("⚠️ ARN 형식을 확인하세요")
            config_valid = False

        if not auth_token.strip():
            st.error("⚠️ JWT 토큰을 입력하세요")
            config_valid = False

        if config_valid:
            st.success("✅ 설정 완료")

        return config_valid
