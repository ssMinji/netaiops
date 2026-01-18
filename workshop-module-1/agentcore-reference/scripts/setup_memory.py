#!/usr/bin/python
import click
import boto3
import sys
import os
from botocore.exceptions import ClientError
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType
from utils import get_aws_region

# Force us-east-1 region for all operations
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
REGION = "us-east-1"
ssm = boto3.client("ssm", region_name=REGION)
memory_client = MemoryClient()


def store_memory_id_in_ssm(param_name: str, memory_id: str):
    ssm.put_parameter(Name=param_name, Value=memory_id, Type="String", Overwrite=True)
    click.echo(f"🔐 Stored memory_id in SSM: {param_name}")


def get_memory_id_from_ssm(param_name: str):
    try:
        response = ssm.get_parameter(Name=param_name)
        return response["Parameter"]["Value"]
    except ClientError as e:
        raise click.ClickException(f"❌ Could not retrieve memory_id from SSM: {e}")


def delete_ssm_param(param_name: str):
    try:
        ssm.delete_parameter(Name=param_name)
        click.echo(f"🧹 Deleted SSM parameter: {param_name}")
    except ClientError as e:
        click.echo(f"⚠️ Failed to delete SSM parameter: {e}")


@click.group()
@click.pass_context
def cli(ctx):
    """AgentCore Memory Management CLI.

    Create and delete AgentCore memory resources for the troubleshooting application.
    """
    ctx.ensure_object(dict)


@cli.command()
@click.option(
    "--name", default="TroubleshootingAgentMemory", help="Name of the memory resource"
)
@click.option(
    "--ssm-param",
    default="/app/troubleshooting/agentcore/memory_id",
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

    strategies = [
        {
            StrategyType.SEMANTIC.value: {
                "name": "permission_extractor",
                "description": "Extracts and stores user permissions (security-group-ops, nacl-ops, routing-ops)",
                "namespaces": ["troubleshooting/user/{actorId}/permissions"],
            },
        },
        {
            StrategyType.SUMMARY.value: {
                "name": "session_summary",
                "description": "Captures summaries of tasks performed, tools invoked and resources changed",
                "namespaces": ["troubleshooting/user/{actorId}/{sessionId}"],
            },
        },
        {
            StrategyType.USER_PREFERENCE.value: {
                "name": "operational_facts",
                "description": "Captures operational facts and network troubleshooting context",
                "namespaces": ["troubleshooting/user/{actorId}/facts"],
            },
        },
    ]

    try:
        click.echo("🔄 Creating memory resource...")
        memory = memory_client.create_memory_and_wait(
            name=name,
            strategies=strategies,
            description="Memory for troubleshooting agent - stores user permissions, session summaries, and operational facts",
            event_expiry_days=event_expiry_days,
        )
        memory_id = memory["id"]
        click.echo(f"✅ Memory created successfully: {memory_id}")

    except Exception as e:
        if "already exists" in str(e):
            click.echo("📋 Memory already exists, finding existing resource...")
            memories = memory_client.list_memories()
            memory_id = next(
                (m["id"] for m in memories if name in m.get("name", "")), None
            )
            if memory_id:
                click.echo(f"✅ Using existing memory: {memory_id}")
            else:
                click.echo("❌ Could not find existing memory resource", err=True)
                sys.exit(1)
        else:
            click.echo(f"❌ Error creating memory: {str(e)}", err=True)
            sys.exit(1)

    try:
        store_memory_id_in_ssm(ssm_param, memory_id)
        click.echo("🎉 Memory setup completed successfully!")
        click.echo(f"   Memory ID: {memory_id}")
        click.echo(f"   SSM Parameter: {ssm_param}")
        click.echo(f"")
        click.echo(f"📋 Memory Strategies Configured:")
        click.echo(f"   🔒 Permission Extractor: Stores security-group-ops, nacl-ops, routing-ops permissions")
        click.echo(f"   📊 Session Summary: Tracks tasks, tools, and resource changes per session")
        click.echo(f"   🧠 Operational Facts: Stores network troubleshooting context")

    except Exception as e:
        click.echo(f"⚠️  Memory created but failed to store in SSM: {str(e)}", err=True)


@cli.command()
@click.option(
    "--memory-id",
    help="Memory ID to delete (if not provided, will read from SSM parameter)",
)
@click.option(
    "--ssm-param",
    default="/app/troubleshooting/agentcore/memory_id",
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
        memory_client.delete_memory(memory_id=memory_id)
        click.echo(f"✅ Memory deleted successfully: {memory_id}")
    except Exception as e:
        click.echo(f"❌ Error deleting memory: {str(e)}", err=True)
        sys.exit(1)

    # Always delete SSM parameter
    delete_ssm_param(ssm_param)
    click.echo("🎉 Memory and SSM parameter deleted successfully")


def setup_troubleshooting_memory():
    """Simplified function for compatibility - creates ONE memory with all strategies"""
    click.echo("🧠 Setting up Troubleshooting Agent Memory...")
    
    name = "TroubleshootingAgentMemory"
    ssm_param = "/app/troubleshooting/agentcore/memory_id"
    event_expiry_days = 30
    
    strategies = [
        {
            StrategyType.SEMANTIC.value: {
                "name": "permission_extractor",
                "description": "Extracts and stores user permissions (security-group-ops, nacl-ops, routing-ops)",
                "namespaces": ["troubleshooting/user/{actorId}/permissions"],
            },
        },
        {
            StrategyType.SUMMARY.value: {
                "name": "session_summary",
                "description": "Captures summaries of tasks performed, tools invoked and resources changed",
                "namespaces": ["troubleshooting/user/{actorId}/{sessionId}"],
            },
        },
        {
            StrategyType.USER_PREFERENCE.value: {
                "name": "operational_facts",
                "description": "Captures operational facts and network troubleshooting context",
                "namespaces": ["troubleshooting/user/{actorId}/facts"],
            },
        },
    ]

    try:
        memory = memory_client.create_memory_and_wait(
            name=name,
            strategies=strategies,
            description="Memory for troubleshooting agent - stores user permissions, session summaries, and operational facts",
            event_expiry_days=event_expiry_days,
        )
        memory_id = memory["id"]
        
        store_memory_id_in_ssm(ssm_param, memory_id)
        
        print("✅ Troubleshooting Agent Memory setup complete!")
        print(f"   Memory ID: {memory_id}")
        print(f"   SSM Parameter: {ssm_param}")
        return memory_id
        
    except Exception as e:
        if "already exists" in str(e):
            memories = memory_client.list_memories()
            memory_id = next(
                (m["id"] for m in memories if name in m.get("name", "")), None
            )
            if memory_id:
                store_memory_id_in_ssm(ssm_param, memory_id)
                print("✅ Using existing memory")
                print(f"   Memory ID: {memory_id}")
                return memory_id
        
        print(f"❌ Failed to setup memory: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "delete":
        # Simple delete for compatibility
        try:
            memory_id = get_memory_id_from_ssm("/app/troubleshooting/agentcore/memory_id")
            memory_client.delete_memory(memory_id=memory_id)
            delete_ssm_param("/app/troubleshooting/agentcore/memory_id")
            print("✅ Memory deleted successfully")
        except Exception as e:
            print(f"❌ Error deleting memory: {e}")
    else:
        setup_troubleshooting_memory()
