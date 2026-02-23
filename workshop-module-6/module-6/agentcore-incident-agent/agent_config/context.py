from contextvars import ContextVar
from typing import Optional
import asyncio

class IncidentContext:
    _gateway_token: Optional[str] = None
    _response_queue: Optional[asyncio.Queue] = None
    _agent: Optional[object] = None
    _gateway_token_ctx: ContextVar[Optional[str]] = ContextVar("gateway_token", default=None)
    _response_queue_ctx: ContextVar[Optional[asyncio.Queue]] = ContextVar("response_queue", default=None)
    _agent_ctx: ContextVar[Optional[object]] = ContextVar("agent", default=None)

    @classmethod
    def get_response_queue_ctx(cls) -> Optional[asyncio.Queue]:
        if cls._response_queue:
            return cls._response_queue
        try:
            return cls._response_queue_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_response_queue_ctx(cls, queue: asyncio.Queue) -> None:
        cls._response_queue = queue
        cls._response_queue_ctx.set(queue)

    @classmethod
    def get_gateway_token_ctx(cls) -> Optional[str]:
        if cls._gateway_token:
            return cls._gateway_token
        try:
            return cls._gateway_token_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_gateway_token_ctx(cls, token: str) -> None:
        cls._gateway_token = token
        cls._gateway_token_ctx.set(token)

    @classmethod
    def get_agent_ctx(cls) -> Optional[object]:
        if cls._agent:
            return cls._agent
        try:
            return cls._agent_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_agent_ctx(cls, agent: object) -> None:
        cls._agent = agent
        cls._agent_ctx.set(agent)
