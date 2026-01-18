#!/usr/bin/env python3
"""
NetOps AgentCore Runtime Test - Exactly matches customer-support-assistant reference
"""

import base64
import hashlib
from typing import Any, Optional
import webbrowser
import urllib
import json
from urllib.parse import urlencode
import requests
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


def generate_pkce_pair():
    """Generate PKCE code verifier and challenge for OAuth2 - exactly like reference"""
    code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode("utf-8").rstrip("=")
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode("utf-8")
        .rstrip("=")
    )
    return code_verifier, code_challenge


def invoke_endpoint(
    agent_arn: str,
    payload,
    session_id: str,
    bearer_token: Optional[str],
    endpoint_name: str = "DEFAULT",
) -> Any:
    """Invoke the AgentCore runtime endpoint - exactly like reference"""
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
    """Start an interactive chat session with the agent."""
    print(f"\n💬 Starting interactive chat session with a2a_performance_agent_runtime...")
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
@click.argument("agent_name", default="a2a_performance_agent_runtime")
@click.option("--prompt", "-p", default="Hello, can you help me analyze network performance issues?", help="Prompt to send to the agent")
@click.option("--interactive", "-i", is_flag=True, help="Start interactive chat session")
def main(agent_name: str, prompt: str, interactive: bool):
    """CLI tool to invoke a NetOps AgentCore by name - exactly like reference implementation."""
    print(f"🔍 Looking for agent: {agent_name}")
    
    runtime_config = read_config(".bedrock_agentcore.yaml")
    print(f"📖 Available agents: {list(runtime_config['agents'].keys())}")

    if agent_name not in runtime_config["agents"]:
        print(f"❌ Agent '{agent_name}' not found in config.")
        print(f"💡 Available agents: {', '.join(runtime_config['agents'].keys())}")
        print(f"💡 Try: python3 test/test_agent.py a2a_performance_agent_runtime")
        sys.exit(1)
    
    print(f"✅ Found agent: {agent_name}")

    code_verifier, code_challenge = generate_pkce_pair()
    state = str(uuid.uuid4())

    client_id = get_ssm_parameter("/a2a/app/performance/agentcore/web_client_id")
    cognito_domain = get_ssm_parameter("/a2a/app/performance/agentcore/cognito_domain")
    cognito_auth_scope = get_ssm_parameter("/a2a/app/performance/agentcore/cognito_auth_scope")
    redirect_uri = "https://example.com/auth/callback"

    login_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": f"openid email profile {cognito_auth_scope}",
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
        "state": state,
    }

    login_url = f"{cognito_domain}/oauth2/authorize?{urlencode(login_params)}"

    print("🔐 Open the following URL in a browser to authenticate:")
    print(login_url)
    webbrowser.open(login_url)

    auth_code_input = input("📥 Paste the full redirected URL or just the code: ").strip()
    
    # Parse the code from the input (handle both full URL and just the code)
    if "code=" in auth_code_input:
        # Extract code from URL parameters
        from urllib.parse import parse_qs, urlparse
        if auth_code_input.startswith("http"):
            # Full URL provided
            parsed_url = urlparse(auth_code_input)
            params = parse_qs(parsed_url.query)
            auth_code = params.get('code', [None])[0]
        else:
            # Just query string provided (like "code=xxx&state=yyy")
            params = parse_qs(auth_code_input)
            auth_code = params.get('code', [None])[0]
        
        if not auth_code:
            print("❌ Could not extract code from URL")
            sys.exit(1)
            
        print(f"✅ Extracted code: {auth_code[:10]}...")
    else:
        # Assume it's just the code
        auth_code = auth_code_input

    token_url = get_ssm_parameter("/a2a/app/performance/agentcore/cognito_token_url")
    response = requests.post(
        token_url,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30  # Add timeout to prevent indefinite hanging requests
    )

    if response.status_code != 200:
        print(f"❌ Failed to exchange code: {response.text}")
        sys.exit(1)

    access_token = response.json()["access_token"]
    print("✅ Access token acquired.")

    agent_arn = runtime_config["agents"][agent_name]["bedrock_agentcore"]["agent_arn"]
    session_id = str(uuid.uuid4())

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
