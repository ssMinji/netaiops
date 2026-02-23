"""
=============================================================================
Incident Analysis Agent - Entry Point (Module 6)
인시던트 분석 에이전트 - 진입점 (모듈 6)
=============================================================================
"""
from agent_config.context import IncidentContext
from agent_config.access_token import get_gateway_access_token
from agent_config.agent_task import agent_task
from agent_config.streaming_queue import StreamingQueue
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import asyncio
import logging
import os

os.environ["STRANDS_OTEL_ENABLE_CONSOLE_EXPORT"] = "true"
os.environ["STRANDS_TOOL_CONSOLE_MODE"] = "enabled"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

@app.entrypoint
async def invoke(payload, context):
    if not IncidentContext.get_response_queue_ctx():
        IncidentContext.set_response_queue_ctx(StreamingQueue())
    if not IncidentContext.get_gateway_token_ctx():
        IncidentContext.set_gateway_token_ctx(await get_gateway_access_token())

    user_message = payload["prompt"]
    actor_id = payload["actor_id"]
    session_id = context.session_id

    if not session_id:
        raise Exception("Context session_id is not set")

    task = asyncio.create_task(
        agent_task(user_message=user_message, session_id=session_id, actor_id=actor_id)
    )

    response_queue = IncidentContext.get_response_queue_ctx()

    async def stream_output():
        async for item in response_queue.stream():
            yield item
        await task

    return stream_output()

def handler(event, context):
    return app.handle(event, context)

if __name__ == "__main__":
    app.run()
