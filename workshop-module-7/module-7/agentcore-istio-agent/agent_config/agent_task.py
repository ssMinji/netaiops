from .context import IstioContext
from .memory_hook_provider import MemoryHookProvider
from .utils import get_ssm_parameter
from .agent import IstioMeshAgent
from bedrock_agentcore.memory import MemoryClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

memory_client = MemoryClient()


async def agent_task(user_message: str, session_id: str, actor_id: str):
    agent = IstioContext.get_agent_ctx()

    response_queue = IstioContext.get_response_queue_ctx()
    gateway_access_token = IstioContext.get_gateway_token_ctx()

    if not gateway_access_token:
        raise RuntimeError("Gateway Access token is none")
    try:
        if agent is None:
            # Get memory ID and user ID from SSM
            memory_id = get_ssm_parameter("/app/istio/agentcore/memory_id")

            # Get consistent USER_ID from SSM, fallback to actor_id
            try:
                consistent_user_id = get_ssm_parameter("/app/istio/agentcore/user_id")
                logger.info(f"Using consistent USER_ID from SSM: {consistent_user_id}")
            except Exception as e:
                logger.warning(f"Could not retrieve USER_ID from SSM, using actor_id: {e}")
                consistent_user_id = actor_id

            # Create new memory hook provider
            memory_hook_provider = MemoryHookProvider(
                memory_id=memory_id,
                client=memory_client
            )

            # Create agent with memory hook provider
            agent = IstioMeshAgent(
                bearer_token=gateway_access_token,
                memory_hook=memory_hook_provider,
                actor_id=consistent_user_id,
                session_id=session_id,
            )

            # Store context for future use
            IstioContext.set_memory_id_ctx(memory_id)
            IstioContext.set_actor_id_ctx(consistent_user_id)
            IstioContext.set_session_id_ctx(session_id)
            IstioContext.set_agent_ctx(agent)

        async for chunk in agent.stream(user_query=user_message):
            await response_queue.put(chunk)

    except Exception as e:
        logger.exception("Agent execution failed.")
        await response_queue.put(f"Error: {str(e)}")
    finally:
        await response_queue.finish()
