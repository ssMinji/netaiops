from bedrock_agentcore.identity.auth import requires_access_token
import boto3
import logging

logger = logging.getLogger(__name__)

def get_cognito_provider_name():
    try:
        ssm = boto3.client('ssm')
        response = ssm.get_parameter(Name='/app/incident/agentcore/cognito_provider')
        provider_name = response['Parameter']['Value']
        return provider_name
    except Exception as e:
        raise ValueError(f"Cannot get Cognito provider name from SSM: {e}")

provider_name = get_cognito_provider_name()

@requires_access_token(provider_name=provider_name, scopes=[], auth_flow="M2M")
async def get_gateway_access_token(access_token: str):
    return access_token
