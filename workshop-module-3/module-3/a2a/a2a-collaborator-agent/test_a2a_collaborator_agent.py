#!/usr/bin/env python3
"""
A2A Collaborator AgentCore Runtime Test - Machine-to-Machine Authentication
"""

import urllib
import json
import requests
import uuid
import sys
import os
import click
import logging
import asyncio
from typing import Any, Optional
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure we can import local utilities
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.utils import get_aws_region, read_config, get_ssm_parameter
from access_token import get_gateway_access_token


def invoke_endpoint(
    agent_arn: str,
    payload,
    session_id: str,
    bearer_token: Optional[str],
    endpoint_name: str = "DEFAULT",
) -> Any:
    """Invoke the AgentCore runtime endpoint with proper streaming"""
    escaped_arn = urllib.parse.quote(agent_arn, safe="")
    url = f"https://bedrock-agentcore.{get_aws_region()}.amazonaws.com/runtimes/{escaped_arn}/invocations"

    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }

    try:
        body = json.loads(payload) if isinstance(payload, str) else payload
    except json.JSONDecodeError:
        body = {"payload": payload}

    try:
        print(f"🤖 A2A Collaborator Agent: ", end="", flush=True)
        
        # Clean streaming - minimal debug output
        response = requests.post(
            url,
            params={"qualifier": endpoint_name},
            headers=headers,
            json=body,
            timeout=300,  # 5 minute timeout
            stream=True,
        )
        
        if response.status_code != 200:
            print(f"❌ Error response: {response.text}")
            return
        
        response_received = False
        
        # Improved streaming with buffer handling
        for line in response.iter_lines(chunk_size=8192, decode_unicode=True):
            if line:
                response_received = True
                
                if line.startswith("data: "):
                    # Extract and clean the content
                    content = line[6:].strip('"')
                    content = content.replace('\\n', '\n')
                    content = content.replace('\\"', '"')
                    content = content.replace('\\\\', '\\')
                    
                    # Force immediate output with flush
                    print(content, end="", flush=True)
                    
                elif line.strip() in ["data: [DONE]", "[DONE]"]:
                    # Stream completion
                    print("\n", flush=True)
                    break
                elif line.startswith("event: "):
                    # Skip event lines silently
                    continue
                elif line.strip() == "":
                    # Skip empty lines
                    continue
        
        if not response_received:
            print("⚠️  No response received from agent")

    except requests.exceptions.Timeout:
        print("⏰ Request timed out after 5 minutes")
        print("💡 The agent may still be processing. Check CloudWatch logs for details.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to invoke agent endpoint: {str(e)}")
        raise
    except KeyboardInterrupt:
        print("\n🛑 Request interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error during response processing: {str(e)}")
        raise


def interactive_chat_session(agent_arn: str, bearer_token: str, session_id: str):
    """Start an interactive chat session with the a2a collaborator agent."""
    print(f"\n💬 Starting interactive chat session with a2a_collaborator_agent_runtime...")
    print(f"🔗 Session ID: {session_id}")
    print("Type 'quit' or 'exit' to end the session")
    print("-" * 50)
    
    while True:
        try:
            user_input = input(f"\n👤 You: ").strip()
            
            if user_input.lower() in ['quit', 'exit']:
                print("\n👋 Ending chat session. Goodbye!")
                break
            elif not user_input:
                continue
            
            # Send message to agent
            invoke_endpoint(
                agent_arn=agent_arn,
                payload=json.dumps({"prompt": user_input, "actor_id": "DEFAULT"}),
                bearer_token=bearer_token,
                session_id=session_id,
            )
            
        except KeyboardInterrupt:
            print("\n\n👋 Chat session interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"❌ Chat error: {e}")


@click.command()
@click.argument("agent_name", default="a2a_collaborator_agent_runtime")
@click.option("--aws-account-id", required=True, help="AWS Account ID")
@click.option("--agentcore-runtime-id", required=True, help="AgentCore Runtime ID")
@click.option("--prompt", "-p", default=None, help="Prompt to send to the agent")
@click.option("--interactive", "-i", is_flag=True, help="Start interactive chat session")
def main(agent_name: str, aws_account_id: str, agentcore_runtime_id: str, prompt: Optional[str], interactive: bool):
    """CLI tool to test the A2A Collaborator AgentCore Runtime using M2M authentication."""
    asyncio.run(async_main(agent_name, aws_account_id, agentcore_runtime_id, prompt, interactive))


async def async_main(agent_name: str, aws_account_id: str, agentcore_runtime_id: str, prompt: Optional[str], interactive: bool):
    """Async main function that uses M2M authentication."""
    
    # Construct the agent ARN using the provided parameters
    agent_arn = f"arn:aws:bedrock-agentcore:us-east-1:{aws_account_id}:runtime/{agentcore_runtime_id}"
    
    print(f"🔍 Testing A2A Collaborator Agent: {agent_name}")
    print(f"🎯 Agent ARN: {agent_arn}")

    try:
        # Use M2M authentication like invoke_agent.py
        print("🔐 Getting M2M access token...")
        bearer_token = await get_gateway_access_token()
        print("✅ Access token acquired via M2M authentication.")
        
        # Generate session ID that meets the 33+ character requirement (exactly like invoke_agent.py)
        from datetime import datetime, timezone
        timestamp = int(datetime.now(timezone.utc).timestamp())
        session_id = f"invoke_session_{timestamp}_{'x' * 10}"
        
        print(f"📝 Generated Session ID: {session_id} (length: {len(session_id)})")
        
        if interactive:
            # Start interactive chat session
            interactive_chat_session(
                agent_arn=agent_arn,
                bearer_token=bearer_token,
                session_id=session_id,
            )
        elif prompt:
            # Single message mode with provided prompt
            invoke_endpoint(
                agent_arn=agent_arn,
                payload=json.dumps({"prompt": prompt, "actor_id": "DEFAULT"}),
                bearer_token=bearer_token,
                session_id=session_id,
            )
        else:
            # Default behavior: interactive mode (like test_agent.py)
            interactive_chat_session(
                agent_arn=agent_arn,
                bearer_token=bearer_token,
                session_id=session_id,
            )
            
    except Exception as e:
        print(f"❌ Authentication error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
