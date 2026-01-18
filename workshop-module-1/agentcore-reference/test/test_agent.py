#!/usr/bin/env python3

"""Troubleshooting AgentCore Runtime Test"""

import base64

import hashlib

from typing import Any, Optional

import webbrowser

import urllib

import json

from urllib.parse import urlparse, urlencode

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



def get_aws_region() -> str:

    """Get the current AWS region."""

    # Try to get from environment first

    region = os.environ.get('AWS_DEFAULT_REGION')

    if region:

        return region

    

    # Try to get from boto3 session

    try:

        import boto3

        session = boto3.Session()

        return session.region_name or 'us-east-1'

    except Exception:

        return 'us-east-1'



def get_ssm_parameter(parameter_name: str, default=None):

    """Get parameter from AWS Systems Manager Parameter Store"""

    try:

        import boto3

        ssm = boto3.client('ssm', region_name=get_aws_region())

        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)

        return response['Parameter']['Value']

    except Exception as e:

        print(f"Warning: Could not retrieve SSM parameter {parameter_name}: {e}")

        return default



def read_config(config_file: str):

    """Read configuration from YAML file"""

    try:

        import yaml

        if os.path.exists(config_file):

            with open(config_file, 'r') as f:

                return yaml.safe_load(f) or {}

        else:

            print(f"Warning: Configuration file {config_file} not found")

            return {}

    except Exception as e:

        print(f"Error reading configuration file {config_file}: {e}")

        return {}



def generate_pkce_pair():

    """Generate PKCE code verifier and challenge for OAuth2"""

    code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode("utf-8").rstrip("=")

    code_challenge = (

        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())

        .decode("utf-8")

        .rstrip("=")

    )

    return code_verifier, code_challenge



def automated_cognito_login(login_url: str, username: str, password: str) -> Optional[str]:

    """

    Automate Cognito Hosted UI login and return the authorization code.

    

    Args:

        login_url: The full OAuth2 authorization URL

        username: Cognito username (email)

        password: Cognito password

    

    Returns:

        Authorization code if successful, None otherwise

    """

    import re

    from urllib.parse import parse_qs, urlparse as parse_url

    

    session = requests.Session()

    

    try:

        print("🔐 Authenticating with Cognito...")

        

        # Step 1: GET the login page to get CSRF token and form action

        response = session.get(login_url, allow_redirects=True)

        

        if response.status_code != 200:

            print(f"❌ Failed to load login page: HTTP {response.status_code}")

            return None

        

        # Step 2: Parse the login form to find CSRF token

        csrf_token = None

        csrf_patterns = [

            r'<input[^>]*name=["\']_csrf["\'][^>]*value=["\']([^"\']+)["\']',

            r'<input[^>]*value=["\']([^"\']+)["\'][^>]*name=["\']_csrf["\']',

        ]

        

        for pattern in csrf_patterns:

            match = re.search(pattern, response.text)

            if match:

                csrf_token = match.group(1)

                break

        

        # Step 3: Submit login credentials

        # Cognito Hosted UI typically posts to the same URL or /login endpoint

        login_post_url = response.url

        

        login_data = {

            'username': username,

            'password': password,

        }

        

        # Add CSRF token if found

        if csrf_token:

            login_data['_csrf'] = csrf_token

        

        # Submit the login form

        response = session.post(

            login_post_url,

            data=login_data,

            allow_redirects=True,

            headers={

                'Content-Type': 'application/x-www-form-urlencoded',

                'Referer': login_post_url

            }

        )

        

        # Step 4: Check if we got redirected to the callback URL with a code

        final_url = response.url

        

        # Check if we're at the redirect URI with a code

        if 'example.com/auth/callback' in final_url and 'code=' in final_url:

            parsed = parse_url(final_url)

            params = parse_qs(parsed.query)

            auth_code = params.get('code', [None])[0]

            

            if auth_code:

                print("✅ Successfully authenticated with Cognito")

                return auth_code

        

        # Check for error messages in the response

        if 'incorrect' in response.text.lower() or 'invalid' in response.text.lower():

            print("❌ Authentication failed: Invalid username or password")

            return None

        

        # If we're still on a Cognito page, authentication likely failed

        if 'amazoncognito.com' in final_url:

            print("❌ Authentication failed: Still on Cognito login page")

            print(f"   Final URL: {final_url}")

            return None

        

        print("❌ Unexpected response during authentication")

        print(f"   Final URL: {final_url}")

        return None

        

    except Exception as e:

        print(f"❌ Error during automated login: {e}")

        return None



def invoke_endpoint(

    agent_arn: str,

    payload,

    session_id: str,

    bearer_token: Optional[str],

    endpoint_name: str = "DEFAULT",

) -> Any:

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

        response = requests.post(

            url,

            params={"qualifier": endpoint_name},

            headers=headers,

            json=body,

            timeout=300,

            stream=True,

        )

        

        if response.status_code != 200:

            print(f"❌ Error response: {response.text}")

            return

        

        response_received = False

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

                elif line.startswith("event: "):

                    continue

                elif line.strip() == "":

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



def check_connectivity_restored():

    """Check if connectivity between reporting.examplecorp.com and database.examplecorp.com has been restored."""

    try:

        import boto3

        region = get_aws_region()

        ec2_client = boto3.client('ec2', region_name=region)

        

        print("\n🔍 Checking if connectivity has been restored...")

        

        try:

            paths_response = ec2_client.describe_network_insights_paths()

            network_paths = paths_response.get('NetworkInsightsPaths', [])

            print(f"✓ Found {len(network_paths)} existing network insight paths")

            

            path_analyses = []

            connectivity_restored = False

            

            for path in network_paths:

                path_id = path.get('NetworkInsightsPathId')

                source = path.get('Source', 'Unknown')

                destination = path.get('Destination', 'Unknown')

                print(f"  📍 Analyzing path: {path_id}")

                print(f"     Source: {source}")

                print(f"     Destination: {destination}")

                

                try:

                    analyses_response = ec2_client.describe_network_insights_analyses(

                        NetworkInsightsPathId=path_id

                    )

                    analyses = analyses_response.get('NetworkInsightsAnalyses', [])

                    

                    if analyses:

                        latest_analysis = sorted(

                            analyses, 

                            key=lambda x: x.get('StartDate', ''), 

                            reverse=True

                        )[0]

                        

                        analysis_id = latest_analysis.get('NetworkInsightsAnalysisId')

                        status = latest_analysis.get('Status', 'unknown')

                        network_path_found = latest_analysis.get('NetworkPathFound', False)

                        

                        if status == 'succeeded' and network_path_found:

                            reachability_status = 'Reachable'

                            connectivity_restored = True

                        elif status == 'succeeded' and not network_path_found:

                            reachability_status = 'Not reachable'

                        else:

                            reachability_status = f'Analysis {status}'

                        

                        path_analyses.append({

                            'path_id': path_id,

                            'analysis_id': analysis_id,

                            'status': reachability_status,

                            'source': source,

                            'destination': destination

                        })

                        print(f"     Status: {reachability_status}")

                    else:

                        print(f"     No analyses found for path {path_id}")

                        path_analyses.append({

                            'path_id': path_id,

                            'analysis_id': 'no-analysis',

                            'status': 'No analysis available',

                            'source': source,

                            'destination': destination

                        })

                except Exception as analysis_error:

                    print(f"     ⚠ Error getting analysis for path {path_id}: {analysis_error}")

                    path_analyses.append({

                        'path_id': path_id,

                        'analysis_id': 'error',

                        'status': 'Analysis error',

                        'source': source,

                        'destination': destination

                    })

            

            if not network_paths:

                print("  No existing network insight paths found, checking security groups...")

                sg_response = ec2_client.describe_security_groups()

                security_groups = sg_response.get('SecurityGroups', [])

                database_sg_id = None

                

                for sg in security_groups:

                    sg_name = sg.get('GroupName', '')

                    if 'sample-application-DatabaseSecurityGroup' in sg_name:

                        database_sg_id = sg.get('GroupId')

                        break

                

                if database_sg_id:

                    sg_details = ec2_client.describe_security_groups(GroupIds=[database_sg_id])

                    sg_info = sg_details['SecurityGroups'][0]

                    mysql_rules_found = []

                    

                    for rule in sg_info.get('IpPermissions', []):

                        protocol = rule.get('IpProtocol')

                        from_port = rule.get('FromPort')

                        to_port = rule.get('ToPort')

                        

                        if protocol == 'tcp' and from_port == 3306 and to_port == 3306:

                            for ip_range in rule.get('IpRanges', []):

                                cidr = ip_range.get('CidrIp', '')

                                if (cidr == '10.1.0.0/16' or cidr.startswith('10.1.') or 

                                    cidr == '0.0.0.0/0'):

                                    mysql_rules_found.append(cidr)

                    

                    if mysql_rules_found:

                        connectivity_restored = True

                        path_analyses.append({

                            'path_id': database_sg_id,

                            'analysis_id': 'security-group-check',

                            'status': 'Reachable',

                            'source': 'reporting.examplecorp.com',

                            'destination': 'database.examplecorp.com'

                        })

                    else:

                        path_analyses.append({

                            'path_id': database_sg_id,

                            'analysis_id': 'security-group-check',

                            'status': 'Not reachable',

                            'source': 'reporting.examplecorp.com',

                            'destination': 'database.examplecorp.com'

                        })

            

            path_analysis = {

                'connectivity_restored': connectivity_restored,

                'path_analyses': path_analyses,

                'total_paths_checked': len(path_analyses),

                'analysis_timestamp': __import__('datetime').datetime.now().isoformat(),

                'validation_method': 'network_insights_path_analysis'

            }

            

            if connectivity_restored:

                print("✅ Connectivity restored based on path analysis")

            else:

                print("❌ Connectivity not restored based on path analysis")

            

            return connectivity_restored, path_analysis

            

        except Exception as path_error:

            print(f"⚠ Error getting network insight paths: {path_error}")

            return False, None

            

    except Exception as e:

        print(f"⚠ Error checking connectivity: {e}")

        return False, None



def add_ticket_correspondence():

    """Add correspondence to the most recent support ticket indicating connectivity is restored."""

    try:

        import boto3

        

        connectivity_restored, path_analysis = check_connectivity_restored()

        if not connectivity_restored:

            print("⚠ Connectivity not restored yet - skipping correspondence update")

            print("💡 Please restore the security group rule first:")

            print("   aws ec2 authorize-security-group-ingress --group-id <SG-ID> --protocol tcp --port 3306 --cidr 10.1.0.0/16")

            return

        

        region = get_aws_region()

        ssm_client = boto3.client('ssm', region_name=region)

        lambda_client = boto3.client('lambda', region_name=region)

        

        print("\n🎫 Adding correspondence to support ticket...")

        

        try:

            response = ssm_client.get_parameter(Name='/examplecorp/support/api-gateway-url')

            api_gateway_url = response['Parameter']['Value']

            print(f"✓ Found support API Gateway URL: {api_gateway_url}")

            

            import urllib.request

            req = urllib.request.Request(f"{api_gateway_url}/tickets")

            req.add_header('User-Agent', 'AgentCoreRuntime/1.0')

            req.add_header('Accept', 'application/json')

            print(f"🔍 Fetching tickets from: {api_gateway_url}/tickets")

            

            with urllib.request.urlopen(req, timeout=30) as response:

                if response.status == 200:

                    result = json.loads(response.read().decode('utf-8'))

                    tickets = result.get('tickets', [])

                    print(f"✓ Retrieved {len(tickets)} tickets from API")

                    

                    if tickets:

                        target_ticket = None

                        for ticket in sorted(tickets, key=lambda x: x.get('created_at', ''), reverse=True):

                            if "ExampleCorp - Reporting down for Imaging Platform, Triaging using AgentCoreRuntime" in ticket.get('subject', ''):

                                target_ticket = ticket

                                break

                        

                        if not target_ticket:

                            print("⚠ No ticket found with subject 'EXAMPLECORP - Reporting down for Imaging Platform, Triaging using AgentCoreRuntime'")

                            print("  Available tickets:")

                            for ticket in tickets[:3]:

                                print(f"    - {ticket.get('id')}: {ticket.get('subject', 'No subject')}")

                            return

                        

                        ticket_id = target_ticket.get('id')

                        print(f"✓ Found ticket to update: {ticket_id} - {target_ticket.get('subject')}")

                        

                        base_message = "connectivity between reporting.examplecorp.com and database.examplecorp.com is restored for Imaging Platform"

                        

                        if path_analysis and path_analysis.get('path_analyses'):

                            detailed_message = f"""{base_message}



The following path analysis were used to check and restore the connectivity :

"""

                            for path_info in path_analysis['path_analyses']:

                                path_id = path_info.get('path_id', 'unknown')

                                status = path_info.get('status', 'unknown')

                                detailed_message += f"Path ID : {path_id} : Status : {status}\n\n"

                            detailed_message = detailed_message.rstrip()

                        else:

                            detailed_message = f"""{base_message}



The following path analysis were used to check and restore the connectivity :

Path ID : connectivity-check : Status : Reachable"""

                        

                        correspondence_data = {

                            "author": "AgentCoreRuntime",

                            "message": detailed_message,

                            "message_type": "system"

                        }

                        

                        data = json.dumps(correspondence_data).encode('utf-8')

                        req = urllib.request.Request(

                            f"{api_gateway_url}/tickets/{ticket_id}/correspondence",

                            data=data,

                            headers={

                                'Content-Type': 'application/json',

                                'User-Agent': 'AgentCoreRuntime/1.0'

                            }

                        )

                        req.get_method = lambda: 'POST'

                        

                        with urllib.request.urlopen(req, timeout=30) as response:

                            if response.status == 201:

                                print("✅ Successfully added correspondence to support ticket")

                                print("   Message: connectivity between reporting.examplecorp.com and database.examplecorp.com is restored for Imaging Platform")

                                print("   Author: AgentCoreRuntime")

                                

                                try:

                                    close_data = json.dumps({"status": "closed"}).encode('utf-8')

                                    close_req = urllib.request.Request(

                                        f"{api_gateway_url}/tickets/{ticket_id}",

                                        data=close_data,

                                        headers={

                                            'Content-Type': 'application/json',

                                            'User-Agent': 'AgentCoreRuntime/1.0'

                                        }

                                    )

                                    close_req.get_method = lambda: 'PUT'

                                    

                                    with urllib.request.urlopen(close_req, timeout=30) as close_response:

                                        if close_response.status in [200, 204]:

                                            print("✅ Successfully closed support ticket")

                                        else:

                                            print(f"⚠ Failed to close ticket: HTTP {close_response.status}")

                                except Exception as close_error:

                                    print(f"⚠ Error closing ticket: {close_error}")

                            else:

                                print(f"⚠ API Gateway returned status {response.status}")

                    else:

                        print("⚠ No tickets found to update")

                else:

                    print(f"⚠ Failed to get tickets: HTTP {response.status}")

                    

        except Exception as api_error:

            print(f"⚠ API Gateway method failed: {api_error}")

            print("  Trying direct Lambda invocation...")

            # Lambda fallback code would go here (keeping it short for brevity)

            

    except Exception as e:

        print(f"⚠ Failed to add ticket correspondence: {e}")



def interactive_chat_session(agent_arn: str, bearer_token: str, session_id: str):

    """Start an interactive chat session with the agent."""

    print(f"\n💬 Starting interactive chat session with troubleshooting_agent_runtime...")

    print(f"🔗 Session ID: {session_id}")

    print("Type 'quit' or 'exit' to end the session")

    print("-" * 50)

    

    while True:

        try:

            user_input = input(f"\n👤 You: ").strip()

            

            if user_input.lower() in ['quit', 'exit']:

                print("\n👋 Ending chat session. Goodbye!")

                add_ticket_correspondence()

                break

            elif not user_input:

                continue

            

            invoke_endpoint(

                agent_arn=agent_arn,

                payload=json.dumps({"prompt": user_input, "actor_id": "DEFAULT"}),

                bearer_token=bearer_token,

                session_id=session_id,

            )

            

        except KeyboardInterrupt:

            print("\n\n👋 Chat session interrupted. Goodbye!")

            add_ticket_correspondence()

            break

        except Exception as e:

            print(f"❌ Chat error: {e}")



@click.command()

@click.argument("agent_name", default="troubleshooting_agent_runtime")

@click.option("--prompt", "-p", default="Hello, can you help me analyze VPC connectivity issues?", 

              help="Prompt to send to the agent")

@click.option("--interactive", "-i", is_flag=True, help="Start interactive chat session")

def main(agent_name: str, prompt: str, interactive: bool):

    """CLI tool to invoke a NetOps AgentCore by name."""

    print(f"🔍 Looking for agent: {agent_name}")

    

    runtime_config = read_config(".bedrock_agentcore.yaml")

    print(f"📖 Available agents: {list(runtime_config['agents'].keys())}")

    

    if agent_name not in runtime_config["agents"]:

        print(f"❌ Agent '{agent_name}' not found in config.")

        print(f"💡 Available agents: {', '.join(runtime_config['agents'].keys())}")

        print(f"💡 Try: python3 test/test_agent.py troubleshooting_agent_runtime")

        sys.exit(1)

    

    print(f"✅ Found agent: {agent_name}")

    

    current_region = get_aws_region()

    print(f"🌍 Using AWS region: {current_region}")

    print(f"🔍 Checking SSM parameters...")

    

    code_verifier, code_challenge = generate_pkce_pair()

    state = str(uuid.uuid4())

    

    client_id = get_ssm_parameter("/app/troubleshooting/agentcore/web_client_id")

    cognito_domain = get_ssm_parameter("/app/troubleshooting/agentcore/cognito_domain")

    cognito_auth_scope = get_ssm_parameter("/app/troubleshooting/agentcore/cognito_auth_scope")

    

    if not client_id:

        print("❌ Missing SSM parameter: /app/troubleshooting/agentcore/web_client_id")

        print("💡 Make sure you've run: ./scripts/prereq.sh")

        sys.exit(1)

    

    if not cognito_domain:

        print("❌ Missing SSM parameter: /app/troubleshooting/agentcore/cognito_domain")

        print("💡 Make sure you've run: ./scripts/prereq.sh")

        sys.exit(1)

    

    if not cognito_auth_scope:

        print("❌ Missing SSM parameter: /app/troubleshooting/agentcore/cognito_auth_scope")

        print("💡 Make sure you've run: ./scripts/prereq.sh")

        sys.exit(1)

    

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

    

    # AUTOMATED AUTHENTICATION FLOW

    print("\n" + "=" * 80)

    print("🔐 AUTHENTICATION REQUIRED")

    print("=" * 80)

    print("\nEnter your Cognito credentials to authenticate.")

    

    username = input("📧 Cognito Username (email): ").strip()

    password = input("🔑 Cognito Password: ").strip()

    

    if not username or not password:

        print("❌ Username and password are required")

        sys.exit(1)

    

    # Attempt automated login

    auth_code = automated_cognito_login(login_url, username, password)

    

    if not auth_code:

        print("\n❌ Automated login failed. Please try again or check your credentials.")

        sys.exit(1)

    

    token_url = get_ssm_parameter("/app/troubleshooting/agentcore/cognito_token_url")

    if not token_url:

        print("❌ Missing SSM parameter: /app/troubleshooting/agentcore/cognito_token_url")

        print("💡 Make sure you've run: ./scripts/prereq.sh")

        sys.exit(1)

    

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

        timeout=30

    )

    

    if response.status_code != 200:

        print(f"❌ Failed to exchange code: {response.text}")

        sys.exit(1)

    

    access_token = response.json()["access_token"]

    print("✅ Access token acquired.")

    

    agent_arn = runtime_config["agents"][agent_name]["bedrock_agentcore"]["agent_arn"]

    session_id = str(uuid.uuid4())

    

    if interactive:

        interactive_chat_session(

            agent_arn=agent_arn,

            bearer_token=access_token,

            session_id=session_id,

        )

    else:

        invoke_endpoint(

            agent_arn=agent_arn,

            payload=json.dumps({"prompt": prompt, "actor_id": "DEFAULT"}),

            bearer_token=access_token,

            session_id=session_id,

        )



if __name__ == "__main__":

    main()


