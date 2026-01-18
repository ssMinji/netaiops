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
    """Create an AgentCore gateway with DNS, connectivity, and CloudWatch tools."""
    try:
        auth_config = {
            "customJWTAuthorizer": {
                "allowedClients": [
                    get_ssm_parameter(
                        "/app/troubleshooting/agentcore/machine_client_id"
                    )
                ],
                "discoveryUrl": get_ssm_parameter(
                    "/app/troubleshooting/agentcore/cognito_discovery_url"
                ),
            }
        }

        execution_role_arn = get_ssm_parameter(
            "/app/troubleshooting/agentcore/gateway_iam_role"
        )

        click.echo(f"Creating gateway in region {REGION} with name: {gateway_name}")
        click.echo(f"Execution role ARN: {execution_role_arn}")

        create_response = gateway_client.create_gateway(
            name=gateway_name,
            roleArn=execution_role_arn,
            protocolType="MCP",
            authorizerType="CUSTOM_JWT",
            authorizerConfiguration=auth_config,
            description="AgentCore Troubleshooting Gateway",
        )

        click.echo(f"✅ Gateway created: {create_response['gatewayId']}")

        credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
        gateway_id = create_response["gatewayId"]

        # Wait for gateway to be ready before adding targets
        click.echo("⏳ Waiting for gateway to be ready for target creation...")
        max_wait = 300  # 5 minutes
        wait_interval = 10  # 10 seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                response = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
                status = response.get('status', 'UNKNOWN')
                
                if status in ['ACTIVE', 'READY']:
                    click.echo("✅ Gateway is ready for target creation")
                    break
                elif status in ['FAILED', 'DELETING', 'DELETED']:
                    click.echo(f"❌ Gateway is in {status} status - cannot add targets")
                    return gateway
                else:
                    click.echo(f"   Gateway status: {status} - waiting...")
                    time.sleep(wait_interval)
                    
            except ClientError as e:
                click.echo(f"   Error checking gateway status: {e}")
                time.sleep(wait_interval)
        else:
            click.echo("⚠️  Timeout waiting for gateway to be ready - proceeding anyway")

        # Target 1: DNS Resolution Tool
        try:
            dns_lambda_arn = get_ssm_parameter("/app/troubleshooting/agentcore/dns_lambda_arn")
            
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

        # Target 2: Consolidated Connectivity Tool (replaces lambda-check + lambda-fix)
        try:
            connectivity_lambda_arn = get_ssm_parameter("/app/troubleshooting/agentcore/connectivity_lambda_arn")
            
            # Find consolidated connectivity API spec file
            connectivity_api_spec_paths = [
                "prerequisite/lambda-connectivity/api_spec.json",
                "../prerequisite/lambda-connectivity/api_spec.json",
                "./prerequisite/lambda-connectivity/api_spec.json"
            ]
            
            connectivity_api_spec = None
            for path in connectivity_api_spec_paths:
                if os.path.exists(path):
                    connectivity_api_spec = load_api_spec(path)
                    click.echo(f"📖 Loaded Consolidated Connectivity API spec from: {path}")
                    break
            
            if not connectivity_api_spec:
                raise Exception("Consolidated Connectivity API specification not found in any expected location")

            connectivity_config = {
                "mcp": {
                    "lambda": {
                        "lambdaArn": connectivity_lambda_arn,
                        "toolSchema": {"inlinePayload": connectivity_api_spec},
                    }
                }
            }

            connectivity_target_response = create_gateway_target_with_retry(
                gateway_id=gateway_id,
                name="ConnectivityTool",
                description="Unified Connectivity Check and Fix Tool",
                target_config=connectivity_config,
                credential_config=credential_config,
            )

            click.echo(f"✅ Consolidated Connectivity target created: {connectivity_target_response['targetId']}")
            
            # Prevent API throttling when creating multiple targets sequentially
            click.echo("⏳ Waiting to prevent API throttling...")
            throttling_delay = 2
            # INTENTIONAL DELAY: AWS Bedrock AgentCore API rate limiting between target creations
            time.sleep(throttling_delay)  # nosemgrep: arbitrary-sleep
            
        except Exception as connectivity_error:
            click.echo(f"⚠️  Consolidated Connectivity tool not available: {connectivity_error}")
            click.echo("   Deploy connectivity tool first: cd prerequisite/lambda-connectivity && ./deploy-connectivity-tool.sh")

        # Target 3: CloudWatch Tool (consolidated monitoring)
        try:
            cloudwatch_lambda_arn = get_ssm_parameter("/app/troubleshooting/agentcore/cloudwatch_lambda_arn")
            
            # Find CloudWatch API spec file
            cloudwatch_api_spec_paths = [
                "prerequisite/lambda-cloudwatch/api_spec.json",
                "../prerequisite/lambda-cloudwatch/api_spec.json",
                "./prerequisite/lambda-cloudwatch/api_spec.json"
            ]
            
            cloudwatch_api_spec = None
            for path in cloudwatch_api_spec_paths:
                if os.path.exists(path):
                    cloudwatch_api_spec = load_api_spec(path)
                    click.echo(f"📖 Loaded CloudWatch API spec from: {path}")
                    break
            
            if not cloudwatch_api_spec:
                raise Exception("CloudWatch API specification not found in any expected location")

            cloudwatch_config = {
                "mcp": {
                    "lambda": {
                        "lambdaArn": cloudwatch_lambda_arn,
                        "toolSchema": {"inlinePayload": cloudwatch_api_spec},
                    }
                }
            }

            cloudwatch_target_response = create_gateway_target_with_retry(
                gateway_id=gateway_id,
                name="CloudWatchTool",
                description="CloudWatch Monitoring and Analysis Tool",
                target_config=cloudwatch_config,
                credential_config=credential_config,
            )

            click.echo(f"✅ CloudWatch target created: {cloudwatch_target_response['targetId']}")
            
        except Exception as cloudwatch_error:
            click.echo(f"⚠️  CloudWatch tool not available: {cloudwatch_error}")
            click.echo("   Deploy CloudWatch tool first: cd prerequisite/lambda-cloudwatch && ./deploy-cloudwatch-tool.sh")

        gateway = {
            "id": gateway_id,
            "name": gateway_name,
            "gateway_url": create_response["gatewayUrl"],
            "gateway_arn": create_response["gatewayArn"],
        }

        # Save gateway details to SSM parameters
        gateway_params = {
            "/app/troubleshooting/agentcore/gateway_id": gateway_id,
            "/app/troubleshooting/agentcore/gateway_name": gateway_name,
            "/app/troubleshooting/agentcore/gateway_arn": create_response["gatewayArn"],
            "/app/troubleshooting/agentcore/gateway_url": create_response["gatewayUrl"],
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
        return get_ssm_parameter("/app/troubleshooting/agentcore/gateway_id")
    except Exception as e:
        click.echo(f"❌ Error reading gateway ID from SSM: {str(e)}", err=True)
        return None


@click.group()
@click.pass_context
def cli(ctx):
    """AgentCore Gateway Management CLI.

    Create and delete AgentCore gateways for the NetOps troubleshooting application.
    """
    ctx.ensure_object(dict)


@cli.command()
@click.option("--name", required=True, help="Name for the gateway")
def create(name):
    """Create a new AgentCore gateway with DNS, connectivity, and CloudWatch tools."""
    click.echo(f"🚀 Creating AgentCore gateway: {name}")
    click.echo(f"📍 Region: {REGION}")

    try:
        gateway = create_gateway(gateway_name=name)
        click.echo(f"🎉 Gateway created successfully with ID: {gateway['id']}")

    except Exception as e:
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
            "/app/troubleshooting/agentcore/gateway_id",
            "/app/troubleshooting/agentcore/gateway_name", 
            "/app/troubleshooting/agentcore/gateway_arn",
            "/app/troubleshooting/agentcore/gateway_url",
        ]
        
        delete_ssm_parameters(gateway_params)
        click.echo("🧹 Removed gateway SSM parameters")
        click.echo("🎉 Gateway and configuration deleted successfully")
    else:
        click.echo("❌ Failed to delete gateway", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
