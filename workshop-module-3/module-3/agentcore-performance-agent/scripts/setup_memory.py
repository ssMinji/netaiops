#!/usr/bin/python
import click
import boto3
import sys
import os
import logging
from datetime import datetime
from typing import Dict
from botocore.exceptions import ClientError
from strands.hooks import AfterInvocationEvent, HookProvider, HookRegistry, MessageAddedEvent


from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType
from utils import get_aws_region

# User and session identifiers
USER_ID = "user_001"
SESSION_ID = f"user_{datetime.now().strftime('%Y%m%d%H%M%S')}"

# Force us-east-1 region for all operations
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
REGION = "us-east-1"
ssm = boto3.client("ssm", region_name=REGION)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Memory Client
client = MemoryClient(region_name=REGION)
memory_name = "PerformanceAgentMemory"

# Define custom prompt for performance metadata extraction
CUSTOM_PROMPT = """
Extract performance-related information from conversations:
- Network performance metrics (latency, packet loss, retransmissions)
- Performance issues and their resolutions
- Infrastructure components involved in performance problems
Focus specifically on performance diagnostics and troubleshooting context.
"""

# Memory execution role ARN - this should be set based on your environment
ROLE_ARN = os.environ.get('MEMORY_EXECUTION_ROLE_ARN', '')


# Helper function to get namespaces from memory strategies list
def get_namespaces(mem_client: MemoryClient, memory_id: str) -> Dict:
    """Get namespace mapping for memory strategies."""
    strategies = mem_client.get_memory_strategies(memoryId=memory_id)
    return {i["type"]: i["namespaces"][0] for i in strategies}


class UserMemoryHooks(HookProvider):
    """Memory hooks for performance agent"""
    
    def __init__(self, memory_id: str, client: MemoryClient):
        self.memory_id = memory_id
        self.client = client
        self.namespaces = get_namespaces(self.client, self.memory_id)

    
    def retrieve_performance_context(self, event: MessageAddedEvent):
        """Retrieve performance context before processing performance query"""
        messages = event.agent.messages
        if messages[-1]["role"] == "user" and "toolResult" not in messages[-1]["content"][0]:
            user_query = messages[-1]["content"][0]["text"]
            
            try:
                # Retrieve performance context from all namespaces
                all_context = []
                
                # Get actor_id from agent state
                actor_id = event.agent.state.get("actor_id")
                if not actor_id:
                    logger.warning("Missing actor_id in agent state")
                    return
                
                for context_type, namespace in self.namespaces.items():
                    memories = self.client.retrieve_memories(
                        memoryId=self.memory_id,
                        namespace=namespace.format(actorId=actor_id),
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
                
                # Inject performance context into the query
                if all_context:
                    context_text = "\n".join(all_context)
                    original_text = messages[-1]["content"][0]["text"]
                    messages[-1]["content"][0]["text"] = (
                        f"Performance Context:\n{context_text}\n\n{original_text}"
                    )
                    logger.info(f"Retrieved {len(all_context)} performance context items")
                    
            except Exception as e:
                logger.error(f"Failed to retrieve performance context: {e}")
    
    def save_performance_interaction(self, event: AfterInvocationEvent):
        """Save performance interaction after agent response"""
        try:
            messages = event.agent.messages
            if len(messages) >= 2 and messages[-1]["role"] == "assistant":
                # Get last user query and agent response
                user_query = None
                agent_response = None
                
                for msg in reversed(messages):
                    if msg["role"] == "assistant" and not agent_response:
                        agent_response = msg["content"][0]["text"]
                    elif msg["role"] == "user" and not user_query and "toolResult" not in msg["content"][0]:
                        user_query = msg["content"][0]["text"]
                        break
                
                if user_query and agent_response:
                    # Get session info from agent state
                    actor_id = event.agent.state.get("actor_id")
                    session_id = event.agent.state.get("session_id")
                    
                    if not actor_id or not session_id:
                        logger.warning("Missing actor_id or session_id in agent state")
                        return
                    
                    # Save the performance interaction
                    self.client.create_event(
                        memoryId=self.memory_id,
                        actor_id=actor_id,
                        session_id=session_id,
                        messages=[(user_query, "USER"), (agent_response, "ASSISTANT")]
                    )
                    logger.info("Saved performance interaction to memory")
                    
        except Exception as e:
            logger.error(f"Failed to save performance interaction: {e}")
    
    def register_hooks(self, registry: HookRegistry) -> None:
        """Register performance memory hooks"""
        registry.add_callback(MessageAddedEvent, self.retrieve_performance_context)
        registry.add_callback(AfterInvocationEvent, self.save_performance_interaction)
        logger.info("Performance memory hooks registered")


def store_memory_id_in_ssm(param_name: str, memory_id: str):
    ssm.put_parameter(Name=param_name, Value=memory_id, Type="String", Overwrite=True)
    click.echo(f"🔐 Stored memory_id in SSM: {param_name}")


def store_user_id_in_ssm(param_name: str, user_id: str):
    ssm.put_parameter(Name=param_name, Value=user_id, Type="String", Overwrite=True)
    click.echo(f"🔐 Stored user_id in SSM: {param_name}")


def get_memory_id_from_ssm(param_name: str):
    """Check if memory ID already stored in SSM (idempotent check)"""
    try:
        response = ssm.get_parameter(Name=param_name)
        return response["Parameter"]["Value"]
    except ClientError as e:
        if e.response['Error']['Code'] == 'ParameterNotFound':
            return None
        raise click.ClickException(f"❌ Could not retrieve memory_id from SSM: {e}")


def verify_memory_exists_and_valid(memory_id: str) -> bool:
    """Verify memory exists and is properly configured"""
    try:
        # Check if memory exists
        memory = client.get_memory(memoryId=memory_id)
        
        # Verify it has the expected strategies
        strategies = client.get_memory_strategies(memoryId=memory_id)
        strategy_types = {s['type'] for s in strategies}
        expected_types = {'user_preference', 'semantic'}
        
        if strategy_types == expected_types:
            print(f"✅ Memory {memory_id} is valid and correctly configured")
            return True
        else:
            print(f"⚠️  Memory {memory_id} exists but config differs")
            print(f"   Expected: {expected_types}")
            print(f"   Found: {strategy_types}")
            return False
    except Exception as e:
        print(f"⚠️  Memory {memory_id} not found or invalid: {e}")
        return False


def delete_ssm_param(param_name: str):
    try:
        ssm.delete_parameter(Name=param_name)
        click.echo(f"🧹 Deleted SSM parameter: {param_name}")
    except ClientError as e:
        click.echo(f"⚠️ Failed to delete SSM parameter: {e}")


def seed_specific_performance_memory(memory_id: str, issue_type: str, resolution: str):
    """Seed memory with specific performance issue and resolution"""
    print(f"🌱 Seeding memory with {issue_type} -> {resolution}")
    
    # Create performance interaction for the specific issue and resolution
    performance_interactions = [
        (f"Performance issue: {issue_type}. Resolution: {resolution}", "USER"),
        (f"I've recorded the performance issue '{issue_type}' with resolution: {resolution}.", "ASSISTANT")
    ]

    # Save performance interactions
    try:
        client.create_event(
            memoryId=memory_id,
            actor_id=USER_ID,
            session_id=SESSION_ID,
            messages=performance_interactions
        )
        print(f"✅ Seeded performance issue: {issue_type}")
    except Exception as e:
        print(f"⚠️ Error seeding performance data: {e}")
        raise


@click.group()
@click.pass_context
def cli(ctx):
    """AgentCore Memory Management CLI.

    Create and delete AgentCore memory resources for the performance agent.
    """
    ctx.ensure_object(dict)


@cli.command()
@click.option(
    "--name", default="PerformanceAgentMemory", help="Name of the memory resource"
)
@click.option(
    "--ssm-param",
    default="/a2a/app/performance/agentcore/memory_id",
    help="SSM parameter to store memory_id",
)
@click.option(
    "--event-expiry-days",
    default=30,
    type=int,
    help="Number of days before events expire (default: 30)",
)
def create(name, ssm_param, event_expiry_days):
    """Create a new AgentCore memory resource."""
    click.echo(f"🚀 Creating AgentCore memory: {name}")
    click.echo(f"📍 Region: {REGION}")
    click.echo(f"⏱️  Event expiry: {event_expiry_days} days")

    # Define memory strategies for performance issues and resolutions
    strategies = [
        {
            StrategyType.USER_PREFERENCE.value: {
                "name": "PerformancePreferences",
                "description": "Captures performance preferences and troubleshooting patterns",
                "namespaces": ["performance/issues/{actorId}/preferences"]
            }
        },
        {
            StrategyType.SEMANTIC.value: {
                "name": "PerformanceIssueSemantic",
                "description": "Stores performance issues, metrics, and resolutions from conversations",
                "namespaces": ["performance/issues/{actorId}/semantic"],
            }
        }
    ]

    memory_id = None
    # Create memory resource
    try:
        click.echo("🔄 Creating memory resource...")
        memory = client.create_memory_and_wait(
            name=name,
            strategies=strategies,         # Define the memory strategies
            description="Memory for performance diagnostics - stores performance issues, metrics, and resolutions",
            event_expiry_days=event_expiry_days,          # Memories expire after specified days
        )
        memory_id = memory['id']
        logger.info(f"✅ Created memory: {memory_id}")
        click.echo(f"✅ Memory created successfully: {memory_id}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ValidationException' and "already exists" in str(e):
            # If memory already exists, retrieve its ID
            click.echo("📋 Memory already exists, finding existing resource...")
            memories = client.list_memories()
            memory_id = next((m['id'] for m in memories if m['id'].startswith(name)), None)
            logger.info(f"Memory already exists. Using existing memory ID: {memory_id}")
            click.echo(f"✅ Using existing memory: {memory_id}")
        else:
            logger.info(f"❌ ERROR: {e}")
            click.echo(f"❌ Error creating memory: {str(e)}", err=True)
            sys.exit(1)
    except Exception as e:
        # Handle any errors during memory creation
        logger.info(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        click.echo(f"❌ Error creating memory: {str(e)}", err=True)
        # Cleanup on error - delete the memory if it was partially created
        if memory_id:
            try:
                client.delete_memory_and_wait(memoryId=memory_id, max_wait=300)
                logger.info(f"Cleaned up memory: {memory_id}")
                click.echo(f"🧹 Cleaned up partially created memory: {memory_id}")
            except Exception as cleanup_error:
                logger.info(f"Failed to clean up memory: {cleanup_error}")
                click.echo(f"⚠️ Failed to clean up memory: {cleanup_error}")
        sys.exit(1)

    try:
        store_memory_id_in_ssm(ssm_param, memory_id)
        
        click.echo("🎉 Memory setup completed successfully!")
        click.echo(f"   Memory ID: {memory_id}")
        click.echo(f"   SSM Parameter: {ssm_param}")
        click.echo(f"")
        click.echo(f"📋 Memory Strategies Configured:")
        click.echo(f"   👤 User Preferences: Captures performance preferences and troubleshooting patterns")
        click.echo(f"   🧠 Semantic Memory: Stores performance issues, metrics, and resolutions from conversations")

    except Exception as e:
        click.echo(f"⚠️  Memory created but failed to store in SSM: {str(e)}", err=True)


@cli.command()
@click.option(
    "--issue", 
    required=True,
    help="Performance issue type to seed (e.g., High-Retransmissions)"
)
@click.option(
    "--resolution", 
    required=True,
    help="Resolution for the performance issue (e.g., Increased MTU size)"
)
@click.option(
    "--memory-id",
    help="Memory ID to use (if not provided, will read from SSM parameter)",
)
@click.option(
    "--ssm-param",
    default="/a2a/app/performance/agentcore/memory_id",
    help="SSM parameter to retrieve memory_id from",
)
def seed(issue, resolution, memory_id, ssm_param):
    """Seed memory with specific performance issue and resolution."""
    click.echo(f"🌱 Seeding memory with performance issue: {issue} -> {resolution}")
    
    # Get memory ID from SSM if not provided
    if not memory_id:
        try:
            memory_id = get_memory_id_from_ssm(ssm_param)
            click.echo(f"📖 Using memory ID from SSM: {memory_id}")
        except Exception:
            click.echo("❌ No memory ID provided and couldn't read from SSM parameter", err=True)
            sys.exit(1)
    
    # Seed with the specific performance issue and resolution
    try:
        seed_specific_performance_memory(memory_id, issue, resolution)
        click.echo("✅ Performance issue seeded successfully!")
    except Exception as e:
        click.echo(f"❌ Error seeding performance issue: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--memory-id",
    help="Memory ID to delete (if not provided, will read from SSM parameter)",
)
@click.option(
    "--ssm-param",
    default="/a2a/app/performance/agentcore/memory_id",
    help="SSM parameter to retrieve memory_id from",
)
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete(memory_id, ssm_param, confirm):
    """Delete an AgentCore memory resource."""

    # If no memory ID provided, try to read from SSM
    if not memory_id:
        try:
            memory_id = get_memory_id_from_ssm(ssm_param)
            click.echo(f"📖 Using memory ID from SSM: {memory_id}")
        except Exception:
            click.echo(
                "❌ No memory ID provided and couldn't read from SSM parameter",
                err=True,
            )
            sys.exit(1)

    # Confirmation prompt
    if not confirm:
        if not click.confirm(
            f"⚠️  Are you sure you want to delete memory {memory_id}? This action cannot be undone."
        ):
            click.echo("❌ Operation cancelled")
            sys.exit(0)

    click.echo(f"🗑️  Deleting memory: {memory_id}")

    try:
        client.delete_memory_and_wait(memoryId=memory_id)
        click.echo(f"✅ Memory deleted successfully: {memory_id}")
    except Exception as e:
        click.echo(f"❌ Error deleting memory: {str(e)}", err=True)
        sys.exit(1)

    # Always delete SSM parameter
    delete_ssm_param(ssm_param)
    click.echo("🎉 Memory and SSM parameter deleted successfully")


def verify_memory_storage(memory_id):
    """Verify stored memories in the memory system"""
    # Check stored performance memories
    print("\n📚 Performance Memory Summary:")
    print("=" * 50)

    namespaces_dict = get_namespaces(client, memory_id)
    for context_type, namespace_template in namespaces_dict.items():
        namespace = namespace_template.replace("{actorId}", USER_ID)
        
        try:
            memories = client.retrieve_memories(
                memoryId=memory_id,
                namespace=namespace,
                query="performance issues and resolutions",
                top_k=3
            )
            
            print(f"\n{context_type.upper()} ({len(memories)} items):")
            for i, memory in enumerate(memories, 1):
                if isinstance(memory, dict):
                    content = memory.get('content', {})
                    if isinstance(content, dict):
                        text = content.get('text', '')[:150] + "..."
                        print(f"  {i}. {text}")
                        
        except Exception as e:
            print(f"Error retrieving {context_type} memories: {e}")

    print("\n" + "=" * 50)


def setup_performance_memory():
    """Idempotent memory setup - checks before creating"""
    click.echo("🧠 Setting up Performance Agent Memory...")
    
    ssm_param = "/a2a/app/performance/agentcore/memory_id"
    event_expiry_days = 90  # Extended retention for performance data
    
    # STEP 1: Check if memory ID already in SSM
    existing_memory_id = get_memory_id_from_ssm(ssm_param)
    
    if existing_memory_id:
        print(f"✅ Found existing memory ID in SSM: {existing_memory_id}")
        
        # STEP 2: Verify it still exists and is valid
        if verify_memory_exists_and_valid(existing_memory_id):
            print(f"✅ Memory already configured, skipping creation")
            store_user_id_in_ssm("/a2a/app/performance/agentcore/user_id", USER_ID)
            return existing_memory_id
        else:
            print(f"⚠️  Memory invalid or missing, will recreate")
            # Try to delete if it exists but is invalid
            try:
                client.delete_memory_and_wait(memoryId=existing_memory_id)
                print(f"🗑️  Deleted invalid memory: {existing_memory_id}")
            except:
                pass
    
    # STEP 3: Check if memory exists by name (alternative check)
    print(f"🔍 Checking if memory exists by name: {memory_name}")
    try:
        memories = client.list_memories()
        for mem in memories:
            if mem['id'].startswith(memory_name):
                memory_id = mem['id']
                print(f"✅ Found existing memory by name: {memory_id}")
                # Verify it's valid before using
                if verify_memory_exists_and_valid(memory_id):
                    store_memory_id_in_ssm(ssm_param, memory_id)
                    store_user_id_in_ssm("/a2a/app/performance/agentcore/user_id", USER_ID)
                    print("✅ Performance Agent Memory setup complete!")
                    print(f"   Memory ID: {memory_id}")
                    print(f"   SSM Parameter: {ssm_param}")
                    return memory_id
    except Exception as e:
        print(f"⚠️  Error listing memories: {e}")
    
    # Define memory strategies for performance issues and resolutions
    strategies = [
        {
            StrategyType.USER_PREFERENCE.value: {
                "name": "PerformancePreferences",
                "description": "Captures performance preferences and troubleshooting patterns",
                "namespaces": ["performance/issues/{actorId}/preferences"]
            }
        },
        {
            StrategyType.SEMANTIC.value: {
                "name": "PerformanceIssueSemantic",
                "description": "Stores performance issues, metrics, and resolutions from conversations",
                "namespaces": ["performance/issues/{actorId}/semantic"],
            }
        }
    ]

    # STEP 4: Create new memory (only if doesn't exist)
    memory_id = None
    print(f"🆕 Creating new memory: {memory_name}")
    try:
        memory = client.create_memory_and_wait(
            name=memory_name,
            strategies=strategies,
            description="Memory for performance diagnostics - stores performance issues, metrics, and resolutions",
            event_expiry_days=event_expiry_days,
        )
        memory_id = memory['id']
        logger.info(f"✅ Created memory: {memory_id}")
        
        store_memory_id_in_ssm(ssm_param, memory_id)
        store_user_id_in_ssm("/a2a/app/performance/agentcore/user_id", USER_ID)
        
        print("✅ Performance Agent Memory setup complete!")
        print(f"   Memory ID: {memory_id}")
        print(f"   SSM Parameter: {ssm_param}")
        print(f"   Strategies: User Preferences + Semantic Memory for performance diagnostics")
        return memory_id
        
    except ClientError as e:
        if 'already exists' in str(e).lower():
            # Race condition - memory was created between our checks
            print("⚠️  Memory was created concurrently, fetching ID...")
            memories = client.list_memories()
            memory_id = next((m['id'] for m in memories if m['id'].startswith(memory_name)), None)
            if memory_id:
                store_memory_id_in_ssm(ssm_param, memory_id)
                store_user_id_in_ssm("/a2a/app/performance/agentcore/user_id", USER_ID)
                print("✅ Performance Agent Memory setup complete!")
                print(f"   Memory ID: {memory_id}")
                print(f"   SSM Parameter: {ssm_param}")
                return memory_id
        
        logger.info(f"❌ ERROR: {e}")
        print(f"❌ Failed to setup memory: {e}")
        sys.exit(1)
    except Exception as e:
        # Handle any errors during memory creation
        logger.info(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print(f"❌ Failed to setup memory: {e}")
        # Cleanup on error - delete the memory if it was partially created
        if memory_id:
            try:
                client.delete_memory_and_wait(memoryId=memory_id, max_wait=300)
                logger.info(f"Cleaned up memory: {memory_id}")
                print(f"🧹 Cleaned up partially created memory: {memory_id}")
            except Exception as cleanup_error:
                logger.info(f"Failed to clean up memory: {cleanup_error}")
                print(f"⚠️ Failed to clean up memory: {cleanup_error}")
        sys.exit(1)


if __name__ == "__main__":
    # Check for --action argument format
    if len(sys.argv) > 1 and "--action" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser(description="AgentCore Memory Management")
        parser.add_argument("--action", required=True, choices=["create", "seed", "delete", "verify"], 
                          help="Action to perform")
        parser.add_argument("--issue", help="Performance issue type (required for seed action)")
        parser.add_argument("--resolution", help="Resolution for the issue (required for seed action)")
        parser.add_argument("--memory-id", help="Memory ID to use")
        parser.add_argument("--ssm-param", default="/a2a/app/performance/agentcore/memory_id",
                          help="SSM parameter to retrieve memory_id from")
        
        args = parser.parse_args()
        
        if args.action == "create":
            # Create memory using setup_performance_memory function
            try:
                memory_id = setup_performance_memory()
                if memory_id:
                    print("✅ Memory created and configured successfully!")
                else:
                    print("❌ Failed to create memory")
                    sys.exit(1)
            except Exception as e:
                print(f"❌ Error creating memory: {e}")
                sys.exit(1)
                
        elif args.action == "seed":
            if not args.issue or not args.resolution:
                print("❌ Error: --issue and --resolution are required for seed action")
                sys.exit(1)
            
            # Get memory ID from SSM if not provided
            memory_id = args.memory_id
            if not memory_id:
                try:
                    memory_id = get_memory_id_from_ssm(args.ssm_param)
                    print(f"📖 Using memory ID from SSM: {memory_id}")
                except Exception:
                    print("❌ No memory ID provided and couldn't read from SSM parameter")
                    sys.exit(1)
            
            # Seed with the specific performance issue and resolution
            try:
                seed_specific_performance_memory(memory_id, args.issue, args.resolution)
                print("✅ Performance issue seeded successfully!")
            except Exception as e:
                print(f"❌ Error seeding performance issue: {e}")
                sys.exit(1)
                
        elif args.action == "delete":
            # Delete memory
            memory_id = args.memory_id
            if not memory_id:
                try:
                    memory_id = get_memory_id_from_ssm(args.ssm_param)
                    print(f"📖 Using memory ID from SSM: {memory_id}")
                except Exception:
                    print("❌ No memory ID provided and couldn't read from SSM parameter")
                    sys.exit(1)
            
            try:
                client.delete_memory_and_wait(memoryId=memory_id)
                delete_ssm_param(args.ssm_param)
                print("✅ Memory deleted successfully")
            except Exception as e:
                print(f"❌ Error deleting memory: {e}")
                
        elif args.action == "verify":
            # Verify memory configuration
            memory_id = args.memory_id
            if not memory_id:
                try:
                    memory_id = get_memory_id_from_ssm(args.ssm_param)
                except Exception as e:
                    print(f"❌ Error retrieving memory ID: {e}")
                    sys.exit(1)
            
            try:
                verify_memory_storage(memory_id)
            except Exception as e:
                print(f"❌ Error verifying memory: {e}")
    
    # Legacy argument handling for backward compatibility
    elif len(sys.argv) > 1 and sys.argv[1] == "delete":
        # Simple delete for compatibility
        try:
            memory_id = get_memory_id_from_ssm("/a2a/app/performance/agentcore/memory_id")
            client.delete_memory_and_wait(memoryId=memory_id)
            delete_ssm_param("/a2a/app/performance/agentcore/memory_id")
            print("✅ Memory deleted successfully")
        except Exception as e:
            print(f"❌ Error deleting memory: {e}")
    elif len(sys.argv) > 1 and sys.argv[1] == "verify":
        # Verify memory configuration
        try:
            memory_id = get_memory_id_from_ssm("/a2a/app/performance/agentcore/memory_id")
            verify_memory_storage(memory_id)
        except Exception as e:
            print(f"❌ Error verifying memory: {e}")
    elif len(sys.argv) > 1 and sys.argv[1] == "seed":
        # Legacy seed - no longer supported, direct users to new format
        print("❌ Legacy seed format no longer supported.")
        print("   Use: python3 setup_memory.py --action seed --issue <issue_type> --resolution <resolution>")
        sys.exit(1)
    else:
        # Default behavior - setup memory only
        memory_id = setup_performance_memory()
        if memory_id:
            verify_memory_storage(memory_id)
