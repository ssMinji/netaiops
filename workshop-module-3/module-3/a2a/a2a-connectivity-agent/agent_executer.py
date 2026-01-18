import logging
import boto3
import time
import json
import asyncio
from typing import Any, Dict, Optional

import httpx

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils.errors import ServerError

from utils import get_token  # reuses your existing token helper

logger = logging.getLogger(__name__)


class _OAuthTokenCache:
    """Simple in-process bearer token cache."""
    def __init__(self) -> None:
        self.token: Optional[str] = None
        self.expire_epoch: float = 0.0

    def valid(self, now_ts: float) -> bool:
        # refresh 30s before expiry
        return self.token is not None and now_ts < (self.expire_epoch - 30)

    def set(self, token: str, expires_in: int, now_ts: float) -> None:
        import time
        base = now_ts or time.time()
        self.token = token
        self.expire_epoch = base + max(1, int(expires_in))


class ConnectivityTroubleshootingAgentCoreExecutor(AgentExecutor):
    """
    A2A executor that fronts a Bedrock AgentCore Runtime (Connectivity Troubleshooting agent)
    via an AgentCore Gateway protected by a Cognito-backed custom JWT authorizer.

    It mirrors the life-cycle behavior of your Kaitlyn executor:
    - submit/start_work
    - stream or single-shot invoke
    - update working/input_required/complete
    - attach final artifact
    """

    def __init__(
        self,
        *,
        base_url: str,
        agent_arn: str,
        agent_session_id: str,
        user_pool_id: str,
        client_id: str,
        client_secret: str,
        scope: str,
        discovery_url: str,
        identity_provider,
        request_timeout_s: int = 900,  # 15 minutes timeout for AgentCore requests
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_arn = agent_arn
        self.agent_session_id = agent_session_id

        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.discovery_url = discovery_url

        self.identity_provider = identity_provider
        # Configure HTTP client with extended timeouts for AgentCore
        self.http = httpx.Client(
            timeout=httpx.Timeout(
                connect=10.0,  # Connection timeout
                read=request_timeout_s,  # Read timeout (15 minutes)
                write=30.0,  # Write timeout
                pool=10.0   # Pool timeout
            ),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            http2=True,  # Enable HTTP/2 for better performance
            follow_redirects=True  # Follow redirects automatically
        )
        self._token_cache = _OAuthTokenCache()

    def _build_agent_url(self, qualifier: str = "DEFAULT") -> str:
        """Build the AgentCore invocation URL similar to the working example"""
        import urllib.parse
        endpoint = f"https://bedrock-agentcore.{boto3.session.Session().region_name}.amazonaws.com"
        escaped_agent_arn = urllib.parse.quote(self.agent_arn, safe='')
        print(f"This is the escaped agent arn: {escaped_agent_arn}")
        return f"{endpoint}/runtimes/{escaped_agent_arn}/invocations?qualifier={qualifier}"

    def _bearer(self) -> str:
        now_ts = time.time()
        logger.debug(f"Checking token cache validity at {now_ts}")
        
        if self._token_cache.valid(now_ts):
            logger.debug("Using cached token")
            return self._token_cache.token  # type: ignore

        logger.info("Fetching new OAuth token")
        logger.debug(f"OAuth configuration:")
        logger.debug(f"  user_pool_id: {self.user_pool_id}")
        logger.debug(f"  client_id: {self.client_id}")
        logger.debug(f"  client_secret: {'*' * (len(self.client_secret) - 4) + self.client_secret[-4:] if self.client_secret else 'None'}")
        logger.debug(f"  scope: {self.scope}")
        logger.debug(f"  discovery_url: {self.discovery_url}")
        
        token_start = time.time()
        
        tok = get_token(
            user_pool_id=self.user_pool_id,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scope_string=self.scope,
            discovery_url=self.discovery_url
        )
        
        token_duration = time.time() - token_start
        logger.info(f"Token fetch completed in {token_duration:.2f}s")
        logger.debug(f"Token response keys: {list(tok.keys())}")
        
        if "access_token" not in tok:
            logger.error("Token fetch failed: %s", {k: tok.get(k) for k in ("error", "error_description")})
            logger.error(f"Full token response: {json.dumps(tok, indent=2)}")
            raise ServerError(error=InternalError())
            
        self._token_cache.set(tok["access_token"], int(tok.get("expires_in", 1800)), now_ts)
        logger.debug("Token cached successfully")
        return tok["access_token"]

    def _invoke_json(self, payload: Dict[str, Any], headers: Dict[str, str]) -> str:
        agent_url = self._build_agent_url()
        logger.info(f"Making request to {agent_url}")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
        logger.debug(f"Request headers: {headers}")
        
        request_start = time.time()
        resp = self.http.post(agent_url, json=payload, headers=headers)
        request_duration = time.time() - request_start
        
        logger.info(f"Request completed in {request_duration:.2f}s with status {resp.status_code}")
        logger.debug(f"Response headers: {dict(resp.headers)}")
        logger.debug(f"Response content length: {len(resp.content)}")
        
        # Check if response is successful
        resp.raise_for_status()
        
        # Get response content
        response_text = resp.text.strip() if resp.text else ""
        content_type = resp.headers.get('content-type', '').lower()
        
        logger.debug(f"Content-Type: {content_type}")
        logger.debug(f"Response text length: {len(response_text)}")
        logger.debug(f"Response text preview: {response_text[:200]}...")
        
        # Handle empty response
        if not response_text:
            logger.warning("Empty response received from AgentCore API")
            error_msg = f"Empty response from agent (Status: {resp.status_code})"
            if resp.headers:
                error_msg += f", Headers: {dict(resp.headers)}"
            return error_msg
        
        # Try to parse as JSON first
        try:
            response_data = resp.json()
            logger.debug(f"Successfully parsed JSON response")
            
            # Extract meaningful content from JSON response
            if isinstance(response_data, dict):
                # Look for common response fields
                content = (
                    response_data.get("response") or 
                    response_data.get("text") or 
                    response_data.get("output") or
                    response_data.get("result") or
                    response_data.get("message") or
                    str(response_data)
                )
                return content
            return str(response_data)
            
        except json.JSONDecodeError as e:
            # If not JSON, treat as plain text (streaming response)
            logger.debug(f"Response is not JSON (error: {e}), treating as text")
            return response_text
        except Exception as e:
            logger.error(f"Unexpected error parsing response: {e}")
            return f"Error parsing response: {e}. Raw response: {response_text[:500]}"


    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        if not context.task_id or not context.context_id:
            raise ValueError("RequestContext must have task_id and context_id")
        if not context.message:
            raise ValueError("RequestContext must have a message")

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        if not context.current_task:
            await updater.submit()
        await updater.start_work()

        user_text = context.get_user_input()
        payload: Dict[str, Any] = {
            "prompt": user_text,
            "actor_id": f"user-{context.context_id}"  # Generate actor_id from context
        }

        try:
            bearer = self._bearer()
            headers = {
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json",
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": self.agent_session_id,
                "X-Amzn-Trace-Id": f"a2a-task-{context.task_id}",
                # helpful for cross-system trace joins:
                "x-correlation-id": f"{context.task_id}:{context.context_id}",
                "x-a2a-context-id": context.context_id,
            }

            # Single-shot call only
            content = self._invoke_json(payload, headers)
            logger.debug(f"Response content type: {type(content)}")
            logger.debug(f"Response content: {content}")
            logger.info(f"Response received: {content}")
            
            parts = [Part(root=TextPart(text=content))]
            await updater.add_artifact(parts, name="connectivity_troubleshooting_result")
            await updater.complete()
            logger.info(f"Task completed with response: {content}")

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            try:
                # For streaming responses, we need to read the content first
                if hasattr(e.response, 'content') and e.response.content:
                    body_preview = e.response.content.decode('utf-8', errors='ignore')[:512]
                else:
                    # Try to read the response if it's available
                    body_preview = str(e.response.text)[:512] if hasattr(e.response, 'text') else "No response body"
            except Exception as ex:
                # If we can't read the response, use status and headers
                body_preview = f"Status: {status}, Headers: {dict(e.response.headers)}, Read error: {str(ex)}"
            
            logger.error("AgentCore HTTP %s: %s", status, body_preview)
            logger.error(f"Request URL: {e.request.url}")
            logger.error(f"Request headers: {dict(e.request.headers)}")
            
            if 400 <= status < 500:
                raise ServerError(error=UnsupportedOperationError()) from e
            raise ServerError(error=InternalError()) from e
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"This error should now be handled in _invoke_json method")
            raise ServerError(error=InternalError()) from e
        except Exception as e:
            logger.exception("ConnectivityTroubleshootingAgentCoreExecutor failed")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception message: {str(e)}")
            raise ServerError(error=InternalError()) from e

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        _ = context, event_queue  # Unused but required by interface
        raise ServerError(error=UnsupportedOperationError())
