#!/usr/bin/python
"""
AgentCore Gateway for K8s Diagnostics Agent

Creates an MCP Gateway with mcpServer targets pointing to the
eks-mcp-server AgentCore Runtime endpoint. This allows the K8s Agent
to access all EKS diagnostic tools through the Gateway aggregation layer.

Architecture:
    K8s Agent -> MCP Gateway -> mcpServer target -> eks-mcp-server Runtime

When new EKS-related MCP servers are added, they can be registered as
additional mcpServer targets on this gateway without changing agent code.
"""

import os
import sys
import time
import urllib.parse
import boto3
import click
from botocore.exceptions import ClientError

from utils import (
    get_aws_region,
    get_ssm_parameter,
    create_ssm_parameters,
    delete_ssm_parameters,
)


REGION = get_aws_region()

gateway_client = boto3.client(
    "bedrock-agentcore-control",
    region_name=REGION,
)

cognito_client = boto3.client(
    "cognito-idp",
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
                    raise e
                delay = initial_delay * (backoff_multiplier ** attempt)
                click.echo(f"Rate limit hit, waiting {delay}s before retry (attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise e
    return None


def wait_for_gateway_active(gateway_id, max_wait_time=300, check_interval=10):
    """Wait for gateway to be in ACTIVE or READY state before proceeding."""
    click.echo(f"Waiting for gateway {gateway_id} to be ready...")
    start_time = time.time()

    while time.time() - start_time < max_wait_time:
        try:
            response = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
            status = response.get('status', 'UNKNOWN')

            if status in ['ACTIVE', 'READY']:
                click.echo(f"Gateway is now ready (status: {status})")
                return True
            elif status in ['FAILED', 'DELETING', 'DELETED']:
                click.echo(f"Gateway is in {status} state")
                return False
            else:
                click.echo(f"   Gateway status: {status}, waiting {check_interval}s...")
                time.sleep(check_interval)
        except Exception as e:
            click.echo(f"   Error checking gateway status: {e}, retrying...")
            time.sleep(check_interval)

    click.echo(f"Timeout waiting for gateway to be ready after {max_wait_time}s")
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


def get_runtime_endpoint_url(runtime_arn: str) -> str:
    """Construct the MCP Runtime endpoint URL from the ARN.

    Follows the official agentcore-mcp-toolkit pattern:
    https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{url_encoded_arn}/invocations?qualifier=DEFAULT
    """
    encoded_arn = urllib.parse.quote(runtime_arn, safe='')
    return f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"


def create_oauth2_credential_provider(provider_name: str) -> str:
    """Create an OAuth2 credential provider for Gateway-to-Runtime auth.

    Reads the Runtime Cognito details from SSM parameters and creates
    an AgentCore OAuth2 credential provider.

    Returns the provider ARN.
    """
    client_id = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_client_id")
    client_secret = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_client_secret")
    token_url = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_token_url")
    scope = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_auth_scope")

    if not all([client_id, client_secret, token_url, scope]):
        raise ValueError("Missing Runtime Cognito SSM parameters. Deploy CloudFormation stack first.")

    click.echo(f"Creating OAuth2 credential provider: {provider_name}")
    click.echo(f"Token URL: {token_url}")

    # Check if provider already exists
    try:
        existing = gateway_client.list_oauth2_credential_providers()
        for p in existing.get('oauth2CredentialProviders', []):
            if p.get('name') == provider_name:
                click.echo(f"OAuth2 provider '{provider_name}' already exists")
                provider_detail = gateway_client.get_oauth2_credential_provider(
                    oauth2CredentialProviderName=provider_name
                )
                return provider_detail.get('credentialProviderArn')
    except Exception as e:
        click.echo(f"Warning checking existing providers: {e}")

    response = gateway_client.create_oauth2_credential_provider(
        name=provider_name,
        credentialProviderVendor="CustomOAuth",
        oauth2ProviderConfigInput={
            "customOAuthProviderConfig": {
                "tokenUrl": token_url,
                "clientId": client_id,
                "clientSecret": client_secret,
            }
        },
    )

    provider_arn = response.get('credentialProviderArn')
    click.echo(f"OAuth2 credential provider created: {provider_arn}")

    # Wait for provider to be ready
    for _ in range(30):
        try:
            detail = gateway_client.get_oauth2_credential_provider(
                oauth2CredentialProviderName=provider_name
            )
            status = detail.get('status', 'UNKNOWN')
            if status in ['ACTIVE', 'READY', 'CREATED']:
                click.echo(f"OAuth2 provider is ready (status: {status})")
                break
            click.echo(f"   OAuth2 provider status: {status}, waiting...")
            time.sleep(5)
        except Exception:
            time.sleep(5)

    return provider_arn


def create_gateway(gateway_name: str) -> dict:
    """Create an AgentCore gateway with eks-mcp-server targets."""
    auth_config = {
        "customJWTAuthorizer": {
            "allowedClients": [
                get_ssm_parameter("/a2a/app/k8s/agentcore/machine_client_id")
            ],
            "discoveryUrl": get_ssm_parameter(
                "/a2a/app/k8s/agentcore/cognito_discovery_url"
            ),
        }
    }

    execution_role_arn = get_ssm_parameter(
        "/a2a/app/k8s/agentcore/gateway_iam_role"
    )

    click.echo(f"Creating gateway in region {REGION} with name: {gateway_name}")
    click.echo(f"Execution role ARN: {execution_role_arn}")

    create_response = gateway_client.create_gateway(
        name=gateway_name,
        roleArn=execution_role_arn,
        protocolType="MCP",
        authorizerType="CUSTOM_JWT",
        authorizerConfiguration=auth_config,
        description="AgentCore K8s Diagnostics Gateway",
    )

    click.echo(f"Gateway created: {create_response['gatewayId']}")

    gateway_id = create_response["gatewayId"]

    # Wait for gateway to become ACTIVE before adding targets
    if not wait_for_gateway_active(gateway_id):
        click.echo("Gateway did not become ACTIVE in time.")
        gateway = {
            "id": gateway_id,
            "name": gateway_name,
            "gateway_url": create_response["gatewayUrl"],
            "gateway_arn": create_response["gatewayArn"],
        }
        gateway_params = {
            "/a2a/app/k8s/agentcore/gateway_id": gateway_id,
            "/a2a/app/k8s/agentcore/gateway_name": gateway_name,
            "/a2a/app/k8s/agentcore/gateway_arn": create_response["gatewayArn"],
            "/a2a/app/k8s/agentcore/gateway_url": create_response["gatewayUrl"],
        }
        create_ssm_parameters(gateway_params)
        return gateway

    # ---- Create OAuth2 credential provider for Gateway→Runtime auth ----
    # mcpServer targets require OAUTH credential type (not GATEWAY_IAM_ROLE)
    oauth_provider_name = "eks-mcp-server-oauth"
    scope = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_auth_scope")

    try:
        oauth_provider_arn = create_oauth2_credential_provider(oauth_provider_name)
    except Exception as e:
        click.echo(f"Failed to create OAuth2 credential provider: {e}")
        click.echo("Ensure CloudFormation stack is deployed with Runtime Cognito resources.")
        oauth_provider_arn = None

    # ---- Target: EKS MCP Server (mcpServer type) ----
    # Points to the eks-mcp-server AgentCore Runtime endpoint
    try:
        eks_mcp_arn = get_ssm_parameter(
            "/a2a/app/k8s/agentcore/eks_mcp_server_arn"
        )
        if not eks_mcp_arn:
            raise ValueError("EKS MCP Server ARN not found in SSM. Deploy eks-mcp-server first.")

        eks_mcp_endpoint = get_runtime_endpoint_url(eks_mcp_arn)
        click.echo(f"EKS MCP Server endpoint: {eks_mcp_endpoint}")

        eks_mcp_target_config = {
            "mcp": {
                "mcpServer": {
                    "endpoint": eks_mcp_endpoint,
                }
            }
        }

        if not oauth_provider_arn:
            raise ValueError("OAuth2 credential provider ARN not available")

        credential_config = [{
            "credentialProviderType": "OAUTH",
            "credentialProvider": {
                "oauthCredentialProvider": {
                    "providerArn": oauth_provider_arn,
                    "scopes": [scope],
                }
            },
        }]

        eks_target_response = create_gateway_target_with_retry(
            gateway_id=gateway_id,
            name="EksMcpServer",
            description="Official AWS Labs EKS MCP Server - cluster diagnostics, resource management, logs, metrics",
            target_config=eks_mcp_target_config,
            credential_config=credential_config,
        )

        click.echo(f"EKS MCP Server target created: {eks_target_response['targetId']}")

    except Exception as e:
        click.echo(f"EKS MCP Server target not available: {e}")
        click.echo("Deploy eks-mcp-server first:")
        click.echo("   cd prerequisite/eks-mcp-server && ./deploy-eks-mcp-server.sh")

    gateway = {
        "id": gateway_id,
        "name": gateway_name,
        "gateway_url": create_response["gatewayUrl"],
        "gateway_arn": create_response["gatewayArn"],
    }

    # Save gateway details to SSM
    gateway_params = {
        "/a2a/app/k8s/agentcore/gateway_id": gateway_id,
        "/a2a/app/k8s/agentcore/gateway_name": gateway_name,
        "/a2a/app/k8s/agentcore/gateway_arn": create_response["gatewayArn"],
        "/a2a/app/k8s/agentcore/gateway_url": create_response["gatewayUrl"],
    }

    create_ssm_parameters(gateway_params)
    click.echo("Gateway configuration saved to SSM parameters")

    return gateway


def delete_gateway(gateway_id: str) -> bool:
    """Delete a gateway and all its targets."""
    try:
        click.echo(f"Deleting all targets for gateway: {gateway_id}")

        list_response = gateway_client.list_gateway_targets(
            gatewayIdentifier=gateway_id, maxResults=100
        )

        for item in list_response["items"]:
            target_id = item["targetId"]
            click.echo(f"   Deleting target: {target_id}")
            gateway_client.delete_gateway_target(
                gatewayIdentifier=gateway_id, targetId=target_id
            )
            click.echo(f"   Target {target_id} deleted")

        click.echo(f"Deleting gateway: {gateway_id}")
        gateway_client.delete_gateway(gatewayIdentifier=gateway_id)
        click.echo(f"Gateway {gateway_id} deleted successfully")

        return True

    except Exception as e:
        click.echo(f"Error deleting gateway: {str(e)}", err=True)
        return False


def get_gateway_id_from_config() -> str:
    """Get gateway ID from SSM parameter."""
    try:
        return get_ssm_parameter("/a2a/app/k8s/agentcore/gateway_id")
    except Exception as e:
        click.echo(f"Error reading gateway ID from SSM: {str(e)}", err=True)
        return None


def find_existing_gateway_by_name(gateway_name: str) -> dict:
    """Check if a gateway with the given name already exists."""
    try:
        list_response = gateway_client.list_gateways(maxResults=100)

        for item in list_response.get("items", []):
            if item.get("name") == gateway_name:
                gateway_id = item["gatewayId"]
                gateway_details = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
                return {
                    "id": gateway_id,
                    "name": gateway_details.get("name"),
                    "gateway_url": gateway_details.get("gatewayUrl"),
                    "gateway_arn": gateway_details.get("gatewayArn"),
                    "status": gateway_details.get("status"),
                }

        return None

    except Exception as e:
        click.echo(f"Error checking for existing gateway: {str(e)}")
        return None


def add_mcp_server_target(gateway_id: str, name: str, description: str, endpoint: str, oauth_provider_arn: str = None) -> bool:
    """Add a new mcpServer target to an existing gateway.

    Use this to register additional EKS-related MCP servers as gateway targets.

    Args:
        gateway_id: The gateway to add the target to
        name: Target name (e.g. 'EksMonitoringMcp')
        description: Target description
        endpoint: HTTPS endpoint of the MCP server
        oauth_provider_arn: OAuth2 credential provider ARN (required for mcpServer targets)
    """
    try:
        if not wait_for_gateway_active(gateway_id):
            click.echo("Gateway is not active")
            return False

        scope = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_auth_scope")

        if not oauth_provider_arn:
            oauth_provider_arn = create_oauth2_credential_provider("eks-mcp-server-oauth")

        credential_config = [{
            "credentialProviderType": "OAUTH",
            "credentialProvider": {
                "oauthCredentialProvider": {
                    "providerArn": oauth_provider_arn,
                    "scopes": [scope],
                }
            },
        }]

        target_config = {
            "mcp": {
                "mcpServer": {
                    "endpoint": endpoint,
                }
            }
        }

        response = create_gateway_target_with_retry(
            gateway_id=gateway_id,
            name=name,
            description=description,
            target_config=target_config,
            credential_config=credential_config,
        )

        click.echo(f"Target '{name}' created: {response['targetId']}")
        return True

    except Exception as e:
        click.echo(f"Failed to add target: {str(e)}", err=True)
        return False


@click.group()
@click.pass_context
def cli(ctx):
    """AgentCore Gateway Management CLI for K8s Diagnostics.

    Create, delete, and manage AgentCore gateways with mcpServer targets
    for the NetOps K8s diagnostics application.
    """
    ctx.ensure_object(dict)


@cli.command()
@click.option("--name", required=True, help="Name for the gateway")
def create(name):
    """Create a new AgentCore gateway with EKS MCP Server target (idempotent)."""
    click.echo(f"Creating AgentCore gateway: {name}")
    click.echo(f"Region: {REGION}")

    try:
        existing_gateway = find_existing_gateway_by_name(name)

        if existing_gateway:
            click.echo(f"Gateway '{name}' already exists (ID: {existing_gateway['id']})")
            gateway_params = {
                "/a2a/app/k8s/agentcore/gateway_id": existing_gateway['id'],
                "/a2a/app/k8s/agentcore/gateway_name": name,
                "/a2a/app/k8s/agentcore/gateway_arn": existing_gateway['gateway_arn'],
                "/a2a/app/k8s/agentcore/gateway_url": existing_gateway['gateway_url'],
            }
            create_ssm_parameters(gateway_params)
            click.echo("SSM parameters updated with existing gateway details")
            return

        gateway = create_gateway(gateway_name=name)
        click.echo(f"Gateway created successfully with ID: {gateway['id']}")

    except Exception as e:
        if 'already exists' in str(e).lower() or 'ConflictException' in str(e):
            existing_gateway = find_existing_gateway_by_name(name)
            if existing_gateway:
                click.echo(f"Using existing gateway: {existing_gateway['id']}")
                return

        click.echo(f"Failed to create gateway: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--gateway-id", help="Gateway ID (reads from SSM if not provided)")
@click.option("--name", required=True, help="Target name")
@click.option("--description", required=True, help="Target description")
@click.option("--endpoint", required=True, help="HTTPS endpoint of the MCP server")
def add_target(gateway_id, name, description, endpoint):
    """Add a new mcpServer target to an existing gateway.

    Use this to register additional EKS-related MCP servers.
    """
    if not gateway_id:
        gateway_id = get_gateway_id_from_config()
        if not gateway_id:
            click.echo("No gateway ID provided and couldn't read from SSM", err=True)
            sys.exit(1)

    click.echo(f"Adding target '{name}' to gateway {gateway_id}")
    if add_mcp_server_target(gateway_id, name, description, endpoint):
        click.echo("Target added successfully")
    else:
        click.echo("Failed to add target", err=True)
        sys.exit(1)


@cli.command()
@click.option("--gateway-id", help="Gateway ID (reads from SSM if not provided)")
def list_targets(gateway_id):
    """List all targets for the K8s gateway."""
    if not gateway_id:
        gateway_id = get_gateway_id_from_config()
        if not gateway_id:
            click.echo("No gateway ID provided and couldn't read from SSM", err=True)
            sys.exit(1)

    click.echo(f"Listing targets for gateway: {gateway_id}")

    try:
        list_response = gateway_client.list_gateway_targets(
            gatewayIdentifier=gateway_id, maxResults=100
        )

        if not list_response["items"]:
            click.echo("No targets found")
            return

        click.echo(f"Found {len(list_response['items'])} targets:")
        click.echo()

        for item in list_response["items"]:
            click.echo(f"  Name: {item['name']}")
            click.echo(f"    ID: {item['targetId']}")
            click.echo(f"    Description: {item.get('description', 'N/A')}")
            click.echo(f"    Status: {item.get('status', 'N/A')}")
            click.echo()

    except Exception as e:
        click.echo(f"Failed to list targets: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--gateway-id", help="Gateway ID (reads from SSM if not provided)")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete(gateway_id, confirm):
    """Delete an AgentCore gateway and all its targets."""
    if not gateway_id:
        gateway_id = get_gateway_id_from_config()
        if not gateway_id:
            click.echo("No gateway ID provided and couldn't read from SSM", err=True)
            sys.exit(1)
        click.echo(f"Using gateway ID from SSM: {gateway_id}")

    if not confirm:
        if not click.confirm(f"Delete gateway {gateway_id}? This cannot be undone."):
            click.echo("Cancelled")
            sys.exit(0)

    if delete_gateway(gateway_id):
        gateway_params = [
            "/a2a/app/k8s/agentcore/gateway_id",
            "/a2a/app/k8s/agentcore/gateway_name",
            "/a2a/app/k8s/agentcore/gateway_arn",
            "/a2a/app/k8s/agentcore/gateway_url",
        ]
        delete_ssm_parameters(gateway_params)
        click.echo("Gateway and SSM parameters deleted successfully")
    else:
        click.echo("Failed to delete gateway", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
