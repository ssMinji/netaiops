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
    try:
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
            description="AgentCore performance Gateway",
        )

        click.echo(f"✅ Gateway created: {create_response['gatewayId']}")

        gateway_id = create_response["gatewayId"]
        
        # Wait for gateway to become ACTIVE before adding targets
        if not wait_for_gateway_active(gateway_id):
            click.echo("❌ Gateway did not become ACTIVE in time. Cannot add targets.")
            click.echo("   You can try adding targets later by recreating the gateway.")
            # Save gateway details even if targets couldn't be added
            gateway = {
                "id": gateway_id,
                "name": gateway_name,
                "gateway_url": create_response["gatewayUrl"],
                "gateway_arn": create_response["gatewayArn"],
            }
            gateway_params = {
                "/a2a/app/troubleshooting/agentcore/gateway_id": gateway_id,
                "/a2a/app/troubleshooting/agentcore/gateway_name": gateway_name,
                "/a2a/app/troubleshooting/agentcore/gateway_arn": create_response["gatewayArn"],
                "/a2a/app/troubleshooting/agentcore/gateway_url": create_response["gatewayUrl"],
            }
            create_ssm_parameters(gateway_params)
            return gateway

        credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]

        # Target 1: DNS Resolution Tool
        try:
            dns_lambda_arn = get_ssm_parameter("/a2a/app/troubleshooting/agentcore/dns_lambda_arn")
            
            # Find DNS API spec file
            dns_api_spec_paths = [
                "prerequisite/lambda-dns/api_spec.json",
                "../prerequisite/lambda-dns/api_spec.json", 
                "./prerequisite/lambda-dns/api_spec.json"
            ]
            
            dns_api_spec = None
            for path in dns_api_spec_paths:
                if os.path.exists(path):
                    dns_api_spec = load_api_spec(path)
                    click.echo(f"📖 Loaded DNS API spec from: {path}")
                    break
            
            if not dns_api_spec:
                raise Exception("DNS API specification not found in any expected location")
            
            dns_config = {
                "mcp": {
                    "lambda": {
                        "lambdaArn": dns_lambda_arn,
                        "toolSchema": {"inlinePayload": dns_api_spec},
                    }
                }
            }

            dns_target_response = create_gateway_target_with_retry(
                gateway_id=gateway_id,
                name="DNSResolutionTool", 
                description="Resolves DNS names to Instance IDs",
                target_config=dns_config,
                credential_config=credential_config,
            )

            click.echo(f"✅ DNS Resolution target created: {dns_target_response['targetId']}")
            
            # Prevent API throttling when creating multiple targets sequentially
            click.echo("⏳ Waiting to prevent API throttling...")
            throttling_delay = 2
            # INTENTIONAL DELAY: AWS Bedrock AgentCore API rate limiting between target creations
            time.sleep(throttling_delay)  # nosemgrep: arbitrary-sleep
            
        except Exception as dns_error:
            click.echo(f"⚠️  DNS Resolution tool not available: {dns_error}")
            click.echo("   Deploy dns-resolve-tool first, then recreate gateway")


        # Target 3: Connectivity Fix Tool (Separate Lambda)
        try:
            connectivity_fix_lambda_arn = get_ssm_parameter("/a2a/app/troubleshooting/agentcore/connectivity_fix_lambda_arn")
            
            # Find connectivity-fix API spec file
            connectivity_fix_api_spec_paths = [
                "prerequisite/lambda-fix/api_spec.json",
                "../prerequisite/lambda-fix/api_spec.json",
                "./prerequisite/lambda-fix/api_spec.json"
            ]
            
            connectivity_fix_api_spec = None
            for path in connectivity_fix_api_spec_paths:
                if os.path.exists(path):
                    connectivity_fix_api_spec = load_api_spec(path)
                    click.echo(f"📖 Loaded Connectivity Fix API spec from: {path}")
                    break
            
            if not connectivity_fix_api_spec:
                raise Exception("Connectivity Fix API specification not found in any expected location")

            connectivity_fix_config = {
                "mcp": {
                    "lambda": {
                        "lambdaArn": connectivity_fix_lambda_arn,
                        "toolSchema": {"inlinePayload": connectivity_fix_api_spec},
                    }
                }
            }

            connectivity_fix_target_response = create_gateway_target_with_retry(
                gateway_id=gateway_id,
                name="ConnectivityFixTool",
                description="Fixes Network Connectivity Issues",
                target_config=connectivity_fix_config,
                credential_config=credential_config,
            )

            click.echo(f"✅ Connectivity Fix target created: {connectivity_fix_target_response['targetId']}")
            
        except Exception as connectivity_fix_error:
            click.echo(f"⚠️  Connectivity Fix tool not available: {connectivity_fix_error}")
            click.echo("   Deploy lambda-fix tool first: cd prerequisite/lambda-fix && ./deploy-connectivity-fix-tool.sh")

        gateway = {
            "id": gateway_id,
            "name": gateway_name,
            "gateway_url": create_response["gatewayUrl"],
            "gateway_arn": create_response["gatewayArn"],
        }

        # Save gateway details to SSM parameters
        gateway_params = {
            "/a2a/app/troubleshooting/agentcore/gateway_id": gateway_id,
            "/a2a/app/troubleshooting/agentcore/gateway_name": gateway_name,
            "/a2a/app/troubleshooting/agentcore/gateway_arn": create_response["gatewayArn"],
            "/a2a/app/troubleshooting/agentcore/gateway_url": create_response["gatewayUrl"],
        }
        
        create_ssm_parameters(gateway_params)
        click.echo("✅ Gateway configuration saved to SSM parameters")

        return gateway

    except Exception as e:
        click.echo(f"❌ Error creating gateway: {str(e)}", err=True)
        sys.exit(1)


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
        return get_ssm_parameter("/a2a/app/troubleshooting/agentcore/gateway_id")
    except Exception as e:
        click.echo(f"❌ Error reading gateway ID from SSM: {str(e)}", err=True)
        return None


def find_existing_gateway_by_name(gateway_name: str) -> dict:
    """Check if a gateway with the given name already exists.
    
    Returns:
        dict with gateway details if found, None otherwise
    """
    try:
        click.echo(f"🔍 Checking for existing gateway: {gateway_name}")
        
        # List all gateways (paginated if necessary)
        list_response = gateway_client.list_gateways(maxResults=100)
        
        for item in list_response.get("items", []):
            if item.get("name") == gateway_name:
                gateway_id = item["gatewayId"]
                click.echo(f"✅ Found existing gateway: {gateway_name} (ID: {gateway_id})")
                
                # Get full gateway details
                gateway_details = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
                
                return {
                    "id": gateway_id,
                    "name": gateway_details.get("name"),
                    "gateway_url": gateway_details.get("gatewayUrl"),
                    "gateway_arn": gateway_details.get("gatewayArn"),
                    "status": gateway_details.get("status"),
                }
        
        click.echo(f"ℹ️  No existing gateway found with name: {gateway_name}")
        return None
        
    except Exception as e:
        click.echo(f"⚠️  Error checking for existing gateway: {str(e)}")
        return None


@click.group()
@click.pass_context
def cli(ctx):
    """AgentCore Gateway Management CLI.

    Create and delete AgentCore gateways for the NetOps performance application.
    """
    ctx.ensure_object(dict)


@cli.command()
@click.option("--name", required=True, help="Name for the gateway")
def create(name):
    """Create a new AgentCore gateway with DNS and connectivity tools (idempotent)."""
    click.echo(f"🚀 Creating AgentCore gateway: {name}")
    click.echo(f"📍 Region: {REGION}")

    try:
        # STEP 1: Check if gateway already exists
        existing_gateway = find_existing_gateway_by_name(name)
        
        if existing_gateway:
            click.echo(f"✅ Gateway '{name}' already exists")
            click.echo(f"   Gateway ID: {existing_gateway['id']}")
            click.echo(f"   Status: {existing_gateway.get('status', 'UNKNOWN')}")
            click.echo(f"ℹ️  Skipping creation - updating SSM parameters with existing gateway info")
            
            # Update SSM parameters with existing gateway info
            gateway_params = {
                "/a2a/app/troubleshooting/agentcore/gateway_id": existing_gateway['id'],
                "/a2a/app/troubleshooting/agentcore/gateway_name": name,
                "/a2a/app/troubleshooting/agentcore/gateway_arn": existing_gateway['gateway_arn'],
                "/a2a/app/troubleshooting/agentcore/gateway_url": existing_gateway['gateway_url'],
            }
            create_ssm_parameters(gateway_params)
            click.echo("✅ SSM parameters updated with existing gateway details")
            click.echo(f"🎉 Gateway configuration complete")
            return
        
        # STEP 2: Create new gateway (only if doesn't exist)
        gateway = create_gateway(gateway_name=name)
        click.echo(f"🎉 Gateway created successfully with ID: {gateway['id']}")

    except Exception as e:
        # Check if error indicates gateway already exists (race condition)
        if 'already exists' in str(e).lower() or 'ConflictException' in str(e):
            click.echo(f"ℹ️  Gateway was created concurrently, fetching details...")
            existing_gateway = find_existing_gateway_by_name(name)
            if existing_gateway:
                click.echo(f"✅ Using existing gateway: {existing_gateway['id']}")
                return
        
        click.echo(f"❌ Failed to create gateway: {str(e)}", err=True)
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
            "/a2a/app/troubleshooting/agentcore/gateway_id",
            "/a2a/app/troubleshooting/agentcore/gateway_name", 
            "/a2a/app/troubleshooting/agentcore/gateway_arn",
            "/a2a/app/troubleshooting/agentcore/gateway_url",
        ]
        
        delete_ssm_parameters(gateway_params)
        click.echo("🧹 Removed gateway SSM parameters")
        click.echo("🎉 Gateway and configuration deleted successfully")
    else:
        click.echo("❌ Failed to delete gateway", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
