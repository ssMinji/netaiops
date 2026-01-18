from .context import TroubleshootingContext
from .memory_hook_provider import MemoryHookProvider
from .utils import get_ssm_parameter
from .agent import TroubleshootingAgent
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize memory hook provider
memory_hook_provider = MemoryHookProvider()


async def agent_task(user_message: str, session_id: str, actor_id: str):
    agent = TroubleshootingContext.get_agent_ctx()

    response_queue = TroubleshootingContext.get_response_queue_ctx()
    gateway_access_token = TroubleshootingContext.get_gateway_token_ctx()

    if not gateway_access_token:
        raise RuntimeError("Gateway Access token is none")
    try:
        if agent is None:
            # Try to get memory_id, but make it optional for Module 1
            # Check both EXAMPLECORP memory location and troubleshooting location
            memory_id = get_ssm_parameter("/examplecorp/agentcore/memory_id") or get_ssm_parameter("/app/troubleshooting/agentcore/memory_id")
            
            if memory_id:
                # Module 2: Use memory with validated actor_id
                # Ensure actor_id meets AWS validation: [a-zA-Z0-9][a-zA-Z0-9-_/]*
                safe_actor_id = actor_id if actor_id and actor_id[0].isalnum() else f"user_{actor_id}" if actor_id else "user1"
                safe_actor_id = ''.join(c if c.isalnum() or c in '-_/' else '_' for c in safe_actor_id)
                
                # Create memory hook using the provider (this ensures proper routing logic)
                memory_hook = memory_hook_provider.create_memory_hook(
                    actor_id=safe_actor_id,
                    session_id=session_id,
                )
                
                if memory_hook:
                    print(f"✅ Memory hook created successfully with routing logic")
                    agent = TroubleshootingAgent(
                        bearer_token=gateway_access_token,
                        memory_hook=memory_hook,
                    )
                else:
                    print(f"⚠️  Memory hook creation failed - using agent without memory")
                    agent = TroubleshootingAgent(
                        bearer_token=gateway_access_token,
                        memory_hook=None,
                    )
            else:
                # Module 1: No memory, just tools
                agent = TroubleshootingAgent(
                    bearer_token=gateway_access_token,
                    memory_hook=None,
                )

            TroubleshootingContext.set_agent_ctx(agent)

        async for chunk in agent.stream(user_query=user_message):
            await response_queue.put(chunk)

    except Exception as e:
        logger.exception("Agent execution failed.")
        await response_queue.put(f"Error: {str(e)}")
    finally:
        await response_queue.finish()
