#!/usr/bin/env python3

"""
Setup Cognito OAuth2 Provider for Performance Agent using CloudFormation
Uses cognito.yaml as the single source of truth for CloudFormation template
"""

import boto3
import json
import time
import sys
import os
from pathlib import Path
from botocore.exceptions import ClientError

# Configuration - make region configurable
DEFAULT_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
STACK_NAME = "a2a-performance-agentcore-cognito"

# Get paths relative to script
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
cognito_template_path = os.path.join(project_root, "prerequisite", "cognito.yaml")

def deploy_cognito_cloudformation(region=None):
    """Deploy Cognito infrastructure using CloudFormation from cognito.yaml"""
    print("🚀 Deploying Cognito infrastructure with CloudFormation...")
    
    if region is None:
        region = DEFAULT_REGION
    
    print(f"📍 Using region: {region}")
    print(f"📁 Template path: {cognito_template_path}")
    
    # Verify template file exists
    if not os.path.exists(cognito_template_path):
        raise FileNotFoundError(f"❌ Cognito template not found: {cognito_template_path}")
    
    cloudformation = boto3.client('cloudformation', region_name=region)
    
    try:
        # Read the YAML template
        with open(cognito_template_path, 'r') as f:
            template_body = f.read()
        
        print(f"✅ Successfully loaded template from {cognito_template_path}")
        
        # Check if stack exists
        try:
            cloudformation.describe_stacks(StackName=STACK_NAME)
            stack_exists = True
            print(f"🔄 Stack '{STACK_NAME}' exists, updating...")
        except cloudformation.exceptions.ClientError:
            stack_exists = False
            print(f"🆕 Creating new stack '{STACK_NAME}'...")
        
        # Deploy or update stack
        if stack_exists:
            cloudformation.update_stack(
                StackName=STACK_NAME,
                TemplateBody=template_body,
                Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
            )
            print("⏳ Waiting for stack update to complete...")
            cloudformation.get_waiter('stack_update_complete').wait(StackName=STACK_NAME)
        else:
            cloudformation.create_stack(
                StackName=STACK_NAME,
                TemplateBody=template_body,
                Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
            )
            print("⏳ Waiting for stack creation to complete...")
            cloudformation.get_waiter('stack_create_complete').wait(StackName=STACK_NAME)
        
        print("✅ CloudFormation stack deployed successfully!")
        
        # Get stack outputs
        response = cloudformation.describe_stacks(StackName=STACK_NAME)
        outputs = response['Stacks'][0].get('Outputs', [])
        
        print("📋 Stack Outputs:")
        output_dict = {}
        for output in outputs:
            print(f"   {output['OutputKey']}: {output['OutputValue']}")
            output_dict[output['OutputKey']] = output['OutputValue']
        
        return output_dict
        
    except Exception as e:
        print(f"❌ CloudFormation deployment failed: {e}")
        raise

def verify_ssm_parameters(region=None):
    """Verify all required SSM parameters exist"""
    print("🔍 Verifying SSM parameters...")
    
    if region is None:
        region = DEFAULT_REGION
    
    ssm = boto3.client('ssm', region_name=region)
    required_parameters = [
        "/a2a/app/performance/agentcore/machine_client_id",
        "/a2a/app/performance/agentcore/web_client_id",
        "/a2a/app/performance/agentcore/cognito_provider",
        "/a2a/app/performance/agentcore/cognito_domain",
        "/a2a/app/performance/agentcore/cognito_token_url",
        "/a2a/app/performance/agentcore/cognito_discovery_url",
        "/a2a/app/performance/agentcore/cognito_auth_url",
        "/a2a/app/performance/agentcore/cognito_auth_scope",
        "/a2a/app/performance/agentcore/userpool_id",
        "/a2a/app/performance/agentcore/gateway_iam_role"
    ]
    
    all_exist = True
    for param in required_parameters:
        try:
            response = ssm.get_parameter(Name=param)
            value = response['Parameter']['Value']
            print(f"  ✅ {param} = {value}")
        except ssm.exceptions.ParameterNotFound:
            print(f"  ❌ {param} = NOT FOUND")
            all_exist = False
    
    return all_exist

def create_test_user(region=None):
    """Create test user in Cognito"""
    print("👤 Creating test user...")
    
    if region is None:
        region = DEFAULT_REGION
    
    try:
        ssm = boto3.client('ssm', region_name=region)
        user_pool_id = ssm.get_parameter(Name="/a2a/app/performance/agentcore/userpool_id")['Parameter']['Value']
        
        # Get passwords from environment variables or use defaults (should be overridden in production)
        temp_password = os.environ.get('COGNITO_TEMP_PASSWORD', 'TempPassword123!')
        final_password = os.environ.get('COGNITO_TEST_PASSWORD', 'TestPassword123!')
        
        cognito = boto3.client('cognito-idp', region_name=region)
        
        try:
            cognito.admin_get_user(UserPoolId=user_pool_id, Username="testuser")
            print("  ℹ️  Test user 'testuser' already exists")
        except cognito.exceptions.UserNotFoundException:
            print("  🆕 Creating test user 'testuser'...")
            cognito.admin_create_user(
                UserPoolId=user_pool_id,
                Username="testuser",
                UserAttributes=[
                    {
                        'Name': 'email',
                        'Value': 'test@example.com'
                    },
                    {
                        'Name': 'email_verified',
                        'Value': 'true'
                    }
                ],
                TemporaryPassword=temp_password,
                MessageAction="SUPPRESS"
            )
            
            # Set permanent password
            cognito.admin_set_user_password(
                UserPoolId=user_pool_id,
                Username="testuser",
                Password=final_password,
                Permanent=True
            )
            
            print(f"  ✅ Test user created with password from environment variable")
            
    except Exception as e:
        print(f"❌ Error creating test user: {e}")

def fix_cognito_provider_ssm_parameter(region=None):
    """Dynamically discover actual resource server and fix SSM parameter"""
    print("🔧 Fixing Cognito provider SSM parameter...")
    
    if region is None:
        region = DEFAULT_REGION
    
    try:
        ssm = boto3.client('ssm', region_name=region)
        cognito = boto3.client('cognito-idp', region_name=region)
        
        # Get user pool ID and web client ID from SSM
        print("📋 Getting existing SSM parameters...")
        user_pool_id = ssm.get_parameter(Name="/a2a/app/performance/agentcore/userpool_id")['Parameter']['Value']
        web_client_id = ssm.get_parameter(Name="/a2a/app/performance/agentcore/web_client_id")['Parameter']['Value']
        
        print(f"   User Pool ID: {user_pool_id}")
        print(f"   Web Client ID: {web_client_id}")
        
        # Get OAuth scopes from the web client to find the actual resource server
        print("🔍 Discovering actual resource server from OAuth scopes...")
        client_response = cognito.describe_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=web_client_id
        )
        
        oauth_scopes = client_response['UserPoolClient'].get('AllowedOAuthScopes', [])
        print(f"   OAuth Scopes: {oauth_scopes}")
        
        # Find resource server identifier from scopes
        resource_server_identifier = None
        for scope in oauth_scopes:
            if '/invoke' in scope and scope != 'openid' and scope != 'email' and scope != 'profile':
                resource_server_identifier = scope.replace('/invoke', '')
                break
        
        if not resource_server_identifier:
            # Fallback: Get resource servers directly
            print("🔍 Fallback: Listing resource servers directly...")
            response = cognito.list_resource_servers(
                UserPoolId=user_pool_id,
                MaxResults=50
            )
            
            resource_servers = response.get('ResourceServers', [])
            print(f"   Found {len(resource_servers)} resource servers")
            
            for server in resource_servers:
                print(f"      Server ID: {server['Identifier']}")
                scopes = server.get('Scopes', [])
                for scope in scopes:
                    if scope.get('ScopeName') == 'invoke':
                        resource_server_identifier = server['Identifier']
                        break
                if resource_server_identifier:
                    break
        
        if not resource_server_identifier:
            print("❌ Could not find resource server with 'invoke' scope")
            return False
            
        print(f"✅ Found actual resource server identifier: {resource_server_identifier}")
        
        # Get current SSM parameter value
        current_value = ssm.get_parameter(Name="/a2a/app/performance/agentcore/cognito_provider")['Parameter']['Value']
        print(f"📋 Current SSM parameter value: {current_value}")
        
        if current_value == resource_server_identifier:
            print("✅ SSM parameter is already correct!")
            return True
            
        # Update SSM parameter with correct value
        print(f"🔧 Updating SSM parameter to: {resource_server_identifier}")
        ssm.put_parameter(
            Name="/a2a/app/performance/agentcore/cognito_provider",
            Value=resource_server_identifier,
            Overwrite=True,
            Type='String',
            Description="Cognito provider name for BedrockAgentCore - Auto-corrected"
        )
        
        # Verify the update
        updated_value = ssm.get_parameter(Name="/a2a/app/performance/agentcore/cognito_provider")['Parameter']['Value']
        print(f"✅ SSM parameter updated successfully: {updated_value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error fixing SSM parameter: {e}")
        return False


def create_bedrockagentcore_oauth2_provider(region=None):
    """Create BedrockAgentCore OAuth2 Credential Provider - Idempotent version"""
    print("🔐 Creating BedrockAgentCore OAuth2 Credential Provider...")
    
    if region is None:
        region = DEFAULT_REGION
    
    try:
        # Initialize clients
        identity_client = boto3.client("bedrock-agentcore-control", region_name=region)
        ssm = boto3.client('ssm', region_name=region)
        
        # Get provider name from SSM parameter
        provider_name = ssm.get_parameter(Name="/a2a/app/performance/agentcore/cognito_provider")['Parameter']['Value']
        
        # STEP 1: Check if provider already exists
        print(f"🔍 Checking if provider '{provider_name}' exists...")
        try:
            response = identity_client.list_oauth2_credential_providers(maxResults=20)
            providers = response.get("credentialProviders", [])
            
            for provider in providers:
                if provider.get('name') == provider_name:
                    print(f"✅ Provider '{provider_name}' already exists")
                    print(f"   ARN: {provider['credentialProviderArn']}")
                    print(f"ℹ️  Skipping creation")
                    return provider
                    
        except Exception as e:
            print(f"⚠️  Error checking for existing provider: {e}")
        
        # STEP 2: Provider doesn't exist, create it
        print(f"ℹ️  Provider '{provider_name}' not found, will create")
        
        # Get all required parameters from SSM
        print("📥 Fetching Cognito configuration from SSM...")
        
        machine_client_id = ssm.get_parameter(Name="/a2a/app/performance/agentcore/machine_client_id")['Parameter']['Value']
        print(f"✅ Retrieved client ID: {machine_client_id}")
        
        # Get client secret
        cognito = boto3.client('cognito-idp', region_name=region)
        user_pool_id = ssm.get_parameter(Name="/a2a/app/performance/agentcore/userpool_id")['Parameter']['Value']
        
        client_response = cognito.describe_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=machine_client_id
        )
        client_secret = client_response['UserPoolClient'].get('ClientSecret', '')
        print(f"✅ Retrieved client secret: {client_secret[:4]}***")
        
        # Get URLs
        issuer = ssm.get_parameter(Name="/a2a/app/performance/agentcore/cognito_discovery_url")['Parameter']['Value']
        auth_url = ssm.get_parameter(Name="/a2a/app/performance/agentcore/cognito_auth_url")['Parameter']['Value']
        token_url = ssm.get_parameter(Name="/a2a/app/performance/agentcore/cognito_token_url")['Parameter']['Value']
        
        print(f"✅ Issuer: {issuer}")
        print(f"✅ Authorization Endpoint: {auth_url}")
        print(f"✅ Token Endpoint: {token_url}")
        
        print(f"🆕 Creating OAuth2 credential provider: {provider_name}")
        
        # Create OAuth2 credential provider
        try:
            cognito_provider = identity_client.create_oauth2_credential_provider(
                name=provider_name,
                credentialProviderVendor="CustomOauth2",
                oauth2ProviderConfigInput={
                    "customOauth2ProviderConfig": {
                        "clientId": machine_client_id,
                        "clientSecret": client_secret,
                        "oauthDiscovery": {
                            "authorizationServerMetadata": {
                                "issuer": issuer,
                                "authorizationEndpoint": auth_url,
                                "tokenEndpoint": token_url,
                                "responseTypes": ["code", "token"],
                            }
                        },
                    }
                },
            )
            
            print("✅ BedrockAgentCore OAuth2 credential provider created successfully!")
            provider_arn = cognito_provider["credentialProviderArn"]
            print(f"   Provider ARN: {provider_arn}")
            print(f"   Provider Name: {cognito_provider['name']}")
            
            return cognito_provider
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'ConflictException':
                # Race condition - provider was created between our check and create attempt
                print(f"✅ Provider '{provider_name}' already exists (created concurrently)")
                return True
            else:
                raise
        
    except ClientError as e:
        print(f"❌ Error creating BedrockAgentCore credential provider: {e}")
        return False
    except Exception as e:
        print(f"❌ Error creating BedrockAgentCore credential provider: {e}")
        return False


def list_oauth2_credential_providers(region=None):
    """List all BedrockAgentCore OAuth2 credential providers"""
    print("📋 Listing BedrockAgentCore OAuth2 credential providers...")
    
    if region is None:
        region = DEFAULT_REGION
    
    try:
        identity_client = boto3.client("bedrock-agentcore-control", region_name=region)
        
        response = identity_client.list_oauth2_credential_providers(maxResults=20)
        providers = response.get("credentialProviders", [])
        
        if not providers:
            print("ℹ️  No OAuth2 credential providers found")
            return []
        
        print(f"📋 Found {len(providers)} OAuth2 credential provider(s):")
        for provider in providers:
            print(f"  • Name: {provider.get('name', 'N/A')}")
            print(f"    ARN: {provider['credentialProviderArn']}")
            print(f"    Vendor: {provider.get('credentialProviderVendor', 'N/A')}")
            if "createdTime" in provider:
                print(f"    Created: {provider['createdTime']}")
            print()
        
        return providers
        
    except Exception as e:
        print(f"❌ Error listing OAuth2 credential providers: {e}")
        return []

def main():
    print("🚀 Setting up Cognito OAuth2 Provider for Performance Agent")
    print("=" * 60)
    print("📋 Using cognito.yaml as the single source of truth")
    
    try:
        # Deploy CloudFormation stack with ALL SSM parameters
        outputs = deploy_cognito_cloudformation()
        
        # Verify all SSM parameters exist
        if not verify_ssm_parameters():
            print("❌ Some SSM parameters are missing!")
            return
        
        # Create test user
        create_test_user()
        
        print("\n🎉 Cognito OAuth2 setup completed successfully!")
        print("📋 All SSM parameters created for BedrockAgentCore:")
        print("   - /a2a/app/performance/agentcore/machine_client_id")
        print("   - /a2a/app/performance/agentcore/web_client_id") 
        print("   - /a2a/app/performance/agentcore/cognito_provider")
        print("   - /a2a/app/performance/agentcore/cognito_domain")
        print("   - /a2a/app/performance/agentcore/cognito_token_url")
        print("   - /a2a/app/performance/agentcore/cognito_discovery_url")
        print("   - /a2a/app/performance/agentcore/gateway_iam_role")
        print("   - And more...")
        print("")
        print("🎯 Test User: testuser / TestPassword123!")
        print("")
        print("📋 Next Steps:")
        print("   1. Fix SSM parameters if needed: python cognito_credentials_provider.py fix-ssm")
        print("   2. Create BedrockAgentCore provider: python cognito_credentials_provider.py create-provider")
        print("   3. Deploy MCP Lambda tools")
        print("   4. Deploy agent runtime")
        print("   5. Test agent functionality")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fix-ssm":
        print("🔧 Running SSM Parameter Fix Only")
        print("=" * 40)
        success = fix_cognito_provider_ssm_parameter()
        if success:
            print("\n✅ SSM parameter fix completed successfully!")
            print("🎯 You can now test the agent - the resource credential provider should work.")
        else:
            print("\n❌ SSM parameter fix failed!")
            sys.exit(1)
    elif len(sys.argv) > 1 and sys.argv[1] == "create-provider":
        print("🔐 Creating BedrockAgentCore OAuth2 Credential Provider Only")
        print("=" * 55)
        success = create_bedrockagentcore_oauth2_provider()
        if success:
            print("\n✅ BedrockAgentCore OAuth2 credential provider created successfully!")
            print("🎯 The missing resource credential provider should now exist.")
            print("💡 You can now test the agent - it should work without 424/500 errors.")
        else:
            print("\n❌ Failed to create BedrockAgentCore OAuth2 credential provider!")
            sys.exit(1)
    elif len(sys.argv) > 1 and sys.argv[1] == "list-providers":
        print("📋 Listing BedrockAgentCore OAuth2 Credential Providers")
        print("=" * 50)
        providers = list_oauth2_credential_providers()
        print(f"\n📊 Summary: {len(providers)} OAuth2 credential provider(s) found")
    else:
        main()
