from .context import PerformanceContext
from .memory_hook_provider import MemoryHookProvider
from .utils import get_ssm_parameter
from .agent import PerformanceAgent
from bedrock_agentcore.memory import MemoryClient
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

memory_client = MemoryClient()


async def agent_task(user_message: str, session_id: str, actor_id: str):
    agent = PerformanceContext.get_agent_ctx()

    response_queue = PerformanceContext.get_response_queue_ctx()
    gateway_access_token = PerformanceContext.get_gateway_token_ctx()

    if not gateway_access_token:
        raise RuntimeError("Gateway Access token is none")
    try:
        if agent is None:
            # Get memory ID and user ID from SSM
            memory_id = get_ssm_parameter("/a2a/app/performance/agentcore/memory_id")
            
            # Get consistent USER_ID from SSM, fallback to actor_id if not available
            try:
                consistent_user_id = get_ssm_parameter("/a2a/app/performance/agentcore/user_id")
                logger.info(f"Using consistent USER_ID from SSM: {consistent_user_id}")
            except Exception as e:
                logger.warning(f"Could not retrieve USER_ID from SSM, using actor_id: {e}")
                consistent_user_id = actor_id
            
            # Create new memory hook provider
            memory_hook_provider = MemoryHookProvider(
                memory_id=memory_id,
                client=memory_client
            )

            # Seed memory with initial application and contact information using consistent USER_ID
            # try:
            #     memory_hook_provider.seed_memory(actor_id=consistent_user_id)
            #     logger.info(f"Memory seeded successfully for actor_id: {consistent_user_id}")
            # except Exception as e:
            #     logger.warning(f"Failed to seed memory for actor_id {consistent_user_id}: {e}")

            # Create agent with new memory hook provider using consistent USER_ID
            agent = PerformanceAgent(
                bearer_token=gateway_access_token,
                memory_hook_provider=memory_hook_provider,
                actor_id=consistent_user_id,
                session_id=session_id,
            )

            # Store memory context for future use
            PerformanceContext.set_memory_id_ctx(memory_id)
            PerformanceContext.set_actor_id_ctx(consistent_user_id)
            PerformanceContext.set_session_id_ctx(session_id)
            PerformanceContext.set_agent_ctx(agent)

        async for chunk in agent.stream(user_query=user_message):
            await response_queue.put(chunk)

    except Exception as e:
        logger.exception("Agent execution failed.")
        await response_queue.put(f"Error: {str(e)}")
    finally:
        await response_queue.finish()
