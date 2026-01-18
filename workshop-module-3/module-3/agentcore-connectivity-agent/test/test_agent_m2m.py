#!/usr/bin/env python3
"""
NetOps AgentCore Runtime Test - Machine-to-Machine Authentication
This script uses client_credentials flow to avoid browser authentication
"""

import json
import requests
import urllib.parse
import uuid
import sys
import os
import click
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure we can import local utilities
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.utils import get_aws_region, read_config, get_ssm_parameter


def get_machine_access_token():
    """Get access token using client_credentials flow (M2M authentication)"""
    try:
        # Get machine client credentials from SSM
        client_id = get_ssm_parameter("/a2a/app/performance/agentcore/machine_client_id")
        client_secret = get_ssm_parameter("/a2a/app/performance/agentcore/machine_client_secret")
        token_url = get_ssm_parameter("/a2a/app/performance/agentcore/cognito_token_url")
        auth_scope = get_ssm_parameter("/a2a/app/performance/agentcore/cognito_auth_scope")
        
        print(f"🔐 Using machine client ID: {client_id}")
        print(f"🔗 Token URL: {token_url}")
        print(f"📋 Scope: {auth_scope}")
        
        # Request token using client_credentials flow
        response = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": auth_scope
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30
        )
        
        if response.status_code == 200:
            token_data = response.json()
            print("✅ Machine-to-machine token acquired successfully")
            return token_data["access_token"]
        else:
            print(f"❌ Failed to get M2M token: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting M2M token: {e}")
        return None


def invoke_endpoint(
    agent_arn: str,
    payload,
    session_id: str,
    bearer_token: str,
    endpoint_name: str = "DEFAULT",
) -> None:
    """Invoke the AgentCore runtime endpoint"""
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
        print(f"🚀 Invoking agent with M2M authentication...")
        response = requests.post(
            url,
            params={"qualifier": endpoint_name},
            headers=headers,
            json=body,
            timeout=300,
            stream=True,
        )
        
        if response.status_code != 200:
            print(f"❌ Error response: {response.status_code} - {response.text}")
            return
        
        print(f"✅ Agent response (status {response.status_code}):")
        print("-" * 50)
        
        response_received = False
        
        # Process streaming response
        for line in response.iter_lines(chunk_size=8192, decode_unicode=True):
            if line:
                response_received = True
                
                if line.startswith("data: "):
                    content = line[6:].strip('"')
                    content = content.replace('\\n', '\n')
                    content = content.replace('\\"', '"')
                    content = content.replace('\\\\', '\\')
                    print(content, end="", flush=True)
                    
                elif line.strip() in ["data: [DONE]", "[DONE]"]:
                    print("\n", flush=True)
                    break
        
        if not response_received:
            print("⚠️  No response received from agent")

    except requests.exceptions.Timeout:
        print("⏰ Request timed out after 5 minutes")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to invoke agent endpoint: {str(e)}")
    except KeyboardInterrupt:
        print("\n🛑 Request interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")


def interactive_chat_session(agent_arn: str, bearer_token: str, session_id: str):
    """Start an interactive chat session with the agent using M2M authentication."""
    print(f"\n💬 Starting interactive M2M chat session...")
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
@click.argument("agent_name", default="a2a_troubleshooting_agent_runtime")
@click.option("--prompt", "-p", default="Hello, can you help me analyze network troubleshooting issues?", help="Prompt to send to the agent")
@click.option("--interactive", "-i", is_flag=True, help="Start interactive chat session")
def main(agent_name: str, prompt: str, interactive: bool):
    """CLI tool to test NetOps AgentCore using machine-to-machine authentication."""
    print(f"🤖 Testing agent with M2M authentication: {agent_name}")
    
    # Read runtime configuration
    runtime_config = read_config(".bedrock_agentcore.yaml")
    print(f"📖 Available agents: {list(runtime_config['agents'].keys())}")

    if agent_name not in runtime_config["agents"]:
        print(f"❌ Agent '{agent_name}' not found in config.")
        print(f"💡 Available agents: {', '.join(runtime_config['agents'].keys())}")
        sys.exit(1)
    
    print(f"✅ Found agent: {agent_name}")

    # Get machine-to-machine access token
    access_token = get_machine_access_token()
    if not access_token:
        print("❌ Failed to get M2M access token")
        sys.exit(1)

    # Get agent ARN and create session
    agent_arn = runtime_config["agents"][agent_name]["bedrock_agentcore"]["agent_arn"]
    session_id = str(uuid.uuid4())
    
    print(f"🔗 Agent ARN: {agent_arn}")
    print(f"🆔 Session ID: {session_id}")

    if interactive:
        # Start interactive chat session
        interactive_chat_session(
            agent_arn=agent_arn,
            bearer_token=access_token,
            session_id=session_id,
        )
    else:
        # Single message mode
        invoke_endpoint(
            agent_arn=agent_arn,
            payload=json.dumps({"prompt": prompt, "actor_id": "DEFAULT"}),
            bearer_token=access_token,
            session_id=session_id,
        )


if __name__ == "__main__":
    main()
