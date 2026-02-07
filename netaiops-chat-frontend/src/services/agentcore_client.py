"""
NetAIOps Chat Frontend - AgentCore Client
NetAIOps 채팅 프론트엔드 - AgentCore 클라이언트

This module provides a client for interacting with AWS Bedrock AgentCore Runtime.
이 모듈은 AWS Bedrock AgentCore Runtime과 상호작용하기 위한 클라이언트를 제공합니다.
"""

import json
import uuid
import urllib.parse
from typing import Optional, Dict, Any

import requests


class AgentCoreClient:
    """
    Client for AWS Bedrock AgentCore Runtime.
    AWS Bedrock AgentCore Runtime 클라이언트.

    This client handles communication with deployed AgentCore Runtime agents
    for network troubleshooting and performance analysis.
    이 클라이언트는 네트워크 트러블슈팅 및 성능 분석을 위해 배포된
    AgentCore Runtime 에이전트와의 통신을 처리합니다.
    """

    def __init__(
        self,
        agent_runtime_arn: str,
        region: str,
        auth_token: str = None,
        timeout: int = 120,
    ):
        """
        Initialize AgentCore client.
        AgentCore 클라이언트 초기화.

        Args:
            agent_runtime_arn: ARN of the deployed AgentCore Runtime
                              배포된 AgentCore Runtime의 ARN
            region: AWS region where the runtime is deployed
                   런타임이 배포된 AWS 리전
            auth_token: JWT token for authentication (Cognito)
                       인증용 JWT 토큰 (Cognito)
            timeout: Request timeout in seconds (default: 120)
                    요청 타임아웃 (초, 기본값: 120)
        """
        self.agent_runtime_arn = agent_runtime_arn
        self.region = region
        self.auth_token = auth_token
        self.timeout = timeout

    def _get_api_url(self) -> str:
        """
        Construct the AgentCore API URL.
        AgentCore API URL 구성.

        Returns:
            str: The constructed API URL
        """
        escaped_agent_arn = urllib.parse.quote(self.agent_runtime_arn, safe="")
        return f"https://bedrock-agentcore.{self.region}.amazonaws.com/runtimes/{escaped_agent_arn}/invocations?qualifier=DEFAULT"

    def _get_headers(self, session_id: str) -> Dict[str, str]:
        """
        Get request headers.
        요청 헤더 가져오기.

        Args:
            session_id: Session ID for the conversation

        Returns:
            Dict[str, str]: Request headers
        """
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
        }

    def create_conversation(self, user_id: str) -> str:
        """
        Create a new conversation session.
        새 대화 세션 생성.

        Args:
            user_id: User identifier / 사용자 식별자

        Returns:
            str: New conversation ID / 새 대화 ID
        """
        return str(uuid.uuid4())

    def send_message(
        self,
        conversation_id: str,
        message: str,
        model: str = None,
        user_id: str = None,
    ) -> Dict[str, Any]:
        """
        Send message to AgentCore and get response.
        AgentCore에 메시지를 전송하고 응답을 받습니다.

        Args:
            conversation_id: Current conversation ID / 현재 대화 ID
            message: User message to send / 전송할 사용자 메시지
            model: Model ID to use (optional) / 사용할 모델 ID (선택)
            user_id: User identifier (optional) / 사용자 식별자 (선택)

        Returns:
            Dict[str, Any]: Response containing message and metadata
                           메시지와 메타데이터가 포함된 응답
        """
        try:
            url = self._get_api_url()
            headers = self._get_headers(conversation_id)

            # Construct payload (페이로드 구성)
            payload = {
                "input": {
                    "prompt": message,
                    "conversation_id": conversation_id,
                    "jwt_token": self.auth_token,
                }
            }

            # Add optional parameters (선택적 매개변수 추가)
            if user_id:
                payload["input"]["user_id"] = user_id
                payload["input"]["actor_id"] = user_id

            if model:
                payload["input"]["model_id"] = model

            # Send request (요청 전송)
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload),
                timeout=self.timeout,
            )

            if response.status_code == 200:
                result = response.json()

                # Extract response content (응답 내용 추출)
                output = result.get("output", {})
                response_text = output.get("message", "") or output.get("response", "")

                # Extract tools used (사용된 도구 추출)
                tools_used = output.get("tools_used", [])
                if isinstance(tools_used, str):
                    tools_used = [t.strip() for t in tools_used.split(",") if t.strip()]

                return {
                    "response": response_text or "응답을 받지 못했습니다.",
                    "status": "success",
                    "tools_used": tools_used,
                    "metadata": output.get("metadata", {}),
                }
            else:
                # Handle error response (오류 응답 처리)
                error_detail = ""
                try:
                    error_json = response.json()
                    error_detail = error_json.get("message", response.text)
                except json.JSONDecodeError:
                    error_detail = response.text

                return {
                    "response": f"오류 발생 ({response.status_code}): {error_detail}",
                    "status": "error",
                    "tools_used": [],
                    "metadata": {"error_code": response.status_code},
                }

        except requests.exceptions.Timeout:
            return {
                "response": f"요청 시간 초과 ({self.timeout}초). 다시 시도해주세요.",
                "status": "error",
                "tools_used": [],
                "metadata": {"error": "timeout"},
            }
        except requests.exceptions.ConnectionError as e:
            return {
                "response": f"연결 오류: AgentCore Runtime에 연결할 수 없습니다. 네트워크를 확인하세요.",
                "status": "error",
                "tools_used": [],
                "metadata": {"error": str(e)},
            }
        except Exception as e:
            return {
                "response": f"오류 발생: {str(e)}",
                "status": "error",
                "tools_used": [],
                "metadata": {"error": str(e)},
            }

    def submit_feedback(
        self,
        run_id: str,
        session_id: str,
        score: float,
        comment: str = "",
    ) -> bool:
        """
        Submit feedback for a response.
        응답에 대한 피드백 제출.

        Args:
            run_id: Run/message identifier / 실행/메시지 식별자
            session_id: Session/conversation identifier / 세션/대화 식별자
            score: Feedback score (0.0 = negative, 1.0 = positive)
                   피드백 점수 (0.0 = 부정적, 1.0 = 긍정적)
            comment: Optional feedback comment / 선택적 피드백 코멘트

        Returns:
            bool: True if feedback was submitted successfully
                  피드백이 성공적으로 제출되면 True
        """
        try:
            url = self._get_api_url()
            headers = self._get_headers(session_id)

            payload = {
                "input": {
                    "feedback": {
                        "run_id": run_id,
                        "session_id": session_id,
                        "score": score,
                        "comment": comment,
                    }
                }
            }

            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload),
                timeout=30,
            )

            return response.status_code == 200

        except Exception:
            # Silently fail for feedback (피드백 실패 시 조용히 처리)
            return False

    def health_check(self) -> Dict[str, Any]:
        """
        Check AgentCore Runtime health.
        AgentCore Runtime 상태 확인.

        Returns:
            Dict[str, Any]: Health status information
                           상태 정보
        """
        try:
            # Simple connectivity test (간단한 연결 테스트)
            url = self._get_api_url()
            headers = self._get_headers("health-check")

            # Send minimal request (최소 요청 전송)
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps({"input": {"prompt": "health check"}}),
                timeout=10,
            )

            return {
                "status": "healthy" if response.status_code in [200, 400] else "unhealthy",
                "region": self.region,
                "runtime_arn": self.agent_runtime_arn[:50] + "...",
                "response_code": response.status_code,
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "region": self.region,
                "runtime_arn": self.agent_runtime_arn[:50] + "...",
                "error": str(e),
            }
