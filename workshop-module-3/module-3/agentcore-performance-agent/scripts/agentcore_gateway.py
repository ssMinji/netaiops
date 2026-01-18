#!/usr/bin/python
from typing import List
import os
import sys
import time
import boto3
import click
from botocore.exceptions import ClientError

from utils import (
    get_aws_region,
    get_ssm_parameter,
    create_ssm_parameters,
    delete_ssm_parameters,
    load_api_spec,
)


REGION = get_aws_region()

gateway_client = boto3.client(
    "bedrock-agentcore-control",
    region_name=REGION,
)


def retry_with_backoff(func, max_retries=5, initial_delay=1, backoff_multiplier=2):
    """Retry function with exponential backoff for handling throttling."""
    for attempt in range(max_retries):
        try:
            return func()
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ['ThrottlingException', 'TooManyRequestsException', 'RequestLimitExceeded']:
                if attempt == max_retries - 1:
                    raise e  # Re-raise if it's the last attempt
                
                delay = initial_delay * (backoff_multiplier ** attempt)
                click.echo(f"⏳ Rate limit hit, waiting {delay}s before retry (attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise e  # Re-raise if it's not a throttling error
    
    return None


def wait_for_gateway_active(gateway_id, max_wait_time=300, check_interval=10):
    """Wait for gateway to be in ACTIVE or READY state before proceeding."""
    click.echo(f"⏳ Waiting for gateway {gateway_id} to be ready...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            response = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
            status = response.get('status', 'UNKNOWN')
            
            if status in ['ACTIVE', 'READY']:
                click.echo(f"✅ Gateway is now ready (status: {status})")
                return True
            elif status in ['FAILED', 'DELETING', 'DELETED']:
                click.echo(f"❌ Gateway is in {status} state")
                return False
            else:
                click.echo(f"   Gateway status: {status}, waiting {check_interval}s...")
                time.sleep(check_interval)
                
        except Exception as e:
            click.echo(f"   Error checking gateway status: {e}, retrying...")
            time.sleep(check_interval)
    
    click.echo(f"❌ Timeout waiting for gateway to be ready after {max_wait_time}s")
    return False


def create_gateway_target_with_retry(gateway_id, name, description, target_config, credential_config):
    """Create gateway target with throttling protection."""
    def create_target():
        return gateway_client.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=name,
            description=description,
            targetConfiguration=target_config,
            credentialProviderConfigurations=credential_config,
        )
    
    return retry_with_backoff(create_target)


def create_gateway(gateway_name: str) -> dict:
    """Create an AgentCore gateway with DNS and connectivity tools."""
    auth_config = {
        "customJWTAuthorizer": {
            "allowedClients": [
                get_ssm_parameter(
                    "/a2a/app/performance/agentcore/machine_client_id"
                )
            ],
            "discoveryUrl": get_ssm_parameter(
                "/a2a/app/performance/agentcore/cognito_discovery_url"
            ),
        }
    }

    execution_role_arn = get_ssm_parameter(
        "/a2a/app/performance/agentcore/gateway_iam_role"
    )

    click.echo(f"Creating gateway in region {REGION} with name: {gateway_name}")
    click.echo(f"Execution role ARN: {execution_role_arn}")

    create_response = gateway_client.create_gateway(
        name=gateway_name,
        roleArn=execution_role_arn,
        protocolType="MCP",
        authorizerType="CUSTOM_JWT",
        authorizerConfiguration=auth_config,
        description="AgentCore Performance Gateway",
    )

    click.echo(f"✅ Gateway created: {create_response['gatewayId']}")

    credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
    gateway_id = create_response["gatewayId"]

    # Wait for gateway to be active before creating targets
    if not wait_for_gateway_active(gateway_id):
        raise Exception("Gateway failed to become active within the timeout period")

    # Get Performance Lambda ARN from SSM
    click.echo("🔧 Creating Performance Analysis targets...")
    try:
        performance_lambda_arn = get_ssm_parameter("/a2a/app/performance/agentcore/lambda_arn")
        click.echo(f"📝 Performance Lambda ARN: {performance_lambda_arn}")
    except Exception as e:
        click.echo(f"❌ Failed to get Performance Lambda ARN from SSM: {e}")
        click.echo("💡 Make sure to deploy the performance lambda first:")
        click.echo("   ./prerequisite/lambda-performance/deploy-performance-tools.sh")
        raise e
    
    # Find performance API spec file
    performance_api_spec_paths = [
        "prerequisite/lambda-performance/api_spec.json",
        "../prerequisite/lambda-performance/api_spec.json",
        "./prerequisite/lambda-performance/api_spec.json"
    ]
    
    performance_api_spec = None
    for path in performance_api_spec_paths:
        if os.path.exists(path):
            performance_api_spec = load_api_spec(path)
            click.echo(f"📖 Loaded Performance API spec from: {path}")
            break
    
    if not performance_api_spec:
        error_msg = "Performance API specification not found in any expected location"
        click.echo(f"❌ {error_msg}")
        click.echo("🔍 Searched paths:")
        for path in performance_api_spec_paths:
            click.echo(f"   - {path}")
        raise Exception(error_msg)

    # Create individual targets for each tool in the performance API spec
    # Note: Target names must be short to avoid 64-char limit when combined with tool names
    tool_targets = [
        {
            "name": "FlowMonitorAnalysis",
            "description": "Analyze all Network Flow Monitors in a region and AWS account",
            "tool_name": "analyze_network_flow_monitor"
        },
        {
            "name": "TrafficMirrorLogs",
            "description": "Extract and analyze PCAP files from traffic mirroring S3 bucket",
            "tool_name": "analyze_traffic_mirroring_logs"
        },
        {
            "name": "FixRetransmissions",
            "description": "Fix TCP retransmission issues by restoring optimal TCP settings and removing network impairment",
            "tool_name": "fix_retransmissions"
        }
    ]

    created_targets = []
    
    for target_info in tool_targets:
        # Find the specific tool in the API spec
        tool_spec = None
        for tool in performance_api_spec:
            if tool["name"] == target_info["tool_name"]:
                tool_spec = tool
                break
        
        if not tool_spec:
            click.echo(f"⚠️  Tool {target_info['tool_name']} not found in API spec, skipping...")
            continue

        # Create target config with single tool
        target_config = {
            "mcp": {
                "lambda": {
                    "lambdaArn": performance_lambda_arn,
                    "toolSchema": {"inlinePayload": [tool_spec]},
                }
            }
        }

        try:
            click.echo(f"🔧 Creating target: {target_info['name']}")
            target_response = create_gateway_target_with_retry(
                gateway_id=gateway_id,
                name=target_info["name"],
                description=target_info["description"],
                target_config=target_config,
                credential_config=credential_config,
            )

            click.echo(f"✅ {target_info['name']} target created: {target_response['targetId']}")
            created_targets.append(target_info['name'])
            
            # Prevent API throttling when creating multiple targets sequentially
            if len(created_targets) < len(tool_targets):  # Don't wait after the last target
                click.echo("⏳ Waiting to prevent API throttling...")
                time.sleep(2)
            
        except Exception as e:
            click.echo(f"❌ Failed to create {target_info['name']} target: {e}")
            raise e

    click.echo(f"✅ Successfully created {len(created_targets)} performance targets")

    gateway = {
        "id": gateway_id,
        "name": gateway_name,
        "gateway_url": create_response["gatewayUrl"],
        "gateway_arn": create_response["gatewayArn"],
    }

    # Save gateway details to SSM parameters
    gateway_params = {
        "/a2a/app/performance/agentcore/gateway_id": gateway_id,
        "/a2a/app/performance/agentcore/gateway_name": gateway_name,
        "/a2a/app/performance/agentcore/gateway_arn": create_response["gatewayArn"],
        "/a2a/app/performance/agentcore/gateway_url": create_response["gatewayUrl"],
    }
    
    create_ssm_parameters(gateway_params)
    click.echo("✅ Gateway configuration saved to SSM parameters")

    return gateway


def delete_gateway(gateway_id: str) -> bool:
    """Delete a gateway and all its targets."""
    try:
        click.echo(f"🗑️  Deleting all targets for gateway: {gateway_id}")

        # List and delete all targets
        list_response = gateway_client.list_gateway_targets(
            gatewayIdentifier=gateway_id, maxResults=100
        )

        for item in list_response["items"]:
            target_id = item["targetId"]
            click.echo(f"   Deleting target: {target_id}")
            gateway_client.delete_gateway_target(
                gatewayIdentifier=gateway_id, targetId=target_id
            )
            click.echo(f"   ✅ Target {target_id} deleted")

        # Delete the gateway
        click.echo(f"🗑️  Deleting gateway: {gateway_id}")
        gateway_client.delete_gateway(gatewayIdentifier=gateway_id)
        click.echo(f"✅ Gateway {gateway_id} deleted successfully")

        return True

    except Exception as e:
        click.echo(f"❌ Error deleting gateway: {str(e)}", err=True)
        return False


def get_gateway_id_from_config() -> str:
    """Get gateway ID from SSM parameter."""
    try:
        return get_ssm_parameter("/a2a/app/performance/agentcore/gateway_id")
    except Exception as e:
        click.echo(f"❌ Error reading gateway ID from SSM: {str(e)}", err=True)
        return None


def create_targets_for_gateway(gateway_id: str) -> bool:
    """Create or update targets for an existing gateway."""
    try:
        # Wait for gateway to be active before creating targets
        if not wait_for_gateway_active(gateway_id):
            raise Exception("Gateway failed to become active within the timeout period")

        # Get Performance Lambda ARN from SSM
        click.echo("🔧 Creating/Updating Performance Analysis targets...")
        try:
            performance_lambda_arn = get_ssm_parameter("/a2a/app/performance/agentcore/lambda_arn")
            click.echo(f"📝 Performance Lambda ARN: {performance_lambda_arn}")
        except Exception as e:
            click.echo(f"❌ Failed to get Performance Lambda ARN from SSM: {e}")
            click.echo("💡 Make sure to deploy the performance lambda first:")
            click.echo("   ./prerequisite/lambda-performance/deploy-performance-tools.sh")
            raise e
        
        # Find performance API spec file
        performance_api_spec_paths = [
            "prerequisite/lambda-performance/api_spec.json",
            "../prerequisite/lambda-performance/api_spec.json",
            "./prerequisite/lambda-performance/api_spec.json"
        ]
        
        performance_api_spec = None
        for path in performance_api_spec_paths:
            if os.path.exists(path):
                performance_api_spec = load_api_spec(path)
                click.echo(f"📖 Loaded Performance API spec from: {path}")
                break
        
        if not performance_api_spec:
            error_msg = "Performance API specification not found in any expected location"
            click.echo(f"❌ {error_msg}")
            click.echo("🔍 Searched paths:")
            for path in performance_api_spec_paths:
                click.echo(f"   - {path}")
            raise Exception(error_msg)

        # Get existing targets to check for duplicates
        existing_targets = {}
        try:
            list_response = gateway_client.list_gateway_targets(
                gatewayIdentifier=gateway_id, maxResults=100
            )
            for item in list_response["items"]:
                existing_targets[item["name"]] = item["targetId"]
            click.echo(f"📋 Found {len(existing_targets)} existing targets")
        except Exception as e:
            click.echo(f"⚠️  Could not list existing targets: {e}")

        credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]

        # Create individual targets for each tool in the performance API spec
        tool_targets = [
            {
                "name": "FlowMonitorAnalysis",
                "description": "Analyze all Network Flow Monitors in a region and AWS account",
                "tool_name": "analyze_network_flow_monitor"
            },
            {
                "name": "TrafficMirrorLogs",
                "description": "Extract and analyze PCAP files from traffic mirroring S3 bucket",
                "tool_name": "analyze_traffic_mirroring_logs"
            },
            {
                "name": "FixRetransmissions",
                "description": "Fix TCP retransmission issues by restoring optimal TCP settings and removing network impairment",
                "tool_name": "fix_retransmissions"
            }
        ]

        created_targets = []
        updated_targets = []
        
        for target_info in tool_targets:
            # Find the specific tool in the API spec
            tool_spec = None
            for tool in performance_api_spec:
                if tool["name"] == target_info["tool_name"]:
                    tool_spec = tool
                    break
            
            if not tool_spec:
                click.echo(f"⚠️  Tool {target_info['tool_name']} not found in API spec, skipping...")
                continue

            # Create target config with single tool
            target_config = {
                "mcp": {
                    "lambda": {
                        "lambdaArn": performance_lambda_arn,
                        "toolSchema": {"inlinePayload": [tool_spec]},
                    }
                }
            }

            try:
                if target_info["name"] in existing_targets:
                    # Update existing target
                    click.echo(f"🔄 Updating target: {target_info['name']}")
                    gateway_client.update_gateway_target(
                        gatewayIdentifier=gateway_id,
                        targetId=existing_targets[target_info["name"]],
                        name=target_info["name"],
                        description=target_info["description"],
                        targetConfiguration=target_config,
                        credentialProviderConfigurations=credential_config,
                    )
                    click.echo(f"✅ {target_info['name']} target updated")
                    updated_targets.append(target_info['name'])
                else:
                    # Create new target
                    click.echo(f"🔧 Creating target: {target_info['name']}")
                    target_response = create_gateway_target_with_retry(
                        gateway_id=gateway_id,
                        name=target_info["name"],
                        description=target_info["description"],
                        target_config=target_config,
                        credential_config=credential_config,
                    )
                    click.echo(f"✅ {target_info['name']} target created: {target_response['targetId']}")
                    created_targets.append(target_info['name'])
                
                # Prevent API throttling when creating multiple targets sequentially
                if len(created_targets) + len(updated_targets) < len(tool_targets):
                    click.echo("⏳ Waiting to prevent API throttling...")
                    time.sleep(5)
                
            except Exception as e:
                click.echo(f"❌ Failed to create/update {target_info['name']} target: {e}")
                raise e

        click.echo(f"✅ Successfully created {len(created_targets)} new targets and updated {len(updated_targets)} existing targets")
        return True

    except Exception as e:
        click.echo(f"❌ Error managing gateway targets: {str(e)}", err=True)
        return False


@click.group()
@click.pass_context
def cli(ctx):
    """AgentCore Gateway Management CLI.

    Create and delete AgentCore gateways for the NetOps Performance application.
    """
    ctx.ensure_object(dict)


def find_existing_gateway_by_name(gateway_name: str) -> str:
    """Find existing gateway by name and return its ID."""
    try:
        # List all gateways and find one with matching name
        list_response = gateway_client.list_gateways(maxResults=100)
        
        for gateway in list_response.get("items", []):
            if gateway.get("name") == gateway_name:
                return gateway.get("gatewayId")
        
        return None
    except Exception as e:
        click.echo(f"⚠️  Could not list existing gateways: {e}")
        return None


@cli.command()
@click.option("--name", required=True, help="Name for the gateway")
@click.option("--update-existing", is_flag=True, help="If gateway exists, update its targets instead of failing")
def create(name, update_existing):
    """Create a new AgentCore gateway with DNS and connectivity tools (idempotent)."""
    click.echo(f"🚀 Creating AgentCore gateway: {name}")
    click.echo(f"📍 Region: {REGION}")

    # STEP 1: Check if gateway already exists
    click.echo(f"🔍 Checking if gateway '{name}' already exists...")
    existing_gateway_id = find_existing_gateway_by_name(name)
    
    if existing_gateway_id:
        click.echo(f"✅ Gateway '{name}' already exists (ID: {existing_gateway_id})")
        
        # Update SSM parameters with existing gateway info
        try:
            gateway_response = gateway_client.get_gateway(gatewayIdentifier=existing_gateway_id)
            gateway_params = {
                "/a2a/app/performance/agentcore/gateway_id": existing_gateway_id,
                "/a2a/app/performance/agentcore/gateway_name": name,
                "/a2a/app/performance/agentcore/gateway_arn": gateway_response.get("gatewayArn", ""),
                "/a2a/app/performance/agentcore/gateway_url": gateway_response.get("gatewayUrl", ""),
            }
            create_ssm_parameters(gateway_params)
            click.echo("✅ Gateway configuration updated in SSM parameters")
        except Exception as ssm_error:
            click.echo(f"⚠️  Could not update SSM parameters: {ssm_error}")
        
        if update_existing:
            click.echo("🔄 Updating targets for existing gateway...")
            try:
                if create_targets_for_gateway(existing_gateway_id):
                    click.echo("🎉 Gateway targets updated successfully")
                else:
                    click.echo("❌ Failed to update gateway targets", err=True)
                    sys.exit(1)
            except Exception as update_error:
                click.echo(f"❌ Failed to update targets: {str(update_error)}", err=True)
                sys.exit(1)
        else:
            click.echo("ℹ️  Gateway already configured, skipping creation")
            click.echo("💡 Use --update-existing flag to add/update targets for the existing gateway")
            click.echo(f"   Or use: python3 scripts/agentcore_gateway.py add-targets --gateway-id {existing_gateway_id}")
        
        return

    # STEP 2: Create new gateway (only if doesn't exist)
    click.echo(f"🆕 Creating new gateway: {name}")
    try:
        gateway = create_gateway(gateway_name=name)
        click.echo(f"🎉 Gateway created successfully with ID: {gateway['id']}")

    except Exception as e:
        error_str = str(e)
        
        # Handle race condition - gateway was created between our check and create attempt
        if "ConflictException" in error_str and "already exists" in error_str:
            click.echo(f"⚠️  Gateway was created concurrently, fetching details...")
            
            # Try to find the gateway that was created
            existing_gateway_id = find_existing_gateway_by_name(name)
            
            if existing_gateway_id:
                click.echo(f"✅ Found gateway: {existing_gateway_id}")
                
                # Update SSM parameters
                try:
                    gateway_response = gateway_client.get_gateway(gatewayIdentifier=existing_gateway_id)
                    gateway_params = {
                        "/a2a/app/performance/agentcore/gateway_id": existing_gateway_id,
                        "/a2a/app/performance/agentcore/gateway_name": name,
                        "/a2a/app/performance/agentcore/gateway_arn": gateway_response.get("gatewayArn", ""),
                        "/a2a/app/performance/agentcore/gateway_url": gateway_response.get("gatewayUrl", ""),
                    }
                    create_ssm_parameters(gateway_params)
                    click.echo("✅ Gateway configuration saved to SSM parameters")
                except Exception as ssm_error:
                    click.echo(f"⚠️  Could not update SSM parameters: {ssm_error}")
                
                click.echo("🎉 Gateway setup complete")
            else:
                click.echo("❌ Could not find gateway details after concurrent creation")
                sys.exit(1)
        else:
            click.echo(f"❌ Failed to create gateway: {error_str}", err=True)
            sys.exit(1)


@cli.command()
@click.option(
    "--gateway-id",
    help="Gateway ID to delete (if not provided, will read from SSM)",
)
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete(gateway_id, confirm):
    """Delete an AgentCore gateway and all its targets."""

    # If no gateway ID provided, try to read from config
    if not gateway_id:
        gateway_id = get_gateway_id_from_config()
        if not gateway_id:
            click.echo(
                "❌ No gateway ID provided and couldn't read from SSM parameters",
                err=True,
            )
            sys.exit(1)
        click.echo(f"📖 Using gateway ID from SSM: {gateway_id}")

    # Confirmation prompt
    if not confirm:
        if not click.confirm(
            f"⚠️  Are you sure you want to delete gateway {gateway_id}? This action cannot be undone."
        ):
            click.echo("❌ Operation cancelled")
            sys.exit(0)

    click.echo(f"🗑️  Deleting gateway: {gateway_id}")

    if delete_gateway(gateway_id):
        click.echo("✅ Gateway deleted successfully")

        # Clean up SSM parameters
        gateway_params = [
            "/a2a/app/performance/agentcore/gateway_id",
            "/a2a/app/performance/agentcore/gateway_name", 
            "/a2a/app/performance/agentcore/gateway_arn",
            "/a2a/app/performance/agentcore/gateway_url",
        ]
        
        delete_ssm_parameters(gateway_params)
        click.echo("🧹 Removed gateway SSM parameters")
        click.echo("🎉 Gateway and configuration deleted successfully")
    else:
        click.echo("❌ Failed to delete gateway", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--gateway-id",
    help="Gateway ID to add/update targets for (if not provided, will read from SSM)",
)
def add_targets(gateway_id):
    """Add or update targets for an existing AgentCore gateway."""

    # If no gateway ID provided, try to read from config
    if not gateway_id:
        gateway_id = get_gateway_id_from_config()
        if not gateway_id:
            click.echo(
                "❌ No gateway ID provided and couldn't read from SSM parameters",
                err=True,
            )
            sys.exit(1)
        click.echo(f"📖 Using gateway ID from SSM: {gateway_id}")

    click.echo(f"🎯 Adding/updating targets for gateway: {gateway_id}")
    click.echo(f"📍 Region: {REGION}")

    try:
        if create_targets_for_gateway(gateway_id):
            click.echo("🎉 Gateway targets added/updated successfully")
        else:
            click.echo("❌ Failed to add/update gateway targets", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"❌ Failed to add/update targets: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--gateway-id",
    help="Gateway ID to list targets for (if not provided, will read from SSM)",
)
def list_targets(gateway_id):
    """List all targets for an existing AgentCore gateway."""

    # If no gateway ID provided, try to read from config
    if not gateway_id:
        gateway_id = get_gateway_id_from_config()
        if not gateway_id:
            click.echo(
                "❌ No gateway ID provided and couldn't read from SSM parameters",
                err=True,
            )
            sys.exit(1)
        click.echo(f"📖 Using gateway ID from SSM: {gateway_id}")

    click.echo(f"📋 Listing targets for gateway: {gateway_id}")

    try:
        list_response = gateway_client.list_gateway_targets(
            gatewayIdentifier=gateway_id, maxResults=100
        )

        if not list_response["items"]:
            click.echo("📭 No targets found for this gateway")
            return

        click.echo(f"🎯 Found {len(list_response['items'])} targets:")
        click.echo()
        
        for item in list_response["items"]:
            click.echo(f"  • Name: {item['name']}")
            click.echo(f"    ID: {item['targetId']}")
            click.echo(f"    Description: {item.get('description', 'N/A')}")
            click.echo(f"    Status: {item.get('status', 'N/A')}")
            click.echo()

    except Exception as e:
        click.echo(f"❌ Failed to list targets: {str(e)}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
