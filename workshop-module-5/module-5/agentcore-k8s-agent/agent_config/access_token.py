from bedrock_agentcore.identity.auth import requires_access_token
import boto3
import os
import logging

# Setup logging for debugging
logger = logging.getLogger(__name__)

def get_cognito_provider_name():
    """Get Cognito provider name from SSM parameter"""
    try:
        ssm = boto3.client('ssm')
        response = ssm.get_parameter(Name='/a2a/app/k8s/agentcore/cognito_provider')
        provider_name = response['Parameter']['Value']
        logger.info(f"Got provider name from SSM: '{provider_name}'")
        return provider_name
    except Exception as e:
        logger.error(f"Failed to get provider name from SSM: {e}")
        raise ValueError(f"Cannot get Cognito provider name from SSM: {e}")

# Get the provider name at import time
provider_name = get_cognito_provider_name()
logger.info(f"Final provider name: '{provider_name}'")

@requires_access_token(
    provider_name=provider_name,
    scopes=[],  # Optional unless required
    auth_flow="M2M",
)
async def get_gateway_access_token(access_token: str):
    logger.info(f"get_gateway_access_token called successfully")
    logger.info(f"Access token received (length: {len(access_token) if access_token else 0})")
    return access_token
