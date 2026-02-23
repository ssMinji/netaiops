"""
Chat display components for incident analysis.
인시던트 분석 채팅 표시 컴포넌트.
"""
import streamlit as st

def render_message(message, client=None):
    with st.chat_message(message.role):
        st.markdown(message.content)
        if message.metadata:
            tools = message.metadata.get("tools_used", "")
            if tools:
                tool_list = tools.split(",") if isinstance(tools, str) else tools
                st.caption(f"사용된 도구: {', '.join(tool_list)}")

def render_sidebar():
    with st.sidebar:
        st.header("설정")
        model = st.selectbox("모델 선택", [
            "global.anthropic.claude-opus-4-6-v1",
            "global.anthropic.claude-opus-4-5-20251101-v1:0",
            "global.anthropic.claude-sonnet-4-20250514-v1:0",
        ], format_func=lambda x: {"global.anthropic.claude-opus-4-6-v1": "Claude Opus 4.6 (Latest)", "global.anthropic.claude-opus-4-5-20251101-v1:0": "Claude Opus 4.5", "global.anthropic.claude-sonnet-4-20250514-v1:0": "Claude Sonnet 4 (Fast)"}[x])

        st.divider()
        st.subheader("테스트 시나리오")
        scenarios = {
            "CPU 급증 분석": "서비스 web-api의 CPU 사용률이 90%를 넘었습니다. 원인을 분석해주세요.",
            "에러율 증가": "지난 1시간 동안 payment 서비스의 에러율이 5%를 초과했습니다. 로그와 메트릭을 분석해주세요.",
            "지연 시간 급증": "API 응답 지연이 P99 기준 2초를 넘었습니다. APM 트레이스와 컨테이너 상태를 확인해주세요.",
            "파드 재시작 반복": "EKS 클러스터에서 checkout-service 파드가 반복적으로 재시작됩니다. 진단해주세요.",
        }
        for name, prompt in scenarios.items():
            if st.button(name, use_container_width=True):
                st.session_state.scenario_prompt = prompt

        st.divider()
        if st.button("대화 초기화", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_id = None
            st.rerun()

        return model
