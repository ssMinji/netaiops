"""
Incident Chat Frontend - AgentCore Client
인시던트 채팅 프론트엔드 - AgentCore 클라이언트
"""
import json
import uuid
import urllib.parse
from typing import Optional, Dict, Any
import requests

class AgentCoreClient:
    def __init__(self, agent_runtime_arn: str, region: str, auth_token: str = None, timeout: int = 120):
        self.agent_runtime_arn = agent_runtime_arn
        self.region = region
        self.auth_token = auth_token
        self.timeout = timeout

    def _get_api_url(self) -> str:
        escaped_agent_arn = urllib.parse.quote(self.agent_runtime_arn, safe="")
        return f"https://bedrock-agentcore.{self.region}.amazonaws.com/runtimes/{escaped_agent_arn}/invocations?qualifier=DEFAULT"

    def _get_headers(self, session_id: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
        }

    def create_conversation(self, user_id: str) -> str:
        return str(uuid.uuid4())

    def send_message(self, conversation_id, message, model=None, user_id=None):
        try:
            url = self._get_api_url()
            headers = self._get_headers(conversation_id)
            payload = {"input": {"prompt": message, "conversation_id": conversation_id, "jwt_token": self.auth_token}}
            if user_id:
                payload["input"]["user_id"] = user_id
                payload["input"]["actor_id"] = user_id
            if model:
                payload["input"]["model_id"] = model
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=self.timeout)
            if response.status_code == 200:
                result = response.json()
                output = result.get("output", {})
                response_text = output.get("message", "") or output.get("response", "")
                tools_used = output.get("tools_used", [])
                if isinstance(tools_used, str):
                    tools_used = [t.strip() for t in tools_used.split(",") if t.strip()]
                return {"response": response_text or "응답을 받지 못했습니다.", "status": "success", "tools_used": tools_used, "metadata": output.get("metadata", {})}
            else:
                error_detail = ""
                try:
                    error_detail = response.json().get("message", response.text)
                except:
                    error_detail = response.text
                return {"response": f"오류 발생 ({response.status_code}): {error_detail}", "status": "error", "tools_used": [], "metadata": {"error_code": response.status_code}}
        except requests.exceptions.Timeout:
            return {"response": f"요청 시간 초과 ({self.timeout}초)", "status": "error", "tools_used": [], "metadata": {"error": "timeout"}}
        except requests.exceptions.ConnectionError as e:
            return {"response": f"연결 오류: AgentCore Runtime에 연결할 수 없습니다.", "status": "error", "tools_used": [], "metadata": {"error": str(e)}}
        except Exception as e:
            return {"response": f"오류 발생: {str(e)}", "status": "error", "tools_used": [], "metadata": {"error": str(e)}}
