from .context import K8sContext
from .memory_hook_provider import MemoryHookProvider
from .utils import get_ssm_parameter
from .agent import K8sAgent
from bedrock_agentcore.memory import MemoryClient
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

memory_client = MemoryClient()


async def agent_task(user_message: str, session_id: str, actor_id: str):
    agent = K8sContext.get_agent_ctx()

    response_queue = K8sContext.get_response_queue_ctx()
    gateway_access_token = K8sContext.get_gateway_token_ctx()

    if not gateway_access_token:
        raise RuntimeError("Gateway Access token is none")
    try:
        if agent is None:
            # Get memory ID and user ID from SSM
            memory_id = get_ssm_parameter("/a2a/app/k8s/agentcore/memory_id")

            # Get consistent USER_ID from SSM, fallback to actor_id if not available
            try:
                consistent_user_id = get_ssm_parameter("/a2a/app/k8s/agentcore/user_id")
                logger.info(f"Using consistent USER_ID from SSM: {consistent_user_id}")
            except Exception as e:
                logger.warning(f"Could not retrieve USER_ID from SSM, using actor_id: {e}")
                consistent_user_id = actor_id

            # Create new memory hook provider
            memory_hook_provider = MemoryHookProvider(
                memory_id=memory_id,
                client=memory_client
            )

            # Create agent with new memory hook provider using consistent USER_ID
            agent = K8sAgent(
                bearer_token=gateway_access_token,
                memory_hook_provider=memory_hook_provider,
                actor_id=consistent_user_id,
                session_id=session_id,
            )

            # Store memory context for future use
            K8sContext.set_memory_id_ctx(memory_id)
            K8sContext.set_actor_id_ctx(consistent_user_id)
            K8sContext.set_session_id_ctx(session_id)
            K8sContext.set_agent_ctx(agent)

        async for chunk in agent.stream(user_query=user_message):
            await response_queue.put(chunk)

    except Exception as e:
        logger.exception("Agent execution failed.")
        await response_queue.put(f"Error: {str(e)}")
    finally:
        await response_queue.finish()
