from contextvars import ContextVar
from typing import Optional
import asyncio


class IstioContext:
    """Context Manager for Istio Mesh Diagnostics Assistant"""

    # Global state for tokens that persist across agent calls
    _gateway_token: Optional[str] = None
    _response_queue: Optional[asyncio.Queue] = None
    _agent: Optional[object] = None
    _memory_id: Optional[str] = None
    _actor_id: Optional[str] = None
    _session_id: Optional[str] = None

    # Context variables for application state
    _gateway_token_ctx: ContextVar[Optional[str]] = ContextVar(
        "gateway_token", default=None
    )
    _response_queue_ctx: ContextVar[Optional[asyncio.Queue]] = ContextVar(
        "response_queue", default=None
    )
    _agent_ctx: ContextVar[Optional[object]] = ContextVar(
        "agent", default=None
    )
    _memory_id_ctx: ContextVar[Optional[str]] = ContextVar(
        "memory_id", default=None
    )
    _actor_id_ctx: ContextVar[Optional[str]] = ContextVar(
        "actor_id", default=None
    )
    _session_id_ctx: ContextVar[Optional[str]] = ContextVar(
        "session_id", default=None
    )

    @classmethod
    def get_response_queue_ctx(
        cls,
    ) -> Optional[asyncio.Queue]:
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
    def get_gateway_token_ctx(
        cls,
    ) -> Optional[str]:
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

    @classmethod
    def get_memory_id_ctx(cls) -> Optional[str]:
        if cls._memory_id:
            return cls._memory_id
        try:
            return cls._memory_id_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_memory_id_ctx(cls, memory_id: str) -> None:
        cls._memory_id = memory_id
        cls._memory_id_ctx.set(memory_id)

    @classmethod
    def get_actor_id_ctx(cls) -> Optional[str]:
        if cls._actor_id:
            return cls._actor_id
        try:
            return cls._actor_id_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_actor_id_ctx(cls, actor_id: str) -> None:
        cls._actor_id = actor_id
        cls._actor_id_ctx.set(actor_id)

    @classmethod
    def get_session_id_ctx(cls) -> Optional[str]:
        if cls._session_id:
            return cls._session_id
        try:
            return cls._session_id_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_session_id_ctx(cls, session_id: str) -> None:
        cls._session_id = session_id
        cls._session_id_ctx.set(session_id)
