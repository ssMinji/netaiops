from .context import IncidentContext
from .memory_hook_provider import MemoryHook
from .utils import get_ssm_parameter
from .agent import IncidentAnalysisAgent
from bedrock_agentcore.memory import MemoryClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

memory_client = MemoryClient()

async def agent_task(user_message, session_id, actor_id):
    agent = IncidentContext.get_agent_ctx()
    response_queue = IncidentContext.get_response_queue_ctx()
    gateway_access_token = IncidentContext.get_gateway_token_ctx()
    if not gateway_access_token:
        raise RuntimeError("Gateway Access token is none")
    try:
        if agent is None:
            memory_id = get_ssm_parameter("/app/incident/agentcore/memory_id")
            if memory_id:
                memory_hook = MemoryHook(memory_client=memory_client, memory_id=memory_id,
                    actor_id=actor_id, session_id=session_id)
                agent = IncidentAnalysisAgent(bearer_token=gateway_access_token, memory_hook=memory_hook)
            else:
                agent = IncidentAnalysisAgent(bearer_token=gateway_access_token, memory_hook=None)
            IncidentContext.set_agent_ctx(agent)
        async for chunk in agent.stream(user_query=user_message):
            await response_queue.put(chunk)
    except Exception as e:
        logger.exception("Agent execution failed.")
        await response_queue.put(f"Error: {str(e)}")
    finally:
        await response_queue.finish()
