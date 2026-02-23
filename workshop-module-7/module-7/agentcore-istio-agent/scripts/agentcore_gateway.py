#!/usr/bin/python
"""
=============================================================================
AgentCore Gateway Management - Istio Mesh Diagnostics Agent (Module 7)
=============================================================================

Description:
    Creates and manages AgentCore gateways for the Istio Mesh Diagnostics Agent.
    Configures a hybrid gateway with two target types:
      - Target 1: EksMcpServer (mcpServer type) - EKS MCP Server from Module 5
      - Target 2: IstioPrometheusTools (Lambda type) - Istio Prometheus metrics

Architecture:
    Istio Agent -> MCP Gateway -> EksMcpServer (mcpServer) + IstioPrometheusTools (Lambda)

Usage:
    python agentcore_gateway.py create --name istio-mesh-gateway
    python agentcore_gateway.py list-targets
    python agentcore_gateway.py delete [--gateway-id <id>] [--confirm]

SSM Prefix: /app/istio/agentcore/

Author: NetAIOps Team
Module: workshop-module-7
=============================================================================
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

# =============================================================================
# Inline Tool Schemas for Istio Prometheus Lambda
# (Extracted from lambda-istio-prometheus TOOL_SCHEMAS)
# =============================================================================

ISTIO_PROMETHEUS_TOOL_SCHEMAS = [
    {
        "name": "istio-query-workload-metrics",
        "description": "Query Istio RED (Rate, Error, Duration) metrics per workload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace filter (optional, default: all)"
                },
                "workload": {
                    "type": "string",
                    "description": "Specific workload name filter (optional)"
                },
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes back to query. Default: 15"
                },
                "step": {
                    "type": "string",
                    "description": "Query step/resolution (e.g., '1m', '5m'). Default: '1m'"
                }
            },
            "required": []
        }
    },
    {
        "name": "istio-query-service-topology",
        "description": "Query Istio service-to-service traffic topology showing request rates and error codes between services.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace filter (optional)"
                },
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes back to query. Default: 15"
                }
            },
            "required": []
        }
    },
    {
        "name": "istio-query-tcp-metrics",
        "description": "Query Istio TCP connection metrics (connections opened/closed, bytes sent/received).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace filter (optional)"
                },
                "workload": {
                    "type": "string",
                    "description": "Specific workload name filter (optional)"
                },
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes back to query. Default: 15"
                }
            },
            "required": []
        }
    },
    {
        "name": "istio-query-control-plane-health",
        "description": "Query Istio control plane (istiod) health metrics including xDS push latency, errors, and config conflicts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes back to query. Default: 30"
                }
            },
            "required": []
        }
    },
    {
        "name": "istio-query-proxy-resource-usage",
        "description": "Query Envoy sidecar proxy resource usage (CPU, memory) across workloads.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace filter (optional)"
                },
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes back to query. Default: 15"
                }
            },
            "required": []
        }
    }
]


# =============================================================================
# Retry Logic
# =============================================================================

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
                click.echo(f"  Rate limit hit, waiting {delay}s before retry (attempt {attempt + 1}/{max_retries})...")
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


# =============================================================================
# OAuth2 Credential Provider (for mcpServer target → EKS MCP Server)
# =============================================================================

def get_runtime_endpoint_url(runtime_arn: str) -> str:
    """Construct the MCP Runtime endpoint URL from the ARN.

    Follows the official agentcore-mcp-toolkit pattern:
    https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{url_encoded_arn}/invocations?qualifier=DEFAULT
    """
    encoded_arn = urllib.parse.quote(runtime_arn, safe='')
    return f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"


def create_oauth2_credential_provider(provider_name: str) -> str:
    """Create an OAuth2 credential provider for Gateway-to-Runtime auth.

    Reads the Runtime Cognito details from Module 5 SSM parameters and creates
    an AgentCore OAuth2 credential provider.

    Returns the provider ARN.
    """
    client_id = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_client_id")
    client_secret = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_client_secret")
    token_url = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_token_url")
    discovery_url = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_discovery_url")
    scope = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_auth_scope")

    if not all([client_id, client_secret, token_url, scope]):
        raise ValueError(
            "Missing Runtime Cognito SSM parameters from Module 5. "
            "Deploy Module 5 CloudFormation stack first."
        )

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

    # Build OAuth2 provider config with oauthDiscovery (required by current API)
    oauth2_config = {
        "customOauth2ProviderConfig": {
            "clientId": client_id,
            "clientSecret": client_secret,
        }
    }

    # Use discoveryUrl if available, otherwise fall back to authorizationServerMetadata
    if discovery_url:
        oauth2_config["customOauth2ProviderConfig"]["oauthDiscovery"] = {
            "discoveryUrl": discovery_url,
        }
    else:
        # Derive metadata from token URL domain
        token_domain = token_url.rsplit("/oauth2/token", 1)[0]
        oauth2_config["customOauth2ProviderConfig"]["oauthDiscovery"] = {
            "authorizationServerMetadata": {
                "issuer": token_domain,
                "authorizationEndpoint": f"{token_domain}/oauth2/authorize",
                "tokenEndpoint": token_url,
            }
        }

    response = gateway_client.create_oauth2_credential_provider(
        name=provider_name,
        credentialProviderVendor="CustomOAuth",
        oauth2ProviderConfigInput=oauth2_config,
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


# =============================================================================
# Gateway Management
# =============================================================================

def create_gateway(gateway_name: str) -> dict:
    """Create an AgentCore gateway with hybrid targets:
    - EksMcpServer (mcpServer type, OAuth2 credential)
    - IstioPrometheusTools (Lambda type, GATEWAY_IAM_ROLE credential)
    """
    auth_config = {
        "customJWTAuthorizer": {
            "allowedClients": [
                get_ssm_parameter("/app/istio/agentcore/machine_client_id")
            ],
            "discoveryUrl": get_ssm_parameter(
                "/app/istio/agentcore/cognito_discovery_url"
            ),
        }
    }

    execution_role_arn = get_ssm_parameter(
        "/app/istio/agentcore/gateway_iam_role"
    )

    click.echo(f"Creating gateway in region {REGION} with name: {gateway_name}")
    click.echo(f"Execution role ARN: {execution_role_arn}")

    create_response = gateway_client.create_gateway(
        name=gateway_name,
        roleArn=execution_role_arn,
        protocolType="MCP",
        authorizerType="CUSTOM_JWT",
        authorizerConfiguration=auth_config,
        description="AgentCore Istio Mesh Diagnostics Gateway",
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
            "/app/istio/agentcore/gateway_id": gateway_id,
            "/app/istio/agentcore/gateway_name": gateway_name,
            "/app/istio/agentcore/gateway_arn": create_response["gatewayArn"],
            "/app/istio/agentcore/gateway_url": create_response["gatewayUrl"],
        }
        create_ssm_parameters(gateway_params)
        return gateway

    # ==================================================================
    # Target 1: EKS MCP Server (mcpServer type, OAuth2 credential)
    # Reuses Module 5's EKS MCP Server Runtime endpoint
    # ==================================================================
    oauth_provider_name = "istio-eks-mcp-server-oauth"
    scope = get_ssm_parameter("/a2a/app/k8s/agentcore/eks_mcp_auth_scope")

    try:
        oauth_provider_arn = create_oauth2_credential_provider(oauth_provider_name)
    except Exception as e:
        click.echo(f"Failed to create OAuth2 credential provider: {e}")
        click.echo("Ensure Module 5 CloudFormation stack is deployed with Runtime Cognito resources.")
        oauth_provider_arn = None

    try:
        eks_mcp_arn = get_ssm_parameter(
            "/a2a/app/k8s/agentcore/eks_mcp_server_arn"
        )
        if not eks_mcp_arn:
            raise ValueError("EKS MCP Server ARN not found in SSM. Deploy Module 5 eks-mcp-server first.")

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

        oauth_credential_config = [{
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
            description="AWS Labs EKS MCP Server - K8s resources, Istio CRDs, pod logs, events",
            target_config=eks_mcp_target_config,
            credential_config=oauth_credential_config,
        )

        click.echo(f"EKS MCP Server target created: {eks_target_response['targetId']}")

        # Prevent API throttling between target creations
        click.echo("Waiting to prevent API throttling...")
        throttling_delay = 2
        # INTENTIONAL DELAY: AWS Bedrock AgentCore API rate limiting between target creations
        time.sleep(throttling_delay)  # nosemgrep: arbitrary-sleep

    except Exception as e:
        click.echo(f"EKS MCP Server target not available: {e}")
        click.echo("Deploy Module 5 eks-mcp-server first:")
        click.echo("   cd ../../workshop-module-5/module-5/agentcore-k8s-agent/prerequisite/eks-mcp-server")
        click.echo("   ./deploy-eks-mcp-server.sh")

    # ==================================================================
    # Target 2: Istio Prometheus Tools (Lambda type, GATEWAY_IAM_ROLE)
    # ==================================================================
    try:
        prometheus_lambda_arn = get_ssm_parameter(
            "/app/istio/agentcore/prometheus_lambda_arn"
        )
        if not prometheus_lambda_arn:
            raise ValueError("Prometheus Lambda ARN not found in SSM. Run deploy-istio-lambdas.sh first.")

        lambda_credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]

        prometheus_config = {
            "mcp": {
                "lambda": {
                    "lambdaArn": prometheus_lambda_arn,
                    "toolSchema": {"inlinePayload": ISTIO_PROMETHEUS_TOOL_SCHEMAS},
                }
            }
        }

        prometheus_target_response = create_gateway_target_with_retry(
            gateway_id=gateway_id,
            name="IstioPrometheusTools",
            description="Istio Prometheus metrics - RED, topology, TCP, control plane, proxy resources",
            target_config=prometheus_config,
            credential_config=lambda_credential_config,
        )

        click.echo(f"Istio Prometheus target created: {prometheus_target_response['targetId']}")

    except Exception as e:
        click.echo(f"WARNING: Istio Prometheus tool not available: {e}")
        click.echo("   Deploy lambda-istio-prometheus first:")
        click.echo("   cd prerequisite && ./deploy-istio-lambdas.sh")

    gateway = {
        "id": gateway_id,
        "name": gateway_name,
        "gateway_url": create_response["gatewayUrl"],
        "gateway_arn": create_response["gatewayArn"],
    }

    # Save gateway details to SSM parameters
    gateway_params = {
        "/app/istio/agentcore/gateway_id": gateway_id,
        "/app/istio/agentcore/gateway_name": gateway_name,
        "/app/istio/agentcore/gateway_arn": create_response["gatewayArn"],
        "/app/istio/agentcore/gateway_url": create_response["gatewayUrl"],
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
        return get_ssm_parameter("/app/istio/agentcore/gateway_id")
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


# =============================================================================
# CLI Commands
# =============================================================================

@click.group()
@click.pass_context
def cli(ctx):
    """Istio Mesh Diagnostics Agent - AgentCore Gateway Management CLI.

    Create, delete, and manage AgentCore gateways with hybrid targets
    (mcpServer + Lambda) for the Istio mesh diagnostics application.

    Uses SSM prefix: /app/istio/agentcore/
    """
    ctx.ensure_object(dict)


@cli.command()
@click.option("--name", required=True, help="Name for the gateway")
def create(name):
    """Create a new AgentCore gateway with EKS MCP Server + Istio Prometheus targets (idempotent)."""
    click.echo(f"Creating AgentCore gateway: {name}")
    click.echo(f"Region: {REGION}")

    try:
        existing_gateway = find_existing_gateway_by_name(name)

        if existing_gateway:
            click.echo(f"Gateway '{name}' already exists (ID: {existing_gateway['id']})")
            gateway_params = {
                "/app/istio/agentcore/gateway_id": existing_gateway['id'],
                "/app/istio/agentcore/gateway_name": name,
                "/app/istio/agentcore/gateway_arn": existing_gateway['gateway_arn'],
                "/app/istio/agentcore/gateway_url": existing_gateway['gateway_url'],
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
def list_targets(gateway_id):
    """List all targets for the Istio mesh gateway."""
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
            "/app/istio/agentcore/gateway_id",
            "/app/istio/agentcore/gateway_name",
            "/app/istio/agentcore/gateway_arn",
            "/app/istio/agentcore/gateway_url",
        ]
        delete_ssm_parameters(gateway_params)
        click.echo("Gateway and SSM parameters deleted successfully")
    else:
        click.echo("Failed to delete gateway", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
