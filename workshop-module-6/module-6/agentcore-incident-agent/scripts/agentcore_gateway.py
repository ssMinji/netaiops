#!/usr/bin/python
"""
=============================================================================
AgentCore Gateway Management - Incident Analysis Agent (Module 6)
=============================================================================

Description:
    Creates and manages AgentCore gateways for the Incident Analysis Agent.
    Configures 3 MCP/Lambda targets: DatadogTools, OpenSearchTools,
    and ContainerInsightTools.

Usage:
    python agentcore_gateway.py create --name incident-analysis-gateway
    python agentcore_gateway.py delete [--gateway-id <id>] [--confirm]

SSM Prefix: /app/incident/agentcore/

Author: NetAIOps Team
Module: workshop-module-6
=============================================================================
"""
import os
import sys
import time
import json
import boto3
import click
from botocore.exceptions import ClientError

# Set AWS profile for workshop deployment
os.environ.setdefault("AWS_PROFILE", "netaiops-deploy")

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

# =============================================================================
# Inline Tool Schemas (extracted from Lambda TOOL_SCHEMAS)
# =============================================================================

DATADOG_TOOL_SCHEMAS = [
    {
        "name": "datadog-query-metrics",
        "description": "Query Datadog timeseries metrics (CPU, Memory, Latency, Error Rate).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Datadog metrics query (e.g., 'avg:system.cpu.user{service:web-app}')"
                },
                "from_ts": {
                    "type": "integer",
                    "description": "Start timestamp (Unix epoch seconds). Default: 1 hour ago"
                },
                "to_ts": {
                    "type": "integer",
                    "description": "End timestamp (Unix epoch seconds). Default: now"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "datadog-get-events",
        "description": "Get Datadog events and alert history.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags to filter events (e.g., 'service:web-app,env:prod')"
                },
                "priority": {
                    "type": "string",
                    "description": "Event priority filter: 'normal' or 'low'. Default: all",
                    "enum": ["normal", "low"]
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours back to search. Default: 24"
                }
            },
            "required": []
        }
    },
    {
        "name": "datadog-get-traces",
        "description": "Get APM traces for slow or error requests.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name to filter traces"
                },
                "operation": {
                    "type": "string",
                    "description": "Operation name filter (optional)"
                },
                "min_duration_ms": {
                    "type": "integer",
                    "description": "Minimum trace duration in milliseconds. Default: 1000"
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours back to search. Default: 1"
                },
                "status": {
                    "type": "string",
                    "description": "Trace status filter: 'error' or 'ok'",
                    "enum": ["error", "ok"]
                }
            },
            "required": ["service"]
        }
    },
    {
        "name": "datadog-get-monitors",
        "description": "Get Datadog monitor statuses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "monitor_tags": {
                    "type": "string",
                    "description": "Comma-separated tags to filter monitors"
                },
                "name_filter": {
                    "type": "string",
                    "description": "Filter monitors by name substring"
                }
            },
            "required": []
        }
    }
]

OPENSEARCH_TOOL_SCHEMAS = [
    {
        "name": "opensearch-search-logs",
        "description": "Search application logs by keyword or pattern.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "description": "OpenSearch index name or pattern (e.g., 'app-logs-*')"
                },
                "query": {
                    "type": "string",
                    "description": "Search query string (e.g., 'error AND timeout')"
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours back to search. Default: 1"
                },
                "size": {
                    "type": "integer",
                    "description": "Maximum number of results. Default: 50"
                }
            },
            "required": ["index", "query"]
        }
    },
    {
        "name": "opensearch-anomaly-detection",
        "description": "Detect anomalous log volume patterns over time.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "description": "OpenSearch index name or pattern"
                },
                "field": {
                    "type": "string",
                    "description": "Field to analyze for anomalies (e.g., 'level', 'status_code'). Default: 'level'"
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours back to analyze. Default: 6"
                },
                "interval": {
                    "type": "string",
                    "description": "Bucket interval (e.g., '5m', '15m', '1h'). Default: '5m'"
                }
            },
            "required": ["index"]
        }
    },
    {
        "name": "opensearch-get-error-summary",
        "description": "Get error log statistics grouped by type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "description": "OpenSearch index name or pattern"
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours back to search. Default: 24"
                },
                "group_by": {
                    "type": "string",
                    "description": "Field to group errors by. Default: 'error_type'"
                }
            },
            "required": ["index"]
        }
    }
]

CONTAINER_INSIGHT_TOOL_SCHEMAS = [
    {
        "name": "container-insight-pod-metrics",
        "description": "Get EKS pod CPU, Memory, Network metrics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_name": {"type": "string", "description": "EKS cluster name"},
                "namespace": {"type": "string", "description": "Kubernetes namespace. Default: all namespaces"},
                "pod_name": {"type": "string", "description": "Specific pod name filter (optional)"},
                "minutes": {"type": "integer", "description": "How many minutes back. Default: 60"},
                "period": {"type": "integer", "description": "Metric period in seconds. Default: 300"}
            },
            "required": ["cluster_name"]
        }
    },
    {
        "name": "container-insight-node-metrics",
        "description": "Get EKS node resource utilization.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_name": {"type": "string", "description": "EKS cluster name"},
                "node_name": {"type": "string", "description": "Specific node name (optional)"},
                "minutes": {"type": "integer", "description": "How many minutes back. Default: 60"},
                "period": {"type": "integer", "description": "Metric period in seconds. Default: 300"}
            },
            "required": ["cluster_name"]
        }
    },
    {
        "name": "container-insight-cluster-overview",
        "description": "Get cluster-wide health overview including node/pod counts and resource usage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_name": {"type": "string", "description": "EKS cluster name"},
                "minutes": {"type": "integer", "description": "How many minutes back. Default: 30"},
                "period": {"type": "integer", "description": "Metric period in seconds. Default: 300"}
            },
            "required": ["cluster_name"]
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
                    raise e  # Re-raise if it's the last attempt

                delay = initial_delay * (backoff_multiplier ** attempt)
                click.echo(f"  Rate limit hit, waiting {delay}s before retry (attempt {attempt + 1}/{max_retries})...")
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


# =============================================================================
# Gateway Management
# =============================================================================

def create_gateway(gateway_name: str) -> dict:
    """Create an AgentCore gateway with Datadog, OpenSearch, and ContainerInsight tools."""
    try:
        auth_config = {
            "customJWTAuthorizer": {
                "allowedClients": [
                    get_ssm_parameter(
                        "/app/incident/agentcore/machine_client_id"
                    )
                ],
                "discoveryUrl": get_ssm_parameter(
                    "/app/incident/agentcore/cognito_discovery_url"
                ),
            }
        }

        execution_role_arn = get_ssm_parameter(
            "/app/incident/agentcore/gateway_iam_role"
        )

        click.echo(f"Creating gateway in region {REGION} with name: {gateway_name}")
        click.echo(f"Execution role ARN: {execution_role_arn}")

        create_response = gateway_client.create_gateway(
            name=gateway_name,
            roleArn=execution_role_arn,
            protocolType="MCP",
            authorizerType="CUSTOM_JWT",
            authorizerConfiguration=auth_config,
            description="AgentCore Incident Analysis Gateway",
        )

        click.echo(f"Gateway created: {create_response['gatewayId']}")

        credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
        gateway_id = create_response["gatewayId"]

        # Wait for gateway to be ready before adding targets
        click.echo("Waiting for gateway to be ready for target creation...")
        max_wait = 300  # 5 minutes
        wait_interval = 10  # 10 seconds
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                response = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
                status = response.get('status', 'UNKNOWN')

                if status in ['ACTIVE', 'READY']:
                    click.echo("Gateway is ready for target creation")
                    break
                elif status in ['FAILED', 'DELETING', 'DELETED']:
                    click.echo(f"Gateway is in {status} status - cannot add targets")
                    return {
                        "id": gateway_id,
                        "name": gateway_name,
                        "gateway_url": create_response["gatewayUrl"],
                        "gateway_arn": create_response["gatewayArn"],
                    }
                else:
                    click.echo(f"   Gateway status: {status} - waiting...")
                    time.sleep(wait_interval)

            except ClientError as e:
                click.echo(f"   Error checking gateway status: {e}")
                time.sleep(wait_interval)
        else:
            click.echo("WARNING: Timeout waiting for gateway to be ready - proceeding anyway")

        # Target 1: Datadog Tools
        try:
            datadog_lambda_arn = get_ssm_parameter("/app/incident/agentcore/datadog_lambda_arn")

            datadog_config = {
                "mcp": {
                    "lambda": {
                        "lambdaArn": datadog_lambda_arn,
                        "toolSchema": {"inlinePayload": DATADOG_TOOL_SCHEMAS},
                    }
                }
            }

            datadog_target_response = create_gateway_target_with_retry(
                gateway_id=gateway_id,
                name="DatadogTools",
                description="Datadog metrics, events, traces, and monitor tools",
                target_config=datadog_config,
                credential_config=credential_config,
            )

            click.echo(f"Datadog target created: {datadog_target_response['targetId']}")

            # Prevent API throttling when creating multiple targets sequentially
            click.echo("Waiting to prevent API throttling...")
            throttling_delay = 2
            # INTENTIONAL DELAY: AWS Bedrock AgentCore API rate limiting between target creations
            time.sleep(throttling_delay)  # nosemgrep: arbitrary-sleep

        except Exception as datadog_error:
            click.echo(f"WARNING: Datadog tool not available: {datadog_error}")
            click.echo("   Deploy lambda-datadog first, then recreate gateway")

        # Target 2: OpenSearch Tools
        try:
            opensearch_lambda_arn = get_ssm_parameter("/app/incident/agentcore/opensearch_lambda_arn")

            opensearch_config = {
                "mcp": {
                    "lambda": {
                        "lambdaArn": opensearch_lambda_arn,
                        "toolSchema": {"inlinePayload": OPENSEARCH_TOOL_SCHEMAS},
                    }
                }
            }

            opensearch_target_response = create_gateway_target_with_retry(
                gateway_id=gateway_id,
                name="OpenSearchTools",
                description="OpenSearch log search, anomaly detection, and error summary tools",
                target_config=opensearch_config,
                credential_config=credential_config,
            )

            click.echo(f"OpenSearch target created: {opensearch_target_response['targetId']}")

            # Prevent API throttling when creating multiple targets sequentially
            click.echo("Waiting to prevent API throttling...")
            throttling_delay = 2
            # INTENTIONAL DELAY: AWS Bedrock AgentCore API rate limiting between target creations
            time.sleep(throttling_delay)  # nosemgrep: arbitrary-sleep

        except Exception as opensearch_error:
            click.echo(f"WARNING: OpenSearch tool not available: {opensearch_error}")
            click.echo("   Deploy lambda-opensearch first, then recreate gateway")

        # Target 3: Container Insight Tools
        try:
            container_insight_lambda_arn = get_ssm_parameter("/app/incident/agentcore/container_insight_lambda_arn")

            container_insight_config = {
                "mcp": {
                    "lambda": {
                        "lambdaArn": container_insight_lambda_arn,
                        "toolSchema": {"inlinePayload": CONTAINER_INSIGHT_TOOL_SCHEMAS},
                    }
                }
            }

            container_insight_target_response = create_gateway_target_with_retry(
                gateway_id=gateway_id,
                name="ContainerInsightTools",
                description="EKS Container Insights pod, node, and cluster metrics tools",
                target_config=container_insight_config,
                credential_config=credential_config,
            )

            click.echo(f"ContainerInsight target created: {container_insight_target_response['targetId']}")

        except Exception as container_insight_error:
            click.echo(f"WARNING: ContainerInsight tool not available: {container_insight_error}")
            click.echo("   Deploy lambda-container-insight first, then recreate gateway")

        gateway = {
            "id": gateway_id,
            "name": gateway_name,
            "gateway_url": create_response["gatewayUrl"],
            "gateway_arn": create_response["gatewayArn"],
        }

        # Save gateway details to SSM parameters
        gateway_params = {
            "/app/incident/agentcore/gateway_id": gateway_id,
            "/app/incident/agentcore/gateway_name": gateway_name,
            "/app/incident/agentcore/gateway_arn": create_response["gatewayArn"],
            "/app/incident/agentcore/gateway_url": create_response["gatewayUrl"],
        }

        create_ssm_parameters(gateway_params)
        click.echo("Gateway configuration saved to SSM parameters")

        return gateway

    except Exception as e:
        click.echo(f"Error creating gateway: {str(e)}", err=True)
        sys.exit(1)


def delete_gateway(gateway_id: str) -> bool:
    """Delete a gateway and all its targets."""
    try:
        click.echo(f"Deleting all targets for gateway: {gateway_id}")

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
            click.echo(f"   Target {target_id} deleted")

        # Delete the gateway
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
        return get_ssm_parameter("/app/incident/agentcore/gateway_id")
    except Exception as e:
        click.echo(f"Error reading gateway ID from SSM: {str(e)}", err=True)
        return None


# =============================================================================
# CLI Commands
# =============================================================================

@click.group()
@click.pass_context
def cli(ctx):
    """Incident Analysis Agent - AgentCore Gateway Management CLI.

    Create and delete AgentCore gateways for the incident analysis application.
    Uses SSM prefix: /app/incident/agentcore/
    """
    ctx.ensure_object(dict)


@cli.command()
@click.option("--name", required=True, help="Name for the gateway")
def create(name):
    """Create a new AgentCore gateway with Datadog, OpenSearch, and ContainerInsight tools."""
    click.echo(f"Creating AgentCore gateway: {name}")
    click.echo(f"Region: {REGION}")

    try:
        gateway = create_gateway(gateway_name=name)
        click.echo(f"Gateway created successfully with ID: {gateway['id']}")

    except Exception as e:
        click.echo(f"Failed to create gateway: {str(e)}", err=True)
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
                "No gateway ID provided and couldn't read from SSM parameters",
                err=True,
            )
            sys.exit(1)
        click.echo(f"Using gateway ID from SSM: {gateway_id}")

    # Confirmation prompt
    if not confirm:
        if not click.confirm(
            f"Are you sure you want to delete gateway {gateway_id}? This action cannot be undone."
        ):
            click.echo("Operation cancelled")
            sys.exit(0)

    click.echo(f"Deleting gateway: {gateway_id}")

    if delete_gateway(gateway_id):
        click.echo("Gateway deleted successfully")

        # Clean up SSM parameters
        gateway_params = [
            "/app/incident/agentcore/gateway_id",
            "/app/incident/agentcore/gateway_name",
            "/app/incident/agentcore/gateway_arn",
            "/app/incident/agentcore/gateway_url",
        ]

        delete_ssm_parameters(gateway_params)
        click.echo("Removed gateway SSM parameters")
        click.echo("Gateway and configuration deleted successfully")
    else:
        click.echo("Failed to delete gateway", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
