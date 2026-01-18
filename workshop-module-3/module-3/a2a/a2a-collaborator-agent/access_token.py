from bedrock_agentcore.identity.auth import requires_access_token
import boto3
import os
import logging
import time

# Setup enhanced logging for debugging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def get_aws_region() -> str:
    """Get the current AWS region."""
    # Try to get from environment first
    region = os.environ.get('AWS_DEFAULT_REGION')
    if region:
        return region
    
    # Try to get from boto3 session
    try:
        session = boto3.Session()
        return session.region_name or 'us-east-1'
    except Exception:
        return 'us-east-1'

def get_cognito_provider_name():
    """Get Cognito provider name from SSM parameter for host agent"""
    try:
        ssm = boto3.client('ssm', region_name=get_aws_region())
        response = ssm.get_parameter(Name='/a2a/app/performance/agentcore/cognito_provider')
        provider_name = response['Parameter']['Value']
        logger.info(f"🔧 [HOST DEBUG] Got provider name from SSM: '{provider_name}'")
        return provider_name
    except Exception as e:
        logger.error(f"🔧 [HOST ERROR] Failed to get provider name from SSM: {e}")
        # For local testing, return a default provider name
        logger.warning("🔧 [HOST WARNING] Using default provider name for local testing")
        return "default-provider"

def is_local_testing():
    """Check if we're running in local testing mode"""
    return os.environ.get('BEDROCK_AGENTCORE_LOCAL_TEST', 'false').lower() == 'true'

# Get the provider name at import time
try:
    provider_name = get_cognito_provider_name()
    logger.info(f"🔧 [HOST DEBUG] Final provider name: '{provider_name}'")
except Exception as e:
    logger.warning(f"🔧 [HOST WARNING] Could not get provider name, using default: {e}")
    provider_name = "default-provider"

# Decorated version for AgentCore runtime - this is the main function used by the runtime
@requires_access_token(
    provider_name=provider_name,
    scopes=[],  # Optional unless required
    auth_flow="M2M",
)
async def get_gateway_access_token(access_token: str):
    """Get access token from AgentCore runtime context"""
    logger.info(f"🔧 [HOST DEBUG] get_gateway_access_token called successfully")
    logger.info(f"🔧 [HOST DEBUG] Access token received (length: {len(access_token) if access_token else 0})")
    return access_token

# Fallback version for when the decorator fails or for local testing
async def get_gateway_access_token_fallback():
    """Get access token fallback - handles local testing scenarios"""
    logger.info("🔧 [HOST DEBUG] Using fallback access token method")
    return await get_gateway_access_token_local()

# Alternative function for local testing that doesn't use the decorator
async def get_gateway_access_token_local():
    """Get access token for local testing without the requires_access_token decorator"""
    logger.info("🔧 [HOST DEBUG] Using local testing access token method")
    
    # Check if we're in local testing mode
    if is_local_testing():
        logger.info("🔧 [HOST DEBUG] Local testing mode enabled")
        dummy_token = "local-test-token-" + str(hash(os.getenv('USER', 'testuser')))
        logger.info(f"🔧 [HOST DEBUG] Generated local test token (length: {len(dummy_token)})")
        return dummy_token
    
    # Try to get token from Cognito for testing
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        # Get Cognito client
        cognito_client = boto3.client('cognito-idp', region_name=get_aws_region())
        
        # Try to get a token using client credentials flow
        # This would require proper Cognito app client configuration
        logger.info("🔧 [HOST DEBUG] Attempting to get token from Cognito")
        
        # For now, return a test token since we don't have full Cognito setup for local testing
        test_token = f"test-token-{int(time.time())}"
        logger.info(f"🔧 [HOST DEBUG] Generated test token for local testing (length: {len(test_token)})")
        return test_token
        
    except Exception as e:
        logger.error(f"🔧 [HOST ERROR] Failed to get token from Cognito: {e}")
        # Return a fallback token for local testing
        fallback_token = "fallback-local-token"
        logger.warning(f"🔧 [HOST WARNING] Using fallback token (length: {len(fallback_token)})")
        return fallback_token
