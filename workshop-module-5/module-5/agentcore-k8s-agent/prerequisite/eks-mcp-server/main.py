"""
EKS MCP Server - AgentCore Runtime Wrapper

Wraps the official AWS Labs eks-mcp-server (awslabs.eks-mcp-server)
and runs it with Streamable HTTP transport so it can be registered
as an MCP Gateway target via the mcpServer endpoint type.
"""

import argparse
import logging
import os

import boto3
from awslabs.eks_mcp_server.server import create_server

# Import all handler classes to register tools with the server
from awslabs.eks_mcp_server.cloudwatch_handler import CloudWatchHandler
from awslabs.eks_mcp_server.cloudwatch_metrics_guidance_handler import CloudWatchMetricsHandler
from awslabs.eks_mcp_server.eks_kb_handler import EKSKnowledgeBaseHandler
from awslabs.eks_mcp_server.eks_stack_handler import EksStackHandler
from awslabs.eks_mcp_server.iam_handler import IAMHandler
from awslabs.eks_mcp_server.insights_handler import InsightsHandler
from awslabs.eks_mcp_server.k8s_handler import K8sHandler
from awslabs.eks_mcp_server.vpc_config_handler import VpcConfigHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="EKS MCP Server for AgentCore")
    parser.add_argument(
        "--allow-write",
        action="store_true",
        default=os.environ.get("EKS_MCP_ALLOW_WRITE", "false").lower() == "true",
        help="Enable mutating operations (create, update, delete)",
    )
    parser.add_argument(
        "--allow-sensitive-data-access",
        action="store_true",
        default=os.environ.get("EKS_MCP_ALLOW_SENSITIVE", "true").lower() == "true",
        help="Enable access to logs, events, and secrets",
    )
    args = parser.parse_args()

    logger.info(
        f"Starting EKS MCP Server (write={args.allow_write}, "
        f"sensitive={args.allow_sensitive_data_access})"
    )

    # Create server following official AgentCore MCP pattern
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        'awslabs.eks-mcp-server',
        host="127.0.0.1",
        stateless_http=True,
    )

    # Initialize all handlers (same as official server main())
    CloudWatchHandler(mcp, args.allow_sensitive_data_access)
    EKSKnowledgeBaseHandler(mcp)
    EksStackHandler(mcp, args.allow_write)
    K8sHandler(mcp, args.allow_write, args.allow_sensitive_data_access)
    IAMHandler(mcp, args.allow_write)
    CloudWatchMetricsHandler(mcp)
    VpcConfigHandler(mcp, args.allow_sensitive_data_access)
    InsightsHandler(mcp, args.allow_sensitive_data_access)

    # Register custom region-switching tool
    @mcp.tool()
    def set_aws_region(region: str) -> str:
        """Set the AWS region for subsequent EKS tool calls.

        Call this BEFORE using any other EKS tools when the user specifies
        or implies a specific AWS region. This changes the region used by
        all subsequent tool calls in this session.

        Common regions:
        - us-east-1 (Virginia)
        - us-west-2 (Oregon)
        - ap-northeast-2 (Seoul)
        - eu-west-1 (Ireland)
        - ap-northeast-1 (Tokyo)

        Args:
            region: AWS region code (e.g. "us-east-1")
        """
        os.environ['AWS_REGION'] = region
        os.environ['AWS_DEFAULT_REGION'] = region
        boto3.setup_default_session(region_name=region)

        # Clear cached boto3 clients so new ones are created with the updated region
        from awslabs.eks_mcp_server.aws_helper import AwsHelper
        from awslabs.eks_mcp_server.k8s_client_cache import K8sClientCache
        AwsHelper._client_cache.clear()
        k8s_cache = K8sClientCache()
        k8s_cache._client_cache.clear()
        k8s_cache._sts_event_handlers_registered = False

        logger.info(f"AWS region switched to {region}, all client caches cleared")
        return f"AWS region set to {region}. All subsequent EKS tools will query this region."

    @mcp.tool()
    def list_eks_clusters() -> str:
        """List all EKS clusters in the current AWS region.

        Call set_aws_region first to set the target region, then use this tool
        to discover available clusters. Returns cluster names as a list.
        """
        from awslabs.eks_mcp_server.aws_helper import AwsHelper
        eks_client = AwsHelper.create_boto3_client('eks')
        clusters = []
        paginator = eks_client.get_paginator('list_clusters')
        for page in paginator.paginate():
            clusters.extend(page.get('clusters', []))
        if not clusters:
            region = os.environ.get('AWS_REGION', 'unknown')
            return f"No EKS clusters found in region {region}."
        return f"EKS clusters in region {os.environ.get('AWS_REGION', 'unknown')}:\n" + "\n".join(f"- {c}" for c in clusters)

    # Run with Streamable HTTP transport for Gateway integration
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
