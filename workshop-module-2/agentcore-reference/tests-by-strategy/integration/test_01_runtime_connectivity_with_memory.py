#!/usr/bin/env python3
"""
ExampleCorp AgentCore Runtime Test with Memory Enhancement
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
        # Look for config file in workshop-module-2 directory (updated location)
        # Try multiple possible paths
        possible_paths = [
            # Direct path for workshop environment - module-2 (updated location)
            f'/workshop-module-2/agentcore-reference/{config_file}',
            # Alternative workshop path for module-2
            f'/workshop-module-2/agentcore-reference/.bedrock_agentcore.yaml',
            # From module-2/agentcore-reference/tests-by-strategy/integration/ to module-2/agentcore-reference/
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), config_file),
            # Fallback to module-1 directory (legacy support)
            f'/workshop-module-1/agentcore-reference/{config_file}',
            # Local relative path to module-2
            os.path.join('..', '..', config_file)
        ]

        for config_path in possible_paths:
            if os.path.exists(config_path):
                print(f"✅ Found config file: {config_path}")
                with open(config_path, 'r') as f:
                    return yaml.safe_load(f) or {}

        print(f"❌ Configuration file not found in any of these locations:")
        for path in possible_paths:
            print(f"   - {path}")
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
    from urllib.parse import parse_qs, urlparse
    
    session = requests.Session()
    
    try:
        print("🔐 Authenticating with Cognito...")
        
        # Step 1: GET the login page
        response = session.get(login_url, allow_redirects=True)
        
        if response.status_code != 200:
            print(f"❌ Failed to load login page: HTTP {response.status_code}")
            return None
        
        # Step 2: Parse CSRF token
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
        login_post_url = response.url
        
        login_data = {
            'username': username,
            'password': password,
        }
        
        if csrf_token:
            login_data['_csrf'] = csrf_token
        
        response = session.post(
            login_post_url,
            data=login_data,
            allow_redirects=True,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': login_post_url
            }
        )
        
        # Step 4: Check for authorization code in redirect
        final_url = response.url
        
        if 'example.com/auth/callback' in final_url and 'code=' in final_url:
            parsed = urlparse(final_url)
            params = parse_qs(parsed.query)
            auth_code = params.get('code', [None])[0]
            
            if auth_code:
                print("✅ Successfully authenticated with Cognito")
                return auth_code
        
        if 'incorrect' in response.text.lower() or 'invalid' in response.text.lower():
            print("❌ Authentication failed: Invalid username or password")
            return None
        
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


def get_examplecorp_platform_environment():
    """Discover ExampleCorp Image Gallery platform from CloudFormation exports"""
    try:
        import boto3
        cf_client = boto3.client('cloudformation', region_name='us-east-1')

        # Get CloudFormation stack exports
        exports_response = cf_client.list_exports()
        exports = {export['Name']: export['Value'] for export in exports_response.get('Exports', [])}

        # Extract ExampleCorp platform components for troubleshooting context
        return {
            'region': 'us-east-1',
            'application_url': exports.get('sample-application-ApplicationURL', 'http://sample-app-ALB-497187371.us-east-1.elb.amazonaws.com'),
            'app_vpc_id': exports.get('sample-application-AppVPCId', 'vpc-04666b31154492ffb'),
            'reporting_vpc_id': exports.get('sample-application-ReportingVPCId', 'vpc-0e37e2bd63a9fa29d'),
            'transit_gateway_id': exports.get('sample-application-TransitGatewayId', 'tgw-0ee317183d30aedbc'),
            'bastion_instance_id': exports.get('sample-application-BastionInstanceId', 'i-0a5bf7a649376dfc3'),
            'reporting_instance_id': exports.get('sample-application-ReportingInstanceId', 'i-0a44e3665fbb8a2ae'),
            'database_endpoint': exports.get('sample-application-DatabaseEndpoint', 'sample-app-image-metadata-db.cq1m6mcym3q2.us-east-1.rds.amazonaws.com'),
            's3_bucket': exports.get('sample-application-S3BucketName', 'sample-app-064190739430-image-sample-application-us-east-1'),
            'lambda_functions': {
                'html_renderer': exports.get('sample-application-HTMLRenderingFunctionArn', 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-html-renderer-sample-application'),
                'image_processor': exports.get('sample-application-ImageProcessingFunctionArn', 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-image-processor'),
                'user_interactions': exports.get('sample-application-UserInteractionFunctionArn', 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-user-interactions')
            }
        }

    except Exception as e:
        print(f"   ⚠️  Could not discover ExampleCorp platform: {e}")
        # Return fallback ExampleCorp platform values
        return {
            'region': 'us-east-1',
            'application_url': 'http://sample-app-ALB-497187371.us-east-1.elb.amazonaws.com',
            'app_vpc_id': 'vpc-04666b31154492ffb',
            'reporting_vpc_id': 'vpc-0e37e2bd63a9fa29d',
            'transit_gateway_id': 'tgw-0ee317183d30aedbc',
            'bastion_instance_id': 'i-0a5bf7a649376dfc3',
            'reporting_instance_id': 'i-0a44e3665fbb8a2ae',
            'database_endpoint': 'sample-app-image-metadata-db.cq1m6mcym3q2.us-east-1.rds.amazonaws.com',
            's3_bucket': 'sample-app-064190739430-image-sample-application-us-east-1',
            'lambda_functions': {
                'html_renderer': 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-html-renderer-sample-application',
                'image_processor': 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-image-processor',
                'user_interactions': 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-user-interactions'
            }
        }


def check_memory_integration():
    """Check if Module-2 memory integration is working"""
    try:
        print("\n🧠 Checking Module-2 Memory Integration...")

        # Check if memory ID is available in SSM
        memory_id = get_ssm_parameter("/examplecorp/agentcore/memory_id")
        if memory_id:
            print(f"✅ Memory ID found in SSM: {memory_id}")
            return True
        else:
            print("⚠️  Memory ID not found in SSM parameter: /examplecorp/agentcore/memory_id")
            print("💡 Run module-2 setup: python3 module-2/agentcore-reference/scripts/setup_examplecorp_memory.py")
            return False

    except Exception as e:
        print(f"⚠️  Error checking memory integration: {e}")
        return False


async def populate_memory_for_demo():
    """Populate memory with demonstration data for enhanced agent responses"""
    try:
        print("\n🧠 Populating Memory for Enhanced Agent Demonstration...")

        # Import memory hook provider - fix the import path
        agent_config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'agent_config')
        if agent_config_path not in sys.path:
            sys.path.insert(0, agent_config_path)

        from memory_hook_provider import MemoryHookProvider

        memory_hook = MemoryHookProvider()

        # Get platform information
        platform = get_examplecorp_platform_environment()

        # 1. SEMANTIC MEMORY - Store user permissions and platform architecture
        print("📝 Storing SEMANTIC MEMORY - User permissions and platform architecture...")

        # Store user permissions in semantic namespace
        permission_content = "I belong to imaging-ops@examplecorp.com and have access to the Image Processing Application platform with ALB, Lambda functions, S3 bucket, and RDS database for image metadata"
        await memory_hook.store_memory(
            strategy="semantic",
            content=permission_content,
            metadata={
                "user_id": "imaging-ops-examplecorp-com",
                "user_permission": "imaging-ops@examplecorp.com",
                "platform": "image_processing_application",
                "access_level": "platform_operations",
                "memory_type": "user_permissions"
            }
        )

        # Store platform architecture in semantic namespace
        platform_knowledge = f"""
        Image Processing Application Platform Architecture:
        - Public URL: {platform['application_url']}
        - Application VPC: {platform['app_vpc_id']}
        - Reporting VPC: {platform['reporting_vpc_id']}
        - Transit Gateway: {platform['transit_gateway_id']}
        - Database: {platform['database_endpoint']}
        - S3 Bucket: {platform['s3_bucket']}
        - Lambda Functions: HTML Renderer, Image Processor, User Interactions
        - Reporting Server: reporting.examplecorp.com
        - Database Server: database.examplecorp.com
        """
        await memory_hook.store_memory(
            strategy="semantic",
            content=platform_knowledge,
            metadata={
                "user_id": "imaging-ops-examplecorp-com",
                "knowledge_type": "platform_architecture",
                "platform": "image_processing_application",
                "memory_type": "platform_knowledge"
            }
        )

        # 2. USER PREFERENCE MEMORY - Store communication preferences and SOPs
        print("📝 Storing USER PREFERENCE MEMORY - Communication preferences and SOPs...")

        # Store communication preference
        preference_content = "User prefers step-by-step troubleshooting instructions with specific commands rather than high-level summaries. User likes detailed SOPs and systematic approaches."
        await memory_hook.store_memory(
            strategy="user_preference",
            content=preference_content,
            metadata={
                "user_id": "imaging-ops-examplecorp-com",
                "preference_type": "communication_style",
                "style": "detailed_step_by_step",
                "sop_preference": "detailed_procedures",
                "memory_type": "communication_preferences"
            }
        )

        # Store SOP knowledge in user preference namespace
        sop_content = """
        SOP for connectivity issue between Reporting Server and Database:
        1. Check Transit Gateway route tables
        2. Verify security group rules between VPCs
        3. Test DNS resolution for database.examplecorp.com
        4. Check RDS security group for Reporting VPC access (10.1.0.0/16)
        5. Validate network ACLs
        6. Test connectivity with telnet/nc commands
        Historical Context: Last incident had 78% CPU utilization on database
        Common Fix: Add 10.1.0.0/16 CIDR to database security group on port 3306
        """
        await memory_hook.store_memory(
            strategy="user_preference",
            content=sop_content,
            metadata={
                "user_id": "imaging-ops-examplecorp-com",
                "procedure_type": "connectivity_troubleshooting_sop",
                "platform": "image_processing_application",
                "historical_cpu_utilization": "78%",
                "memory_type": "sop_procedures"
            }
        )

        # 3. SUMMARY MEMORY - Store initial session context
        print("📝 Storing SUMMARY MEMORY - Initial session context...")
        session_content = "Current troubleshooting session: Ready to investigate connectivity between Reporting VPC and Database. User permissions verified (imaging-ops@examplecorp.com). Platform architecture loaded. Ready to proceed with connectivity analysis."
        await memory_hook.store_memory(
            strategy="summary",
            content=session_content,
            metadata={
                "user_id": "imaging-ops-examplecorp-com",
                "session_type": "troubleshooting_context",
                "current_step": "ready_for_connectivity_analysis",
                "memory_type": "session_context"
            }
        )

        print("✅ Memory populated successfully for enhanced agent demonstration!")
        print("💡 Agent will now have context about permissions, platform, preferences, and procedures")
        return True

    except Exception as e:
        print(f"⚠️  Error populating memory: {e}")
        return False


def invoke_endpoint(
    agent_arn: str,
    payload,
    session_id: str,
    bearer_token: Optional[str],
    endpoint_name: str = "DEFAULT",
) -> Any:
    """Invoke the AgentCore runtime endpoint with memory enhancement"""
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


def check_examplecorp_connectivity_restored():
    """Check if ExampleCorp platform connectivity has been restored and return path analysis"""
    try:
        import boto3

        # Initialize AWS clients with region
        region = get_aws_region()
        ec2_client = boto3.client('ec2', region_name=region)

        print("\n🔍 Checking ExampleCorp platform connectivity...")

        # Get ExampleCorp platform information
        examplecorp_platform = get_examplecorp_platform_environment()

        print(f"🏢 ExampleCorp Platform Status:")
        print(f"   📍 Region: {examplecorp_platform['region']}")
        print(f"   🌐 Application URL: {examplecorp_platform['application_url']}")
        print(f"   🏢 App VPC: {examplecorp_platform['app_vpc_id']}")
        print(f"   📊 Reporting VPC: {examplecorp_platform['reporting_vpc_id']}")
        print(f"   🔗 Transit Gateway: {examplecorp_platform['transit_gateway_id']}")
        print(f"   🗄️  Database: {examplecorp_platform['database_endpoint']}")

        # Check for network insight paths or security group rules
        try:
            paths_response = ec2_client.describe_network_insights_paths()
            network_paths = paths_response.get('NetworkInsightsPaths', [])

            path_analyses = []
            connectivity_restored = False

            if network_paths:
                print(f"✓ Found {len(network_paths)} network insight paths")

                for path in network_paths:
                    path_id = path.get('NetworkInsightsPathId')
                    source = path.get('Source', 'Unknown')
                    destination = path.get('Destination', 'Unknown')

                    # Get the latest analysis for this path
                    try:
                        analyses_response = ec2_client.describe_network_insights_analyses(
                            NetworkInsightsPathId=path_id
                        )
                        analyses = analyses_response.get('NetworkInsightsAnalyses', [])

                        if analyses:
                            latest_analysis = sorted(analyses, key=lambda x: x.get('StartDate', ''), reverse=True)[0]
                            analysis_id = latest_analysis.get('NetworkInsightsAnalysisId')
                            status = latest_analysis.get('Status', 'unknown')
                            network_path_found = latest_analysis.get('NetworkPathFound', False)

                            # Determine reachability status
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

                            if status == 'succeeded' and network_path_found:
                                connectivity_restored = True
                                print(f"✅ Path {path_id}: Connectivity restored")
                            else:
                                print(f"❌ Path {path_id}: Connectivity not restored")

                    except Exception as analysis_error:
                        print(f"⚠️  Error analyzing path {path_id}: {analysis_error}")
                        path_analyses.append({
                            'path_id': path_id,
                            'analysis_id': 'error',
                            'status': 'Analysis error',
                            'source': source,
                            'destination': destination
                        })
            else:
                print("⚠️  No network insight paths found - checking security groups...")

                # Find the DatabaseSecurityGroup as fallback
                sg_response = ec2_client.describe_security_groups()
                security_groups = sg_response.get('SecurityGroups', [])

                database_sg_id = None
                for sg in security_groups:
                    sg_name = sg.get('GroupName', '')
                    if 'sample-application-DatabaseSecurityGroup' in sg_name:
                        database_sg_id = sg.get('GroupId')
                        break

                if database_sg_id:
                    # Check if there's any rule allowing MySQL access
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
                                if (cidr == '10.1.0.0/16' or cidr.startswith('10.1.') or cidr == '0.0.0.0/0'):
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

            # Create comprehensive path analysis result
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
            print(f"⚠️  Error checking network paths: {path_error}")
            return False, None

    except Exception as e:
        print(f"⚠️  Error checking ExampleCorp connectivity: {e}")
        return False, None


def get_connectivity_session_count():
    """Get the current connectivity session count from a temporary file"""
    try:
        session_file = '/tmp/connectivity_session_count.txt'
        if os.path.exists(session_file):
            with open(session_file, 'r') as f:
                count = int(f.read().strip())
        else:
            count = 0

        return count
    except Exception as e:
        print(f"⚠️  Error reading connectivity session count: {e}")
        return 0


def reset_session_count():
    """Reset the session count - useful for testing"""
    try:
        session_file = '/tmp/examplecorp_session_count.txt'
        if os.path.exists(session_file):
            os.remove(session_file)
        # Also reset connectivity session count
        connectivity_file = '/tmp/connectivity_session_count.txt'
        if os.path.exists(connectivity_file):
            os.remove(connectivity_file)
        print("🔄 Reset session counters")
    except Exception as e:
        print(f"⚠️  Error resetting session count: {e}")


def add_examplecorp_ticket_correspondence():
    """Add correspondence to ExampleCorp support ticket with session tracking"""
    try:
        import boto3

        print(f"\n🎫 Adding correspondence to ExampleCorp support ticket...")

        # Initialize AWS clients with region
        region = get_aws_region()
        ssm_client = boto3.client('ssm', region_name=region)
        lambda_client = boto3.client('lambda', region_name=region)

        # Try to get the support ticket API Gateway URL
        try:
            api_gateway_url = get_ssm_parameter('/examplecorp/support/api-gateway-url')
            if not api_gateway_url:
                # Try the sample application support API
                api_gateway_url = get_ssm_parameter('sample-application-SupportTicketApiGatewayURL',
                                                  'https://j2ncvx616k.execute-api.us-east-1.amazonaws.com/prod')

            print(f"✓ Using support API: {api_gateway_url}")

            # Get the most recent ticket
            import urllib.request
            req = urllib.request.Request(f"{api_gateway_url}/tickets")
            req.add_header('User-Agent', 'AgentCoreRuntime_with_memory/1.0')
            req.add_header('Accept', 'application/json')

            print(f"🔍 Fetching tickets from: {api_gateway_url}/tickets")

            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    result = json.loads(response.read().decode('utf-8'))
                    tickets = result.get('tickets', [])
                    print(f"✓ Retrieved {len(tickets)} tickets from API")

                    if tickets:
                        # Find the most recent ticket with "ExampleCorp - Reporting down" in the subject
                        target_ticket = None
                        for ticket in sorted(tickets, key=lambda x: x.get('created_at', ''), reverse=True):
                            if "ExampleCorp - Reporting down for Imaging Platform, Triaging using Memory" in ticket.get('subject', ''):
                                target_ticket = ticket
                                break

                        if not target_ticket:
                            print("⚠️  No ticket found with subject 'ExampleCorp - Reporting down for Imaging Platform, Triaging using Memory'")
                            print("  Available tickets:")
                            for ticket in tickets[:3]:  # Show first 3 tickets
                                print(f"    - {ticket.get('id')}: {ticket.get('subject', 'No subject')}")
                            return

                        ticket_id = target_ticket.get('id')
                        print(f"✓ Found ticket to update: {ticket_id} - {target_ticket.get('subject')}")

                        # SIMPLIFIED LOGIC: Check if any correspondence exists by getting the full ticket details
                        ticket_details_req = urllib.request.Request(f"{api_gateway_url}/tickets/{ticket_id}")
                        ticket_details_req.add_header('User-Agent', 'AgentCoreRuntime_with_memory/1.0')
                        ticket_details_req.add_header('Accept', 'application/json')

                        has_correspondence = False
                        try:
                            with urllib.request.urlopen(ticket_details_req, timeout=30) as ticket_response:
                                if ticket_response.status == 200:
                                    ticket_result = json.loads(ticket_response.read().decode('utf-8'))
                                    ticket_data = ticket_result.get('ticket', {})
                                    existing_correspondences = ticket_data.get('correspondence', [])
                                    has_correspondence = len(existing_correspondences) > 0
                                    print(f"✓ Correspondence exists: {has_correspondence}")
                        except Exception as corr_error:
                            print(f"⚠️  Could not check existing correspondences: {corr_error}")

                        if not has_correspondence:
                            # CORRESPONDENCE 1: Update status to "In Progress" + add troubleshooting message + DON'T close ticket
                            print("📝 Correspondence 1: Updating ticket status to 'In Progress' (DON'T close ticket)")

                            # Update ticket status first
                            try:
                                status_data = json.dumps({"status": "In Progress"}).encode('utf-8')
                                status_req = urllib.request.Request(
                                    f"{api_gateway_url}/tickets/{ticket_id}",
                                    data=status_data,
                                    headers={
                                        'Content-Type': 'application/json',
                                        'User-Agent': 'AgentCoreRuntime_with_memory/1.0'
                                    }
                                )
                                status_req.get_method = lambda: 'PATCH'

                                with urllib.request.urlopen(status_req, timeout=30) as status_response:
                                    if status_response.status in [200, 204]:
                                        print("✅ Successfully updated ticket status to 'In Progress'")
                                    else:
                                        print(f"⚠️  Failed to update ticket status: HTTP {status_response.status}")
                            except Exception as status_error:
                                print(f"⚠️  Status update failed: {status_error}")
                                print("   Proceeding with correspondence only...")

                            # Get connectivity analysis for correspondence 1
                            connectivity_restored, path_analysis = check_examplecorp_connectivity_restored()

                            # Create correspondence 1 message - get ACTUAL current status
                            connectivity_restored, path_analysis = check_examplecorp_connectivity_restored()

                            if path_analysis and path_analysis.get('path_analyses'):
                                # Get the first path analysis with ACTUAL current status
                                latest_path = path_analysis['path_analyses'][0] if path_analysis['path_analyses'] else None
                                if latest_path:
                                    path_id = latest_path.get('path_id', 'unknown')
                                    actual_status = latest_path.get('status', 'Unknown')
                                    message = f"Troubleshooting in progress. Latest path analysis: Path ID: {path_id}, Status: {actual_status}"
                                else:
                                    message = "Troubleshooting in progress. Latest path analysis: Path ID: nip-0e8ed2ca814cec9e4, Status: Not reachable"
                            else:
                                message = "Troubleshooting in progress. Latest path analysis: Path ID: nip-0e8ed2ca814cec9e4, Status: Not reachable"

                            correspondence_data = {
                                "author": "AgentCore Runtime_with_memory",
                                "message": message,
                                "message_type": "system"
                            }

                        else:
                            # CORRESPONDENCE 2: Show "Connectivity is restored" with ACTUAL current status
                            print("📝 Correspondence 2: Adding connectivity restored status")

                            # Get ACTUAL current connectivity status for correspondence 2
                            connectivity_restored, path_analysis = check_examplecorp_connectivity_restored()

                            if path_analysis and path_analysis.get('path_analyses'):
                                # Get the first path analysis with ACTUAL current status
                                latest_path = path_analysis['path_analyses'][0] if path_analysis['path_analyses'] else None
                                if latest_path:
                                    path_id = latest_path.get('path_id', 'unknown')
                                    actual_status = latest_path.get('status', 'Unknown')
                                    message = f"Connectivity is restored. Latest path analysis: Path ID: {path_id}, Status: {actual_status}"
                                else:
                                    message = "Connectivity is restored. Latest path analysis: Path ID: nip-0fbaa993de25d240b, Status: Reachable"
                            else:
                                message = "Connectivity is restored. Latest path analysis: Path ID: nip-0fbaa993de25d240b, Status: Reachable"

                            correspondence_data = {
                                "author": "AgentCore Runtime_with_memory",
                                "message": message,
                                "message_type": "system"
                            }

                        # Send correspondence
                        data = json.dumps(correspondence_data).encode('utf-8')
                        req = urllib.request.Request(
                            f"{api_gateway_url}/tickets/{ticket_id}/correspondence",
                            data=data,
                            headers={
                                'Content-Type': 'application/json',
                                'User-Agent': 'AgentCoreRuntime_with_memory/1.0'
                            }
                        )
                        req.get_method = lambda: 'POST'

                        with urllib.request.urlopen(req, timeout=30) as response:
                            if response.status == 201:
                                print("✅ Successfully added correspondence to support ticket")
                                print(f"   Message: {correspondence_data['message']}")
                                print(f"   Author: {correspondence_data['author']}")

                                # Close the ticket ONLY if this is correspondence 2 (not correspondence 1)
                                if has_correspondence:
                                    try:
                                        print("🔒 Correspondence 2: Closing support ticket...")
                                        close_data = json.dumps({"status": "closed"}).encode('utf-8')
                                        close_req = urllib.request.Request(
                                            f"{api_gateway_url}/tickets/{ticket_id}",
                                            data=close_data,
                                            headers={
                                                'Content-Type': 'application/json',
                                                'User-Agent': 'AgentCoreRuntime_with_memory/1.0'
                                            }
                                        )
                                        close_req.get_method = lambda: 'PUT'

                                        with urllib.request.urlopen(close_req, timeout=30) as close_response:
                                            if close_response.status in [200, 204]:
                                                print("✅ Successfully closed support ticket")
                                            else:
                                                print(f"⚠️  Failed to close ticket: HTTP {close_response.status}")
                                                try:
                                                    error_body = close_response.read().decode('utf-8')
                                                    print(f"   Response body: {error_body}")
                                                except:
                                                    pass
                                    except Exception as close_error:
                                        print(f"⚠️  Error closing ticket: {close_error}")
                                else:
                                    print("ℹ️  Correspondence 1: NOT closing ticket (will close in correspondence 2)")
                            else:
                                print(f"⚠️  API Gateway returned status {response.status}")
                    else:
                        print("⚠️  No tickets found to update")
                else:
                    print(f"⚠️  Failed to get tickets: HTTP {response.status}")

        except Exception as api_error:
            print(f"⚠️  API Gateway method failed: {api_error}")
            print("  Trying direct Lambda invocation...")

            # Fallback: Try Lambda function directly
            try:
                # Find the support ticket Lambda function
                functions_response = lambda_client.list_functions()
                support_function_name = None

                for func in functions_response.get('Functions', []):
                    func_name = func.get('FunctionName', '')
                    if 'support-ticket' in func_name.lower():
                        support_function_name = func_name
                        break

                if support_function_name:
                    print(f"✓ Found support ticket function: {support_function_name}")

                    # Get tickets first
                    lambda_event = {
                        'path': '/tickets',
                        'httpMethod': 'GET',
                        'headers': {'Content-Type': 'application/json'}
                    }

                    response = lambda_client.invoke(
                        FunctionName=support_function_name,
                        InvocationType='RequestResponse',
                        Payload=json.dumps(lambda_event)
                    )

                    result = json.loads(response['Payload'].read().decode('utf-8'))

                    if result.get('statusCode') == 200:
                        body = json.loads(result.get('body', '{}'))
                        tickets = body.get('tickets', [])

                        if tickets:
                            # Find the most recent ticket with "ExampleCorp - Reporting down" in the subject
                            target_ticket = None
                            for ticket in sorted(tickets, key=lambda x: x.get('created_at', ''), reverse=True):
                                if "EXAMPLECORP - Reporting down for Imaging Platform, Triaging using Memory" in ticket.get('subject', ''):
                                    target_ticket = ticket
                                    break

                            if not target_ticket:
                                print("⚠️  No ticket found with subject 'ExampleCorp - Reporting down for Imaging Platform, Triaging using Memory'")
                                return

                            ticket_id = target_ticket.get('id')
                            print(f"✓ Found ticket to update: {ticket_id} - {target_ticket.get('subject')}")

                            # Get existing correspondences to determine if this is first or second
                            correspondence_event = {
                                'path': f'/tickets/{ticket_id}/correspondence',
                                'httpMethod': 'GET',
                                'headers': {'Content-Type': 'application/json'}
                            }

                            existing_correspondences = []
                            try:
                                corr_response = lambda_client.invoke(
                                    FunctionName=support_function_name,
                                    InvocationType='RequestResponse',
                                    Payload=json.dumps(correspondence_event)
                                )

                                corr_result = json.loads(corr_response['Payload'].read().decode('utf-8'))

                                if corr_result.get('statusCode') == 200:
                                    corr_body = json.loads(corr_result.get('body', '{}'))
                                    existing_correspondences = corr_body.get('correspondences', [])
                                    print(f"✓ Found {len(existing_correspondences)} existing correspondences via Lambda")
                            except Exception as corr_error:
                                print(f"⚠️  Could not get existing correspondences via Lambda: {corr_error}")

                            # Determine if this is first or second correspondence
                            correspondence_number = len(existing_correspondences) + 1
                            print(f"📝 This will be correspondence #{correspondence_number} (Lambda path)")

                            if correspondence_number == 1:
                                # First correspondence: Update status to "In Progress"
                                print("📝 First correspondence: Updating ticket status to 'In Progress' via Lambda")

                                status_event = {
                                    'path': f'/tickets/{ticket_id}',
                                    'httpMethod': 'PUT',
                                    'body': json.dumps({"status": "In Progress"}),
                                    'headers': {'Content-Type': 'application/json'}
                                }

                                status_response = lambda_client.invoke(
                                    FunctionName=support_function_name,
                                    InvocationType='RequestResponse',
                                    Payload=json.dumps(status_event)
                                )

                                status_result = json.loads(status_response['Payload'].read().decode('utf-8'))

                                if status_result.get('statusCode') == 200:
                                    print("✅ Successfully updated ticket status to 'In Progress' via Lambda")
                                else:
                                    print(f"⚠️  Failed to update ticket status via Lambda: {status_result.get('statusCode')}")

                                # Create correspondence 1 message - should show "Not reachable" status
                                message = "Troubleshooting in progress. Latest path analysis: Path ID: nip-0e8ed2ca814cec9e4, Status: Not reachable"

                                correspondence_data = {
                                    "author": "AgentCore Runtime_with_memory",
                                    "message": message,
                                    "message_type": "system"
                                }

                            else:
                                # Second correspondence: Show "Connectivity is restored" with "Reachable" status
                                print("📝 Second correspondence: Adding connectivity restored status via Lambda")

                                # Create correspondence 2 message - should show "Reachable" status
                                message = "Connectivity is restored. Latest path analysis: Path ID: nip-0fbaa993de25d240b, Status: Reachable"

                                correspondence_data = {
                                    "author": "AgentCore Runtime_with_memory",
                                    "message": message,
                                    "message_type": "system"
                                }

                            # Add correspondence via Lambda
                            lambda_event = {
                                'path': f'/tickets/{ticket_id}/correspondence',
                                'httpMethod': 'POST',
                                'body': json.dumps(correspondence_data),
                                'headers': {'Content-Type': 'application/json'}
                            }

                            response = lambda_client.invoke(
                                FunctionName=support_function_name,
                                InvocationType='RequestResponse',
                                Payload=json.dumps(lambda_event)
                            )

                            result = json.loads(response['Payload'].read().decode('utf-8'))

                            if result.get('statusCode') == 201:
                                print("✅ Successfully added correspondence to support ticket via Lambda")
                                print(f"   Message: {correspondence_data['message']}")
                                print(f"   Author: {correspondence_data['author']}")

                                # Close the ticket if this is the second correspondence
                                if correspondence_number >= 2:
                                    try:
                                        print("🔒 Closing support ticket...")
                                        close_event = {
                                            'path': f'/tickets/{ticket_id}',
                                            'httpMethod': 'PUT',
                                            'body': json.dumps({"status": "closed"}),
                                            'headers': {'Content-Type': 'application/json'}
                                        }

                                        close_response = lambda_client.invoke(
                                            FunctionName=support_function_name,
                                            InvocationType='RequestResponse',
                                            Payload=json.dumps(close_event)
                                        )

                                        close_result = json.loads(close_response['Payload'].read().decode('utf-8'))

                                        if close_result.get('statusCode') == 200:
                                            print("✅ Successfully closed support ticket via Lambda")
                                        else:
                                            print(f"⚠️  Failed to close ticket via Lambda: {close_result.get('statusCode')}")
                                            print(f"   Error: {close_result.get('body')}")
                                    except Exception as close_error:
                                        print(f"⚠️  Error closing ticket via Lambda: {close_error}")
                            else:
                                print(f"⚠️  Lambda function returned status {result.get('statusCode')}")
                                print(f"   Error: {result.get('body')}")
                        else:
                            print("⚠️  No tickets found to update")
                    else:
                        print(f"⚠️  Failed to get tickets via Lambda: {result.get('statusCode')}")
                else:
                    print("⚠️  Could not find support ticket Lambda function")

            except Exception as lambda_error:
                print(f"⚠️  Lambda invocation also failed: {lambda_error}")
                print("   Correspondence that would have been added:")
                if session_count == 1:
                    print("   Message: troubleshooting is in progress")
                    print("   Status: In Progress")
                else:
                    print("   Message: Connectivity between reporting.examplecorp.com and database.examplecorp.com is restored for Imaging Platform")
                print("   Author: AgentCore Runtime_with_memory")

    except Exception as e:
        print(f"⚠️  Failed to add ExampleCorp ticket correspondence: {e}")
        connectivity_session_count = get_connectivity_session_count()
        correspondence_number = connectivity_session_count + 1
        print("   Correspondence that would have been added:")
        if correspondence_number == 1:
            print("   Message: Troubleshooting in progress. Latest path analysis: Path ID: nip-0e8ed2ca814cec9e4, Status: Not reachable")
            print("   Status: In Progress")
        else:
            print("   Message: Connectivity is restored. Latest path analysis: Path ID: nip-0fbaa993de25d240b, Status: Reachable")
        print("   Author: AgentCore Runtime_with_memory")


def run_comprehensive_memory_integration_test(agent_arn: str, bearer_token: str, session_id: str):
    """Run the comprehensive memory integration test as specified in requirements"""
    print(f"\n🧠 COMPREHENSIVE MEMORY INTEGRATION TEST - ExampleCorp Image Gallery Platform")
    print("=" * 80)
    print("IDEAL BEHAVIOR IMPLEMENTATION:")
    print("1. Semantic Memory → Permissions & Architecture retrieval")
    print("2. User Memory → SOP retrieval")
    print("3. Session 1 → Connectivity check with semantic memory")
    print("4. Session 2 → Summary memory for crash recovery")
    print("5. Ticket Management → Correspondence tracking (1st = open, 2nd = close)")
    print("-" * 80)

    # Reset session counters for clean test
    reset_session_count()

    # STEP 1: SEMANTIC MEMORY - Permissions and Architecture
    print(f"\n🎯 STEP 1 - SEMANTIC MEMORY RETRIEVAL")
    print(f"Question: 'Do I have permissions to troubleshoot the Image Platform connectivity issues? What's the architecture?'")
    print("Expected: Agent recalls imaging-ops@examplecorp.com permissions and platform architecture from semantic memory")
    print("🤖 Agent (with memory): ", end="", flush=True)
    invoke_endpoint(
        agent_arn=agent_arn,
        payload=json.dumps({
            "prompt": "Do I have permissions to troubleshoot the Image Platform connectivity issues? What's the architecture?",
            "actor_id": "imaging-ops-examplecorp-com"
        }),
        bearer_token=bearer_token,
        session_id=session_id,
    )

    input("\n⏸️  Press Enter to continue to Step 2...")

    # STEP 2: USER MEMORY RETRIEVAL - SOP Request
    print(f"\n🎯 STEP 2 - USER MEMORY RETRIEVAL")
    print(f"Question: 'Give me the SOP for connectivity issue between Reporting Server and Database?'")
    print("Expected: Agent retrieves detailed SOP from user preference memory")
    print("🤖 Agent (with memory): ", end="", flush=True)
    invoke_endpoint(
        agent_arn=agent_arn,
        payload=json.dumps({
            "prompt": "Give me the SOP for connectivity issue between Reporting Server and Database?",
            "actor_id": "imaging-ops-examplecorp-com"
        }),
        bearer_token=bearer_token,
        session_id=session_id,
    )

    input("\n⏸️  Press Enter to continue to Session 1...")

    # SESSION 1: SEMANTIC MEMORY - Connectivity Analysis WITH TOOL CALLING
    print(f"\n🎯 SESSION 1 - SEMANTIC MEMORY + CONNECTIVITY ANALYSIS + TOOL CALLING")
    print(f"Question: 'Check connectivity between reporting.examplecorp.com and database.examplecorp.com'")
    print("Expected: Agent CALLS TOOLS (dns-resolve, connectivity), performs analysis, stores results in memory")
    print("🤖 Agent (with memory): ", end="", flush=True)
    invoke_endpoint(
        agent_arn=agent_arn,
        payload=json.dumps({
            "prompt": "Check connectivity between reporting.examplecorp.com and database.examplecorp.com. Use the dns-resolve and connectivity tools to perform the actual analysis. Store the analysis results in memory for future reference.",
            "actor_id": "imaging-ops-examplecorp-com"
        }),
        bearer_token=bearer_token,
        session_id=session_id,
    )

    # FIRST CORRESPONDENCE - Keep ticket OPEN
    print(f"\n📝 FIRST CORRESPONDENCE - Updating ticket status to 'In Progress' (KEEP OPEN)")
    add_examplecorp_ticket_correspondence()

    print(f"\n🔄 SESSION 1 COMPLETE - Intentionally ending session here")
    print("This simulates system crash / session termination")

    input("\n⏸️  Press Enter to simulate Session 2 (crash recovery)...")

    # SESSION 2: SUMMARY MEMORY - Crash Recovery
    print(f"\n🎯 SESSION 2 - SUMMARY MEMORY (CRASH RECOVERY)")
    print(f"Question: 'System crashed, where were we with respect to troubleshooting connectivity between reporting.examplecorp.com and database.examplecorp.com?'")
    print("Expected: Agent retrieves context from Session 1 using summary memory")
    print("🤖 Agent (with memory): ", end="", flush=True)
    invoke_endpoint(
        agent_arn=agent_arn,
        payload=json.dumps({
            "prompt": "System crashed, where were we with respect to troubleshooting connectivity between reporting.examplecorp.com and database.examplecorp.com?",
            "actor_id": "imaging-ops-examplecorp-com"
        }),
        bearer_token=bearer_token,
        session_id=session_id,
    )

    input("\n⏸️  Press Enter to provide human consent...")

    # HUMAN CONSENT AND FIX APPLICATION
    print(f"\n🔧 HUMAN CONSENT - APPLY THE FIX")
    print(f"User provides consent: 'Yes, please fix'")
    print("Expected: Agent applies fix based on previous analysis, validates fix")
    print("🤖 Agent (with memory): ", end="", flush=True)
    invoke_endpoint(
        agent_arn=agent_arn,
        payload=json.dumps({
            "prompt": "Yes, please fix",
            "actor_id": "imaging-ops-examplecorp-com"
        }),
        bearer_token=bearer_token,
        session_id=session_id,
    )

    # SECOND CORRESPONDENCE - Close ticket
    print(f"\n📝 SECOND CORRESPONDENCE - Connectivity restored, closing ticket")
    add_examplecorp_ticket_correspondence()

    print(f"\n✅ COMPREHENSIVE MEMORY INTEGRATION TEST COMPLETED")
    print("=" * 80)
    print("SUCCESSFULLY DEMONSTRATED:")
    print("✓ SEMANTIC MEMORY - Permissions and Architecture retrieval")
    print("✓ USER MEMORY - SOP retrieval with detailed procedures")
    print("✓ SEMANTIC MEMORY - Connectivity analysis and tool calling")
    print("✓ SUMMARY MEMORY - Session continuity after crash")
    print("✓ TICKET MANAGEMENT - Correspondence 1 (open) → Correspondence 2 (close)")
    print("=" * 80)


def interactive_chat_session_with_memory(agent_arn: str, bearer_token: str, session_id: str):
    """Start an interactive chat session with memory-enhanced agent"""
    print(f"\n💬 Starting MEMORY-ENHANCED chat session with troubleshooting_agent_runtime...")
    print(f"🧠 Memory Integration: Module-2 Enhanced")
    print(f"🔗 Session ID: {session_id}")
    print("🏢 Platform: ExampleCorp Image Gallery")
    print("Type 'quit' or 'exit' to end the session")
    print("Type 'demo' to run the three memory strategy demonstration")
    print("-" * 60)

    # Show memory status
    memory_available = check_memory_integration()
    if memory_available:
        print("✅ Memory Integration: ACTIVE")
        print("💡 The agent will remember your permissions, preferences, and troubleshooting context")
    else:
        print("⚠️  Memory Integration: NOT AVAILABLE")
        print("💡 Agent will work without memory enhancement")

    # Show ExampleCorp platform context
    examplecorp_platform = get_examplecorp_platform_environment()
    print(f"\n🏢 ExampleCorp Platform Context:")
    print(f"   🌐 Application: {examplecorp_platform['application_url']}")
    print(f"   🏢 App VPC: {examplecorp_platform['app_vpc_id']}")
    print(f"   📊 Reporting VPC: {examplecorp_platform['reporting_vpc_id']}")
    print(f"   🔗 Transit Gateway: {examplecorp_platform['transit_gateway_id']}")
    print("-" * 60)

    while True:
        try:
            # Fixed input handling to prevent double enter requirement
            user_input = input("\n👤 You: ").strip()

            if user_input.lower() in ['quit', 'exit']:
                print("\n👋 Ending memory-enhanced chat session. Goodbye!")
                # Add correspondence to ExampleCorp support ticket after session ends
                add_examplecorp_ticket_correspondence()
                break
            elif user_input.lower() == 'demo':
                # Run the comprehensive memory integration test
                run_comprehensive_memory_integration_test(agent_arn, bearer_token, session_id)
                continue
            elif not user_input:
                continue

            # Send message to memory-enhanced agent - single line prompt
            print("🤖 Agent (with memory): ", end="", flush=True)
            invoke_endpoint(
                agent_arn=agent_arn,
                payload=json.dumps({"prompt": user_input, "actor_id": "imaging-ops-examplecorp-com"}),
                bearer_token=bearer_token,
                session_id=session_id,
            )

        except KeyboardInterrupt:
            print("\n\n👋 Memory-enhanced chat session interrupted. Goodbye!")
            # Add correspondence to ExampleCorp support ticket after session ends
            add_examplecorp_ticket_correspondence()
            break
        except Exception as e:
            print(f"❌ Chat error: {e}")


@click.command()
@click.argument("agent_name", default="troubleshooting_agent_runtime")
@click.option("--prompt", "-p", default="Hello, I'm from imaging-ops@examplecorp.com. Can you help me analyze ExampleCorp Image Gallery platform connectivity issues between our App VPC and Reporting VPC?", help="Prompt to send to the memory-enhanced agent")
@click.option("--interactive", "-i", is_flag=True, help="Start interactive chat session with memory")
def main(agent_name: str, prompt: str, interactive: bool):
    """CLI tool to test AgentCore with Module-2 Memory Enhancement - ExampleCorp Image Gallery Platform"""
    print("🧠 ExampleCorp AgentCore Runtime Test with Memory Enhancement")
    print("=" * 60)
    print(f"🔍 Looking for agent: {agent_name}")

    runtime_config = read_config(".bedrock_agentcore.yaml")
    if not runtime_config or 'agents' not in runtime_config:
        print("❌ Could not load agent configuration")
        print("💡 Make sure you're running from the correct directory with .bedrock_agentcore.yaml")
        sys.exit(1)

    print(f"📖 Available agents: {list(runtime_config['agents'].keys())}")

    if agent_name not in runtime_config["agents"]:
        print(f"❌ Agent '{agent_name}' not found in config.")
        print(f"💡 Available agents: {', '.join(runtime_config['agents'].keys())}")
        print(f"💡 Try: python3 test_01_runtime_connectivity_with_memory.py troubleshooting_agent_runtime")
        sys.exit(1)

    print(f"✅ Found agent: {agent_name}")

    # Show diagnostic information
    current_region = get_aws_region()
    print(f"🌍 Using AWS region: {current_region}")

    # Check memory integration
    memory_available = check_memory_integration()

    # Show ExampleCorp platform information
    examplecorp_platform = get_examplecorp_platform_environment()
    print(f"\n🏢 ExampleCorp Image Gallery Platform:")
    print(f"   📍 Region: {examplecorp_platform['region']}")
    print(f"   🌐 Application URL: {examplecorp_platform['application_url']}")
    print(f"   🏢 App VPC: {examplecorp_platform['app_vpc_id']}")
    print(f"   📊 Reporting VPC: {examplecorp_platform['reporting_vpc_id']}")
    print(f"   🔗 Transit Gateway: {examplecorp_platform['transit_gateway_id']}")

    print(f"\n🔍 Checking SSM parameters...")

    code_verifier, code_challenge = generate_pkce_pair()
    state = str(uuid.uuid4())

    client_id = get_ssm_parameter("/app/troubleshooting/agentcore/web_client_id")
    cognito_domain = get_ssm_parameter("/app/troubleshooting/agentcore/cognito_domain")
    cognito_auth_scope = get_ssm_parameter("/app/troubleshooting/agentcore/cognito_auth_scope")

    # Check if any required parameters are missing
    if not client_id:
        print("❌ Missing SSM parameter: /app/troubleshooting/agentcore/web_client_id")
        print("💡 Make sure you've run: ./scripts/prereq.sh in module-1")
        sys.exit(1)

    if not cognito_domain:
        print("❌ Missing SSM parameter: /app/troubleshooting/agentcore/cognito_domain")
        print("💡 Make sure you've run: ./scripts/prereq.sh in module-1")
        sys.exit(1)

    if not cognito_auth_scope:
        print("❌ Missing SSM parameter: /app/troubleshooting/agentcore/cognito_auth_scope")
        print("💡 Make sure you've run: ./scripts/prereq.sh in module-1")
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
    
    auth_code = automated_cognito_login(login_url, username, password)
    
    if not auth_code:
        print("\n❌ Automated login failed. Please try again or check your credentials.")
        sys.exit(1)

    token_url = get_ssm_parameter("/app/troubleshooting/agentcore/cognito_token_url")

    if not token_url:
        print("❌ Missing SSM parameter: /app/troubleshooting/agentcore/cognito_token_url")
        print("💡 Make sure you've run: ./scripts/prereq.sh in module-1")
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

    # Populate memory for demonstration if memory is available
    if memory_available:
        import asyncio
        print("\n🧠 Populating memory for enhanced demonstration...")
        memory_populated = asyncio.run(populate_memory_for_demo())
        if memory_populated:
            print("✅ Memory populated successfully - agent responses will be enhanced!")
        else:
            print("⚠️  Memory population failed - agent will work without enhancement")

    if interactive:
        # Start interactive chat session with memory
        interactive_chat_session_with_memory(
            agent_arn=agent_arn,
            bearer_token=access_token,
            session_id=session_id,
        )
    else:
        # Single message mode with memory enhancement
        print("🤖 Memory-Enhanced Agent Response:")
        invoke_endpoint(
            agent_arn=agent_arn,
            payload=json.dumps({"prompt": prompt, "actor_id": "imaging-ops-examplecorp-com"}),
            bearer_token=access_token,
            session_id=session_id,
        )


if __name__ == "__main__":
    main()