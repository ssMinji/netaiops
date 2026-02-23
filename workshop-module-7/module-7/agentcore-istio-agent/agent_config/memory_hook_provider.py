from bedrock_agentcore.memory import MemoryClient
from strands.hooks.events import AgentInitializedEvent, MessageAddedEvent, AfterInvocationEvent
from strands.hooks.registry import HookProvider, HookRegistry
from typing import Dict
import logging
import uuid

logger = logging.getLogger(__name__)


def get_namespaces(mem_client: MemoryClient, memory_id: str) -> Dict:
    """Get namespace mapping for memory strategies."""
    try:
        strategies = mem_client.get_memory_strategies(memory_id)
        return {i["type"]: i["namespaces"][0] for i in strategies}
    except Exception as e:
        logger.error(f"Failed to get namespaces: {e}")
        return {}


class MemoryHookProvider(HookProvider):
    """Hook provider for automatic memory management - Istio Mesh diagnostics"""

    def __init__(self, memory_id: str, client: MemoryClient):
        self.memory_id = memory_id
        self.client = client
        self.namespaces = get_namespaces(self.client, self.memory_id)
        logger.info(f"Initialized MemoryHookProvider with namespaces: {self.namespaces}")

    def seed_memory(self, actor_id: str):
        """Seed memory with initial Istio mesh context information"""
        try:
            try:
                if self.namespaces:
                    first_namespace_template = list(self.namespaces.values())[0]
                    namespace = first_namespace_template.replace("{actorId}", actor_id)

                    existing_memories = self.client.retrieve_memories(
                        memory_id=self.memory_id,
                        namespace=namespace,
                        query="Istio-Mesh",
                        top_k=1
                    )
                    if existing_memories:
                        logger.info("Memory already contains seeded data, skipping seeding")
                        return
            except Exception as e:
                logger.info(f"Could not check existing memories, proceeding with seeding: {e}")

            from datetime import datetime
            session_id = f"user_{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # Seed with Istio mesh and cluster context
            mesh_interactions = [
                ("Istio mesh on EKS cluster netaiops-eks-cluster, namespace default has STRICT mTLS. Contact: platform-team@company.com", "USER"),
                ("Istio 메시 정보를 기록했습니다. EKS 클러스터 netaiops-eks-cluster의 default 네임스페이스에 STRICT mTLS가 설정되어 있으며, 담당자는 platform-team@company.com 입니다.", "ASSISTANT"),
            ]

            try:
                self.client.create_event(
                    memory_id=self.memory_id,
                    actor_id=actor_id,
                    session_id=session_id,
                    messages=mesh_interactions
                )
                logger.info("Seeded Istio mesh context information")
            except Exception as e:
                logger.warning(f"Error seeding mesh data: {e}")

        except Exception as e:
            logger.error(f"Failed to seed memory: {e}")
            logger.warning("Continuing without seeded memory data")

    def retrieve_memories(self, event: MessageAddedEvent):
        """Retrieve relevant memories before processing user message"""
        messages = event.agent.messages
        if messages[-1]["role"] == "user" and "toolResult" not in messages[-1]["content"][0]:
            user_query = messages[-1]["content"][0].get("text", "")

            try:
                actor_id = event.agent.state.get("actor_id")
                if not actor_id:
                    logger.warning("Missing actor_id in agent state")
                    return

                all_context = []

                for context_type, namespace_template in self.namespaces.items():
                    namespace = namespace_template.replace("{actorId}", actor_id)

                    try:
                        memories = self.client.retrieve_memories(
                            memory_id=self.memory_id,
                            namespace=namespace,
                            query=user_query,
                            top_k=3
                        )

                        for memory in memories:
                            if isinstance(memory, dict):
                                content = memory.get('content', {})
                                if isinstance(content, dict):
                                    text = content.get('text', '').strip()
                                    if text:
                                        all_context.append(f"[{context_type.upper()}] {text}")

                        logger.debug(f"Retrieved {len(memories)} memories from {context_type} namespace")

                    except Exception as e:
                        logger.warning(f"Failed to retrieve memories from {context_type}: {e}")

                if all_context:
                    context_text = "\n".join(all_context)
                    original_text = messages[-1]["content"][0]["text"]
                    messages[-1]["content"][0]["text"] = (
                        f"Application Context:\n{context_text}\n\n{original_text}"
                    )
                    logger.info(f"Retrieved {len(all_context)} application context items")
                else:
                    logger.warning("No memory context found to inject")

            except Exception as e:
                logger.error(f"Failed to retrieve application context: {e}")

    def save_memories(self, event: AfterInvocationEvent):
        """Save conversation after agent response"""
        try:
            messages = event.agent.messages
            if len(messages) >= 2 and messages[-1]["role"] == "assistant":
                user_query = None
                agent_response = None

                for msg in reversed(messages):
                    if msg["role"] == "assistant" and not agent_response:
                        agent_response = msg["content"][0]["text"]
                    elif msg["role"] == "user" and not user_query and "toolResult" not in msg["content"][0]:
                        user_query = msg["content"][0]["text"]
                        break

                if user_query and agent_response:
                    actor_id = event.agent.state.get("actor_id")
                    session_id = event.agent.state.get("session_id")

                    if not actor_id or not session_id:
                        logger.warning("Missing actor_id or session_id in agent state")
                        return

                    self.client.create_event(
                        memory_id=self.memory_id,
                        actor_id=actor_id,
                        session_id=session_id,
                        messages=[(user_query, "USER"), (agent_response, "ASSISTANT")]
                    )
                    logger.info("Saved Istio mesh diagnostics interaction to memory")

        except Exception as e:
            logger.error(f"Failed to save Istio mesh diagnostics interaction: {e}")

    def register_hooks(self, registry: HookRegistry) -> None:
        """Register memory hooks"""
        registry.add_callback(MessageAddedEvent, self.retrieve_memories)
        registry.add_callback(AfterInvocationEvent, self.save_memories)
        logger.info("Istio mesh diagnostics memory hooks registered")
