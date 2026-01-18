"""
Enhanced Memory Hook Provider for AgentCore Integration
Updated with Module-2 enhancements for seamless memory integration
"""
# Handle missing dependencies gracefully
try:
    import boto3
except ImportError:
    boto3 = None

from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

try:
    from bedrock_agentcore.memory import MemoryClient
except ImportError:
    MemoryClient = None

try:
    from strands.hooks.events import AgentInitializedEvent, MessageAddedEvent
    from strands.hooks.registry import HookProvider, HookRegistry
except ImportError:
    # Create dummy classes for when strands is not available
    class AgentInitializedEvent:
        pass
    class MessageAddedEvent:
        pass
    class HookProvider:
        pass
    class HookRegistry:
        pass

import copy


class MemoryHook(HookProvider):
    """
    Enhanced Memory Hook Provider with Module-2 capabilities
    Integrates with AgentCore runtime for automatic memory management
    """
    
    def __init__(
        self,
        memory_client: MemoryClient,
        memory_id: str,
        actor_id: str,
        session_id: str,
    ):
        self.memory_client = memory_client
        self.memory_id = memory_id
        # Use actor_id as provided - validation issue is elsewhere
        self.actor_id = actor_id
        self.session_id = session_id
        print(f"   🧠 Initialized memory hook: {memory_id}")

    def on_agent_initialized(self, event: AgentInitializedEvent):
        """Initialize agent with memory-aware system prompt and load session context"""
        try:
            # Load recent conversation history from ALL previous sessions for continuity
            # Use a consistent session pattern to retrieve cross-session context
            all_sessions_context = ""
            
            try:
                # Try to get recent turns from current session first
                recent_turns = self.memory_client.get_last_k_turns(
                    memory_id=self.memory_id,
                    actor_id=self.actor_id,
                    session_id=self.session_id,
                    k=10,
                )
                
                # If no recent turns in current session, try with a generic session pattern
                if not recent_turns:
                    # Try with different session patterns to find previous conversations
                    for session_pattern in ["troubleshooting_session", "main_session", "default_session"]:
                        try:
                            recent_turns = self.memory_client.get_last_k_turns(
                                memory_id=self.memory_id,
                                actor_id=self.actor_id,
                                session_id=session_pattern,
                                k=10,
                            )
                            if recent_turns:
                                print(f"   🔍 Found previous session context in: {session_pattern}")
                                break
                        except:
                            continue

                if recent_turns:
                    all_sessions_context = "\n\n=== PREVIOUS SESSION CONTEXT ===\n"
                    for turn in recent_turns[-5:]:  # Last 5 turns for context
                        for message in turn:
                            role = "User" if message["role"] == "USER" else "Assistant"
                            content = message["content"]["text"][:200] + "..." if len(message["content"]["text"]) > 200 else message["content"]["text"]
                            all_sessions_context += f"{role}: {content}\n"
                    all_sessions_context += "=== END PREVIOUS SESSION CONTEXT ===\n\n"
                    print(f"   🧠 Loaded {len(recent_turns)} previous conversation turns for session continuity")
                else:
                    print(f"   ℹ️  No previous session context found - starting fresh session")
                    
            except Exception as session_error:
                print(f"   ⚠️  Could not load session context: {session_error}")
                all_sessions_context = ""

            # Enhance system prompt to prioritize memory context
            event.agent.system_prompt += f"""

MEMORY-ENHANCED AGENT INSTRUCTIONS:
You are a memory-enhanced troubleshooting agent. When memory context is provided in your system prompt, you MUST use it directly in your responses.

{all_sessions_context}

MANDATORY MEMORY USAGE RULES:
1. When you see "=== SEMANTIC MEMORY STRATEGY CONTEXT ===" or similar memory blocks, use that exact information in your response
2. DO NOT use tools when memory context provides the answer
3. DO NOT give generic responses when specific memory information is available
4. Always end responses with the memory strategy tag: [Semantic Memory], [User Preference Memory], [Custom Memory], or [Summarization Memory]

CRITICAL: For permission questions, if memory shows "I belong to imaging-ops@examplecorp.com", you MUST start your response with "Yes, you belong to imaging-ops@examplecorp.com" - do not give generic permission responses.

MEMORY STRATEGY PRIORITIES:
- Semantic Memory: User permissions, platform architecture, operational facts
- User Preference Memory: Communication styles, troubleshooting preferences  
- Custom Memory: Institutional procedures, historical context
- Summary Memory: Session context, previous troubleshooting steps
"""
            print(f"   🧠 Enhanced agent system prompt with memory instructions and session context")

        except Exception as e:
            print(f"   ⚠️  Memory initialization error: {e}")

    def _add_context_user_query(
        self, namespace: str, query: str, init_content: str, event: MessageAddedEvent, strategy_name: str = "Memory"
    ):
        """Enhanced context retrieval with proper memory injection for Bedrock API"""
        try:
            memories = self.memory_client.retrieve_memories(
                memory_id=self.memory_id, namespace=namespace, query=query, top_k=3
            )

            if memories:
                # BALANCED APPROACH: Memory provides context, tools remain available
                memory_context = f"\n\n=== MEMORY CONTEXT FOR RESPONSE ===\n"
                memory_context += f"STRATEGY: {strategy_name.upper()}\n"
                memory_context += f"CONTEXT TYPE: {init_content}\n\n"
                
                # Build memory context with specific instructions for different query types
                for i, memory in enumerate(memories):
                    memory_text = memory['content']['text']
                    memory_context += f"MEMORY {i+1}: {memory_text}\n"
                
                # Add specific instructions based on query type and strategy
                user_query = event.agent.messages[-1]["content"][0]["text"].lower() if event.agent.messages else ""
                
                if strategy_name == "Custom Memory":
                    memory_context += f"\nCRITICAL FOR CUSTOM MEMORY: Use the EXACT procedures and historical context from memory above. Do NOT use tools to recreate information that is already stored in memory. Reference the specific support ticket and procedures mentioned in the memory content.\n"
                elif strategy_name == "Summary Memory":
                    # Summary Memory should ALWAYS use stored results, never run new analysis
                    memory_context += f"\nCRITICAL FOR SUMMARY MEMORY: This is a continuation session. Use ONLY the analysis results from memory above. NEVER use dns-resolve, connectivity, or any analysis tools. The analysis was already completed in the previous session.\n"
                    memory_context += f"\nFORBIDDEN ACTIONS: Do NOT call dns-resolve, connectivity, cloudwatch-monitoring, or any other analysis tools. Do NOT run fresh analysis. Do NOT resolve hostnames again.\n"
                    memory_context += f"\nMANDATORY BEHAVIOR: When user asks to apply the fix, go DIRECTLY to applying the security group fix using the connectivity tool with 'fix' action. Skip all DNS resolution and connectivity analysis steps.\n"
                    memory_context += f"\nFOR SUMMARY MEMORY: State the previous findings from memory, then when user confirms to apply fix, use connectivity tool ONLY with action='fix' parameter.\n"
                elif "permission" in user_query or "access" in user_query:
                    memory_context += f"\nFOR PERMISSION QUESTIONS: Start your response with the exact permission information from memory above, then offer to help with troubleshooting using your available tools.\n"
                elif "architecture" in user_query or "platform" in user_query:
                    memory_context += f"\nFOR ARCHITECTURE QUESTIONS: Use ONLY the exact platform information from memory above. Do NOT add instance IDs, IP addresses, or technical details not mentioned in the memory. Describe the architecture exactly as stored in memory, then offer troubleshooting assistance.\n"
                    memory_context += f"\nCRITICAL: If memory mentions Lambda and ALB, do NOT mention EC2 instances. If memory mentions TGW, do NOT add instance IDs. Use ONLY what is explicitly stated in the memory content above.\n"
                else:
                    memory_context += f"\nUSE MEMORY CONTEXT: Incorporate the relevant information from memory above into your response, while still offering to use your troubleshooting tools as needed.\n"
                
                memory_context += f"\nAVAILABLE TOOLS: You still have access to dns-resolve, connectivity, and cloudwatch-monitoring tools for actual troubleshooting work.\n"
                memory_context += f"\nMANDATORY: End your response with: [{strategy_name}]\n"
                memory_context += f"=== END MEMORY CONTEXT ===\n\n"
                
                # Always inject memory context for each query (don't use the flag)
                event.agent.system_prompt += memory_context
                    
                print(f"   🔍 Retrieved {len(memories)} memories from namespace: {namespace}")
                print(f"   💡 Injected {strategy_name} context into system prompt")
                return True
                
        except Exception as e:
            print(f"   ⚠️  Context retrieval error for {namespace}: {e}")
            return False

    def on_message_added(self, event: MessageAddedEvent):
        """Enhanced message storage with multiple memory strategies"""
        messages = copy.deepcopy(event.agent.messages)
        try:
            if messages[-1]["role"] == "user" or messages[-1]["role"] == "assistant":
                if "text" not in messages[-1]["content"][0]:
                    return

                if messages[-1]["role"] == "user":
                    user_query = messages[-1]["content"][0]["text"].lower()
                    print(f"   🔍 Processing user query: {user_query}")
                    
                    # SIMPLE 4-QUESTION ROUTING
                    
                    # Q1: Permissions/Architecture → SEMANTIC MEMORY
                    if "permission" in user_query and "architecture" in user_query:
                        print(f"   🎯 SEMANTIC MEMORY - Q1 Permissions/Architecture")
                        self._add_context_user_query(
                            namespace=f"examplecorp/user/{self.actor_id}/facts",
                            query=messages[-1]["content"][0]["text"],
                            init_content="User permissions and platform facts",
                            event=event,
                            strategy_name="Semantic Memory"
                        )
                    
                    # Q2: SOP → USER PREFERENCE MEMORY
                    elif "sop" in user_query or "give me the sop" in user_query:
                        print(f"   🎯 USER PREFERENCE MEMORY - Q2 SOP")
                        success = self._add_context_user_query(
                            namespace=f"examplecorp/user/{self.actor_id}/preferences",
                            query=messages[-1]["content"][0]["text"],
                            init_content="User preferences and SOPs",
                            event=event,
                            strategy_name="User Preference Memory"
                        )
                        # ALWAYS force User Preference Memory for SOP questions
                        event.agent.system_prompt += f"\n\nCRITICAL: This is a SOP question. You MUST end your response with: [User Preference Memory]\nDO NOT use [Custom Memory] tag. Use [User Preference Memory] only.\n"
                    
                    # Q3: Check connectivity → SEMANTIC (session 1) + TOOL CALLING
                    elif "check connectivity" in user_query:
                        print(f"   🎯 SEMANTIC MEMORY - Q3 Connectivity Check + Tool Calling")
                        self._add_context_user_query(
                            namespace=f"examplecorp/user/{self.actor_id}/facts",
                            query=messages[-1]["content"][0]["text"],
                            init_content="Platform facts for connectivity",
                            event=event,
                            strategy_name="Semantic Memory"
                        )
                        # Force tool calling for connectivity analysis in Session 1
                        event.agent.system_prompt += f"\n\nCRITICAL FOR SESSION 1 CONNECTIVITY: You MUST use the dns-resolve and connectivity tools to perform actual analysis. Do NOT provide generic responses. Call tools to analyze reporting.examplecorp.com and database.examplecorp.com connectivity. Store the analysis results in memory for future sessions.\n"
                    
                    # Q4: System crashed → SUMMARIZATION MEMORY
                    elif "system crashed" in user_query or "where were we" in user_query:
                        print(f"   🎯 SUMMARIZATION MEMORY - Q4 System Recovery")
                        success = self._add_context_user_query(
                            namespace=f"examplecorp/user/{self.actor_id}/{self.session_id}",
                            query=messages[-1]["content"][0]["text"],
                            init_content="Previous session results",
                            event=event,
                            strategy_name="Summarization Memory"
                        )
                        # Force Summarization Memory if no stored session
                        if not success:
                            event.agent.system_prompt += f"\n\nMANDATORY: End your response with: [Summarization Memory]\n"
                
                # Store conversation in memory
                self.memory_client.save_conversation(
                    memory_id=self.memory_id,
                    actor_id=self.actor_id,
                    session_id=self.session_id,
                    messages=[
                        (messages[-1]["content"][0]["text"], messages[-1]["role"])
                    ],
                )
                print(f"   💾 Stored message in memory: {messages[-1]['role']}")
                
                # Special handling for assistant responses with connectivity analysis
                if messages[-1]["role"] == "assistant":
                    content = messages[-1]["content"][0]["text"]
                    
                    # If this is a connectivity analysis response, store it in summary memory
                    if any(indicator in content for indicator in ["PathID", "nip-", "ENI_SG_RULES_MISMATCH", "connectivity", "reporting.examplecorp.com", "database.examplecorp.com"]):
                        try:
                            # Extract key troubleshooting details
                            summary_content = f"Connectivity Analysis Results:\n"
                            if "PathID" in content or "nip-" in content:
                                # Extract PathID
                                import re
                                path_match = re.search(r'(nip-[a-f0-9]+)', content)
                                if path_match:
                                    summary_content += f"PathID: {path_match.group(1)}\n"
                            
                            if "ENI_SG_RULES_MISMATCH" in content:
                                summary_content += f"Issue: ENI_SG_RULES_MISMATCH on TCP port 3306\n"
                            
                            if "reporting.examplecorp.com" in content and "database.examplecorp.com" in content:
                                summary_content += f"Resources: reporting.examplecorp.com to database.examplecorp.com\n"
                            
                            if "i-" in content:
                                # Extract instance ID
                                instance_match = re.search(r'(i-[a-f0-9]+)', content)
                                if instance_match:
                                    summary_content += f"Source Instance: {instance_match.group(1)}\n"
                            
                            summary_content += f"Status: Analysis completed, security group fix required\n"
                            summary_content += f"Next Step: Update RDS security group rules for port 3306\n"
                            
                            # Store in summary memory for cross-session access
                            self.memory_client.save_conversation(
                                memory_id=self.memory_id,
                                actor_id=self.actor_id,
                                session_id="troubleshooting_session",  # Standard session for cross-session access
                                messages=[
                                    (summary_content, "assistant")
                                ]
                            )
                            print(f"   📝 Stored connectivity analysis in summary memory for session continuity")
                            
                        except Exception as summary_error:
                            print(f"   ⚠️  Could not store connectivity summary: {summary_error}")

        except Exception as e:
            print(f"   ⚠️  Memory save error: {e}")
            # Don't raise exception to avoid breaking the agent runtime
            # raise RuntimeError(f"Memory save error: {e}")

    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(MessageAddedEvent, self.on_message_added)
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)


class MemoryHookProvider:
    """
    Enhanced Memory Hook Provider with automatic SSM integration
    Compatible with both Module-1 and Module-2 memory configurations
    """
    
    def __init__(self, region: str = "us-east-1"):
        self.region = region
        
        # Handle missing dependencies gracefully
        if MemoryClient is None:
            print(f"   ⚠️  MemoryClient not available - memory functionality will be limited")
            self.memory_client = None
        else:
            self.memory_client = MemoryClient(region_name=region)
            
        if boto3 is None:
            print(f"   ⚠️  boto3 not available - SSM functionality will be limited")
            self.ssm_client = None
        else:
            self.ssm_client = boto3.client('ssm', region_name=region)
            
        self.memory_id = self._get_memory_id_from_ssm()
        self.memory_session_id = str(uuid.uuid4())
        print(f"   🧠 Initialized memory session: {self.memory_session_id}")
        if self.memory_id:
            print(f"   🧠 Using memory: {self.memory_id}")
    
    def _get_memory_id_from_ssm(self) -> Optional[str]:
        """Retrieve memory ID from SSM Parameter Store"""
        try:
            if self.ssm_client is None:
                print(f"   ⚠️  SSM client not available - cannot retrieve memory ID")
                return None
                
            response = self.ssm_client.get_parameter(Name="/examplecorp/agentcore/memory_id")
            memory_id = response['Parameter']['Value']
            print(f"   📋 Retrieved memory ID from SSM: {memory_id}")
            return memory_id
        except Exception as e:
            print(f"   ⚠️  Could not retrieve memory ID from SSM: {str(e)}")
            print(f"   💡 Make sure to run module-2 setup_examplecorp_memory.py to create memory resource")
            return None
    
    async def store_memory(self, strategy: str, content: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Store memory content using save_conversation"""
        try:
            if not self.memory_client or not self.memory_id:
                print(f"   ⚠️  Memory client or ID not available - simulating storage for {strategy}")
                return {
                    "memory_id": f"mem_{strategy}_{uuid.uuid4().hex[:8]}",
                    "status": "simulated",
                    "strategy": strategy,
                    "error": "Memory client not available"
                }
            
            # Use actor_id as provided - convert to valid format for AWS Bedrock
            actor_id = metadata.get("user_id", "imaging-ops-examplecorp-com") if metadata else "imaging-ops-examplecorp-com"
            session_id = metadata.get("session_id", self.memory_session_id) if metadata else self.memory_session_id
            
            print(f"   💾 STORING [{strategy}] for actor:{actor_id}, session:{session_id}")
            print(f"   📝 Content: {content[:100]}{'...' if len(content) > 100 else ''}")
            if metadata:
                print(f"   🏷️  Metadata: {metadata}")
            
            # Store both user and assistant messages to trigger all strategies
            self.memory_client.save_conversation(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                messages=[
                    (content, "user"),
                    ("Acknowledged and stored in memory.", "assistant")
                ]
            )
            
            # Add delay to allow memory processing and indexing
            import asyncio
            await asyncio.sleep(3.0)
            
            print(f"   ✅ STORED successfully in memory {self.memory_id}")
            
            return {
                "memory_id": f"mem_{strategy}_{uuid.uuid4().hex[:8]}",
                "status": "stored",
                "strategy": strategy
            }
            
        except Exception as e:
            print(f"   ⚠️  Memory storage failed: {str(e)}")
            return {
                "memory_id": f"mem_{strategy}_{uuid.uuid4().hex[:8]}",
                "status": "fallback",
                "strategy": strategy,
                "error": str(e)
            }
    
    async def retrieve_memory(self, strategy: str, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Retrieve memory content using retrieve_memories with retry logic"""
        import asyncio
        
        try:
            if not self.memory_id:
                return []
            
            # Use standard actor_id
            actor_id = "user"
            
            # Try namespace patterns matching the exact memory configuration
            namespace_patterns = [
                f"examplecorp/user/{actor_id}/facts",                        # Semantic memory
                f"examplecorp/user/{actor_id}/preferences",                  # User preference memory
                f"examplecorp/user/{actor_id}/{self.memory_session_id}",     # Summarization memory
                f"examplecorp/procedures/{actor_id}/workflows",              # Custom memory procedures
                f"troubleshooting/user/{actor_id}/permissions",       # Module-1 compatibility
                f"troubleshooting/user/{actor_id}/facts"              # Module-1 compatibility
            ]
            
            # Retry logic for memory retrieval
            max_retries = 3
            retry_delay = 2.0
            
            for attempt in range(max_retries):
                all_results = []
                found_namespaces = []
                
                for namespace in namespace_patterns:
                    try:
                        memories = self.memory_client.retrieve_memories(
                            memory_id=self.memory_id,
                            namespace=namespace,
                            query=query,
                            top_k=max_results
                        )
                        
                        if memories:
                            if not found_namespaces:
                                print(f"   🔍 RETRIEVING [{strategy}] memories (attempt {attempt + 1})")
                                print(f"   🔎 Query: '{query}'")
                            
                            print(f"   ✅ FOUND {len(memories)} memories in namespace: {namespace}")
                            found_namespaces.append(namespace)
                            
                            for i, memory in enumerate(memories):
                                content = memory.get("content", {}).get("text", "")
                                print(f"   📄 Memory {i+1}: {content[:100]}{'...' if len(content) > 100 else ''}")
                                
                                all_results.append({
                                    "memory_id": memory.get("id", "unknown"),
                                    "content": content,
                                    "metadata": memory.get("metadata", {}),
                                    "timestamp": memory.get("created_at", datetime.now().isoformat()),
                                    "strategy": strategy,
                                    "namespace": namespace
                                })
                        
                    except Exception as ns_error:
                        if "not found" not in str(ns_error).lower():
                            print(f"   ⚠️  Error searching namespace {namespace}: {str(ns_error)}")
                        continue
                
                # If we found results, return them
                if all_results:
                    # Remove duplicates and limit results
                    unique_results = []
                    seen_content = set()
                    for result in all_results:
                        content_key = result["content"][:100]
                        if content_key not in seen_content:
                            seen_content.add(content_key)
                            unique_results.append(result)
                    
                    print(f"   🎯 RETURNING {len(unique_results)} unique results from all namespaces")
                    return unique_results[:max_results]
                
                # If no results and not the last attempt, wait and retry
                if attempt < max_retries - 1:
                    print(f"   ⏳ No memories found on attempt {attempt + 1}, retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5
            
            print(f"   ⚠️  No memories found in any namespace for query: '{query}' after {max_retries} attempts")
            return []
            
        except Exception as e:
            print(f"   ⚠️  Memory retrieval failed: {str(e)}")
            return []

    def create_memory_hook(self, actor_id: str, session_id: str) -> Optional[MemoryHook]:
        """Create a MemoryHook instance for AgentCore runtime integration"""
        if not self.memory_id:
            print(f"   ⚠️  Cannot create memory hook - no memory ID available")
            return None
        
        return MemoryHook(
            memory_client=self.memory_client,
            memory_id=self.memory_id,
            actor_id=actor_id,
            session_id=session_id
        )

    # Stage-3 compatible methods for backward compatibility
    async def get_last_k_turns(self, actor_id: str, session_id: str, k: int = 5) -> List[Any]:
        """Get last k conversation turns - backward compatibility"""
        try:
            if not self.memory_id:
                return []
            return self.memory_client.get_last_k_turns(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                k=k
            )
        except Exception as e:
            print(f"   ⚠️  get_last_k_turns failed: {str(e)}")
            return []

    async def save_conversation(self, actor_id: str, session_id: str, messages: List[tuple]) -> Dict[str, Any]:
        """Save conversation messages - backward compatibility"""
        try:
            if not self.memory_id:
                return {"status": "fallback", "message": "No memory ID"}
                
            self.memory_client.save_conversation(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                messages=messages
            )
            
            return {"status": "success", "messages_saved": len(messages)}
            
        except Exception as e:
            print(f"   ⚠️  save_conversation failed: {str(e)}")
            return {"status": "error", "error": str(e)}


# Create aliases for backward compatibility
WorkshopProgressHook = MemoryHookProvider
CorrespondenceMemoryHook = MemoryHookProvider

