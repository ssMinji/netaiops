#!/usr/bin/env python3

"""
Setup Cognito OAuth2 Provider for Troubleshooting Agent using CloudFormation - Reference Implementation
This creates ALL SSM parameters that BedrockAgentCore expects, exactly like the reference
"""

import boto3
import json
import time
import sys
import os
from pathlib import Path
from botocore.exceptions import ClientError

# Add project root to path for shared config manager
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.append(project_root)

# Import only when needed (for update_config_with_cognito_details function)
AgentCoreConfigManager = None

# CloudFormation template for Cognito setup with ALL SSM parameters
COGNITO_TEMPLATE = {
    "AWSTemplateFormatVersion": "2010-09-09",
    "Description": "CloudFormation template for Troubleshooting Agent System with Cognito authentication",
    "Parameters": {
        "ResourceServerIdentifier": {
            "Type": "String",
            "Default": "troubleshooting-connectivity-analyzer",
            "Description": "Identifier for the Cognito Resource Server"
        },
        "TestUserPassword": {
            "Type": "String",
            "Default": "TestPassword123!",
            "NoEcho": True,
            "Description": "Password for test user (should be changed in production)"
        },
        "TempPassword": {
            "Type": "String", 
            "Default": "TempPassword123!",
            "NoEcho": True,
            "Description": "Temporary password for user creation"
        }
    },
    "Resources": {
        "UserPool": {
            "Type": "AWS::Cognito::UserPool",
            "Properties": {
                "UserPoolName": "TroubleshootingAgentGatewayPool",
                "MfaConfiguration": "OFF",
                "UsernameConfiguration": {
                    "CaseSensitive": False
                },
                "UsernameAttributes": ["email"],
                "AutoVerifiedAttributes": ["email"]
            }
        },
        "AdminGroup": {
            "Type": "AWS::Cognito::UserPoolGroup",
            "Properties": {
                "GroupName": "admin",
                "Description": "Administrator group",
                "UserPoolId": {"Ref": "UserPool"},
                "Precedence": 1
            }
        },
        "UserGroup": {
            "Type": "AWS::Cognito::UserPoolGroup",
            "Properties": {
                "GroupName": "user",
                "Description": "Regular user group",
                "UserPoolId": {"Ref": "UserPool"},
                "Precedence": 2
            }
        },
        "ResourceServer": {
            "Type": "AWS::Cognito::UserPoolResourceServer",
            "Properties": {
                "UserPoolId": {"Ref": "UserPool"},
                "Identifier": {"Ref": "ResourceServerIdentifier"},
                "Name": "Troubleshooting Connectivity Analyzer Resource Server",
                "Scopes": [
                    {
                        "ScopeName": "invoke",
                        "ScopeDescription": "Invoke troubleshooting agent runtime"
                    }
                ]
            }
        },
        "WebUserPoolClient": {
            "Type": "AWS::Cognito::UserPoolClient",
            "DependsOn": "ResourceServer",
            "Properties": {
                "ClientName": "TroubleshootingWebClient",
                "UserPoolId": {"Ref": "UserPool"},
                "GenerateSecret": False,
                "AllowedOAuthFlows": ["code"],
                "AllowedOAuthScopes": [
                    "openid",
                    "email",
                    "profile",
                    "troubleshooting-connectivity-analyzer/invoke"
                ],
                "AllowedOAuthFlowsUserPoolClient": True,
                "CallbackURLs": [
                    "http://localhost:8501/",
                    "https://example.com/auth/callback"
                ],
                "LogoutURLs": [
                    "http://localhost:8501/"
                ],
                "SupportedIdentityProviders": ["COGNITO"],
                "AccessTokenValidity": 60,
                "IdTokenValidity": 60,
                "RefreshTokenValidity": 30,
                "TokenValidityUnits": {
                    "AccessToken": "minutes",
                    "IdToken": "minutes",
                    "RefreshToken": "days"
                },
                "EnableTokenRevocation": True
            }
        },
        "MachineUserPoolClient": {
            "Type": "AWS::Cognito::UserPoolClient",
            "DependsOn": "ResourceServer",
            "Properties": {
                "ClientName": "TroubleshootingMachineClient",
                "UserPoolId": {"Ref": "UserPool"},
                "GenerateSecret": True,
                "ExplicitAuthFlows": ["ALLOW_REFRESH_TOKEN_AUTH"],
                "RefreshTokenValidity": 1,
                "AccessTokenValidity": 60,
                "IdTokenValidity": 60,
                "TokenValidityUnits": {
                    "AccessToken": "minutes",
                    "IdToken": "minutes",
                    "RefreshToken": "days"
                },
                "AllowedOAuthFlows": ["client_credentials"],
                "AllowedOAuthScopes": ["troubleshooting-connectivity-analyzer/invoke"],
                "AllowedOAuthFlowsUserPoolClient": True,
                "SupportedIdentityProviders": ["COGNITO"],
                "EnableTokenRevocation": True
            }
        },
        "UserPoolDomain": {
            "Type": "AWS::Cognito::UserPoolDomain",
            "Properties": {
                "UserPoolId": {"Ref": "UserPool"},
                "Domain": {
                    "Fn::Join": [
                        "",
                        [
                            "troubleshooting-connectivity-",
                            {"Ref": "AWS::AccountId"}
                        ]
                    ]
                }
            }
        },
        # ALL SSM Parameters that BedrockAgentCore expects - EXACTLY like reference
        "CognitoMachineClientIdParameter": {
            "Type": "AWS::SSM::Parameter",
            "Properties": {
                "Name": "/app/troubleshooting/agentcore/machine_client_id",
                "Type": "String",
                "Value": {"Ref": "MachineUserPoolClient"},
                "Description": "Machine Cognito client ID",
                "Tags": {
                    "Application": "Troubleshooting"
                }
            }
        },
        "CognitoWebClientIdParameter": {
            "Type": "AWS::SSM::Parameter",
            "Properties": {
                "Name": "/app/troubleshooting/agentcore/web_client_id",
                "Type": "String",
                "Value": {"Ref": "WebUserPoolClient"},
                "Description": "Cognito client ID for web app",
                "Tags": {
                    "Application": "Troubleshooting"
                }
            }
        },
        "UserPoolIdParameter": {
            "Type": "AWS::SSM::Parameter",
            "Properties": {
                "Name": "/app/troubleshooting/agentcore/userpool_id",
                "Type": "String",
                "Value": {"Ref": "UserPool"},
                "Description": "Cognito User Pool ID",
                "Tags": {
                    "Application": "Troubleshooting"
                }
            }
        },
        "CognitoProviderParameter": {
            "Type": "AWS::SSM::Parameter",
            "Properties": {
                "Name": "/app/troubleshooting/agentcore/cognito_provider",
                "Type": "String",
                "Value": {
                    "Fn::Join": [
                        "",
                        [
                            "troubleshooting-connectivity-",
                            {"Ref": "AWS::AccountId"}
                        ]
                    ]
                },
                "Description": "Cognito provider name for BedrockAgentCore",
                "Tags": {
                    "Application": "Troubleshooting"
                }
            }
        },
        "CognitoAuthScopeParameter": {
            "Type": "AWS::SSM::Parameter",
            "Properties": {
                "Name": "/app/troubleshooting/agentcore/cognito_auth_scope",
                "Type": "String",
                "Value": "troubleshooting-connectivity-analyzer/invoke",
                "Description": "OAuth2 scope for Cognito auth",
                "Tags": {
                    "Application": "Troubleshooting"
                }
            }
        },
        "CognitoDiscoveryURLParameter": {
            "Type": "AWS::SSM::Parameter",
            "Properties": {
                "Name": "/app/troubleshooting/agentcore/cognito_discovery_url",
                "Type": "String",
                "Value": {
                    "Fn::Sub": "https://cognito-idp.${AWS::Region}.amazonaws.com/${UserPool}/.well-known/openid-configuration"
                },
                "Description": "OAuth2 Discovery URL",
                "Tags": {
                    "Application": "Troubleshooting"
                }
            }
        },
        "CognitoTokenURLParameter": {
            "Type": "AWS::SSM::Parameter",
            "Properties": {
                "Name": "/app/troubleshooting/agentcore/cognito_token_url",
                "Type": "String",
                "Value": {
                    "Fn::Join": [
                        "",
                        [
                            {
                                "Fn::Sub": "https://troubleshooting-connectivity-${AWS::AccountId}.auth.${AWS::Region}.amazoncognito.com/oauth2/token"
                            }
                        ]
                    ]
                },
                "Description": "OAuth2 Token URL",
                "Tags": {
                    "Application": "Troubleshooting"
                }
            }
        },
        "CognitoAuthorizeURLParameter": {
            "Type": "AWS::SSM::Parameter",
            "Properties": {
                "Name": "/app/troubleshooting/agentcore/cognito_auth_url",
                "Type": "String",
                "Value": {
                    "Fn::Join": [
                        "",
                        [
                            {
                                "Fn::Sub": "https://troubleshooting-connectivity-${AWS::AccountId}.auth.${AWS::Region}.amazoncognito.com/oauth2/authorize"
                            }
                        ]
                    ]
                },
                "Description": "OAuth2 Authorization URL",
                "Tags": {
                    "Application": "Troubleshooting"
                }
            }
        },
        "CognitoDomainParameter": {
            "Type": "AWS::SSM::Parameter",
            "Properties": {
                "Name": "/app/troubleshooting/agentcore/cognito_domain",
                "Type": "String",
                "Value": {
                    "Fn::Join": [
                        "",
                        [
                            {
                                "Fn::Sub": "https://troubleshooting-connectivity-${AWS::AccountId}.auth.${AWS::Region}.amazoncognito.com"
                            }
                        ]
                    ]
                },
                "Description": "Cognito hosted domain for OAuth2",
                "Tags": {
                    "Application": "Troubleshooting"
                }
            }
        }
    },
    "Outputs": {
        "UserPoolId": {
            "Description": "Cognito User Pool ID",
            "Value": {"Ref": "UserPool"},
            "Export": {
                "Name": {"Fn::Sub": "${AWS::StackName}-UserPoolId"}
            }
        },
        "WebClientId": {
            "Description": "Web Application Client ID",
            "Value": {"Ref": "WebUserPoolClient"},
            "Export": {
                "Name": {"Fn::Sub": "${AWS::StackName}-WebClientId"}
            }
        },
        "MachineClientId": {
            "Description": "Machine Application Client ID",
            "Value": {"Ref": "MachineUserPoolClient"},
            "Export": {
                "Name": {"Fn::Sub": "${AWS::StackName}-MachineClientId"}
            }
        },
        "CognitoDomain": {
            "Description": "Cognito Domain",
            "Value": {
                "Fn::Join": [
                    "",
                    [
                        {
                            "Fn::Sub": "https://troubleshooting-connectivity-${AWS::AccountId}.auth.${AWS::Region}.amazoncognito.com"
                        }
                    ]
                ]
            },
            "Export": {
                "Name": {"Fn::Sub": "${AWS::StackName}-CognitoDomain"}
            }
        }
    }
}

def deploy_cognito_cloudformation():
    """Deploy Cognito infrastructure using CloudFormation"""
    print("🚀 Deploying Cognito infrastructure with CloudFormation...")
    
    cloudformation = boto3.client('cloudformation', region_name='us-east-1')
    stack_name = "troubleshooting-agentcore-cognito"
    
    try:
        # Check if stack exists
        try:
            cloudformation.describe_stacks(StackName=stack_name)
            stack_exists = True
            print(f"🔄 Stack '{stack_name}' exists, updating...")
        except cloudformation.exceptions.ClientError:
            stack_exists = False
            print(f"🆕 Creating new stack '{stack_name}'...")
        
        # Deploy or update stack
        if stack_exists:
            cloudformation.update_stack(
                StackName=stack_name,
                TemplateBody=json.dumps(COGNITO_TEMPLATE),
                Capabilities=['CAPABILITY_IAM']
            )
            print("⏳ Waiting for stack update to complete...")
            cloudformation.get_waiter('stack_update_complete').wait(StackName=stack_name)
        else:
            cloudformation.create_stack(
                StackName=stack_name,
                TemplateBody=json.dumps(COGNITO_TEMPLATE),
                Capabilities=['CAPABILITY_IAM']
            )
            print("⏳ Waiting for stack creation to complete...")
            cloudformation.get_waiter('stack_create_complete').wait(StackName=stack_name)
        
        print("✅ CloudFormation stack deployed successfully!")
        
        # Get stack outputs
        response = cloudformation.describe_stacks(StackName=stack_name)
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

def verify_ssm_parameters():
    """Verify all required SSM parameters exist"""
    print("🔍 Verifying SSM parameters...")
    
    ssm = boto3.client('ssm', region_name='us-east-1')
    required_parameters = [
        "/app/troubleshooting/agentcore/machine_client_id",
        "/app/troubleshooting/agentcore/web_client_id",
        "/app/troubleshooting/agentcore/cognito_provider",
        "/app/troubleshooting/agentcore/cognito_domain",
        "/app/troubleshooting/agentcore/cognito_token_url",
        "/app/troubleshooting/agentcore/cognito_discovery_url",
        "/app/troubleshooting/agentcore/cognito_auth_url",
        "/app/troubleshooting/agentcore/cognito_auth_scope",
        "/app/troubleshooting/agentcore/userpool_id"
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

def create_test_user():
    """Create test user in Cognito"""
    print("👤 Creating test user...")
    
    try:
        ssm = boto3.client('ssm', region_name='us-east-1')
        user_pool_id = ssm.get_parameter(Name="/app/troubleshooting/agentcore/userpool_id")['Parameter']['Value']
        
        # Get passwords from environment variables or use defaults (should be overridden in production)
        temp_password = os.environ.get('COGNITO_TEMP_PASSWORD', 'TempPassword123!')
        final_password = os.environ.get('COGNITO_TEST_PASSWORD', 'TestPassword123!')
        
        cognito = boto3.client('cognito-idp', region_name='us-east-1')
        
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
                MessageAction="RESEND"
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

def fix_cognito_provider_ssm_parameter():
    """Dynamically discover actual resource server and fix SSM parameter"""
    print("🔧 Fixing Cognito provider SSM parameter...")
    
    try:
        ssm = boto3.client('ssm', region_name='us-east-1')
        cognito = boto3.client('cognito-idp', region_name='us-east-1')
        
        # Get user pool ID and web client ID from SSM
        print("📋 Getting existing SSM parameters...")
        user_pool_id = ssm.get_parameter(Name="/app/troubleshooting/agentcore/userpool_id")['Parameter']['Value']
        web_client_id = ssm.get_parameter(Name="/app/troubleshooting/agentcore/web_client_id")['Parameter']['Value']
        
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
        current_value = ssm.get_parameter(Name="/app/troubleshooting/agentcore/cognito_provider")['Parameter']['Value']
        print(f"📋 Current SSM parameter value: {current_value}")
        
        if current_value == resource_server_identifier:
            print("✅ SSM parameter is already correct!")
            return True
            
        # Update SSM parameter with correct value
        print(f"🔧 Updating SSM parameter to: {resource_server_identifier}")
        ssm.put_parameter(
            Name="/app/troubleshooting/agentcore/cognito_provider",
            Value=resource_server_identifier,
            Overwrite=True,
            Type='String',
            Description="Cognito provider name for BedrockAgentCore - Auto-corrected"
        )
        
        # Verify the update
        updated_value = ssm.get_parameter(Name="/app/troubleshooting/agentcore/cognito_provider")['Parameter']['Value']
        print(f"✅ SSM parameter updated successfully: {updated_value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error fixing SSM parameter: {e}")
        return False


def create_bedrockagentcore_oauth2_provider():
    """Create BedrockAgentCore OAuth2 Credential Provider - Following Reference Implementation"""
    print("🔐 Creating BedrockAgentCore OAuth2 Credential Provider...")
    
    try:
        # Initialize bedrock-agentcore-control client
        identity_client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
        ssm = boto3.client('ssm', region_name='us-east-1')
        
        # Get all required parameters from SSM
        print("📥 Fetching Cognito configuration from SSM...")
        
        machine_client_id = ssm.get_parameter(Name="/app/troubleshooting/agentcore/machine_client_id")['Parameter']['Value']
        print(f"✅ Retrieved client ID: {machine_client_id}")
        
        # Get client secret
        cognito = boto3.client('cognito-idp', region_name='us-east-1')
        user_pool_id = ssm.get_parameter(Name="/app/troubleshooting/agentcore/userpool_id")['Parameter']['Value']
        
        client_response = cognito.describe_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=machine_client_id
        )
        client_secret = client_response['UserPoolClient'].get('ClientSecret', '')
        print(f"✅ Retrieved client secret: {client_secret[:4]}***")
        
        # Get URLs
        issuer = ssm.get_parameter(Name="/app/troubleshooting/agentcore/cognito_discovery_url")['Parameter']['Value']
        auth_url = ssm.get_parameter(Name="/app/troubleshooting/agentcore/cognito_auth_url")['Parameter']['Value']
        token_url = ssm.get_parameter(Name="/app/troubleshooting/agentcore/cognito_token_url")['Parameter']['Value']
        
        print(f"✅ Issuer: {issuer}")
        print(f"✅ Authorization Endpoint: {auth_url}")
        print(f"✅ Token Endpoint: {token_url}")
        
        # Get provider name from SSM parameter
        provider_name = ssm.get_parameter(Name="/app/troubleshooting/agentcore/cognito_provider")['Parameter']['Value']
        
        print(f"⚙️  Creating OAuth2 credential provider: {provider_name}")
        
        # Create OAuth2 credential provider
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
            print(f"ℹ️  OAuth2 credential provider '{provider_name}' already exists")
            return True
        else:
            print(f"❌ Error creating BedrockAgentCore credential provider: {e}")
            return False
    except Exception as e:
        print(f"❌ Error creating BedrockAgentCore credential provider: {e}")
        return False


def list_oauth2_credential_providers():
    """List all BedrockAgentCore OAuth2 credential providers"""
    print("📋 Listing BedrockAgentCore OAuth2 credential providers...")
    
    try:
        identity_client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
        
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


def update_config_with_cognito_details():
    """Update dynamic configuration with Cognito details"""
    print("📝 Updating dynamic configuration...")
    
    try:
        # Import only when needed
        global AgentCoreConfigManager
        if AgentCoreConfigManager == None:
            from shared.config_manager import AgentCoreConfigManager
        
        config_manager = AgentCoreConfigManager()
        ssm = boto3.client('ssm', region_name='us-east-1')
        
        # Get values from SSM parameters
        machine_client_id = ssm.get_parameter(Name="/app/troubleshooting/agentcore/machine_client_id")['Parameter']['Value']
        web_client_id = ssm.get_parameter(Name="/app/troubleshooting/agentcore/web_client_id")['Parameter']['Value']
        user_pool_id = ssm.get_parameter(Name="/app/troubleshooting/agentcore/userpool_id")['Parameter']['Value']
        domain_prefix = ssm.get_parameter(Name="/app/troubleshooting/agentcore/cognito_provider")['Parameter']['Value']
        discovery_url = ssm.get_parameter(Name="/app/troubleshooting/agentcore/cognito_discovery_url")['Parameter']['Value']
        
        # Get client secret for machine client
        cognito = boto3.client('cognito-idp', region_name='us-east-1')
        client_response = cognito.describe_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=machine_client_id
        )
        client_secret = client_response['UserPoolClient'].get('ClientSecret', '')
        
        updates = {
            "authentication": {
                "type": "cognito",
                "cognito": {
                    "user_pool_id": user_pool_id,
                    "client_id": machine_client_id,
                    "client_secret": client_secret,
                    "web_client_id": web_client_id,
                    "region": "us-east-1",
                    "domain_prefix": domain_prefix,
                    "resource_server_identifier": domain_prefix,  # Use the corrected value
                    "scopes": [f"{domain_prefix}/invoke"],
                    "discovery_url": discovery_url,
                    "auth_flow": "CLIENT_CREDENTIALS",
                    "access_token": ""
                }
            }
        }
        
        config_manager.update_dynamic_config(updates)
        print("✅ Dynamic configuration updated with Cognito details")
        
    except Exception as e:
        print(f"❌ Error updating configuration: {e}")

def main():
    print("🚀 Setting up Cognito OAuth2 Provider for Troubleshooting Agent")
    print("=" * 60)
    
    try:
        # Deploy CloudFormation stack with ALL SSM parameters
        outputs = deploy_cognito_cloudformation()
        
        # Verify all SSM parameters exist
        if not verify_ssm_parameters():
            print("❌ Some SSM parameters are missing!")
            return
        
        # Create test user
        create_test_user()
        
        # Update dynamic configuration
        update_config_with_cognito_details()
        
        print("\n🎉 Cognito OAuth2 setup completed successfully!")
        print("📋 All SSM parameters created for BedrockAgentCore:")
        print("   - /app/troubleshooting/agentcore/machine_client_id")
        print("   - /app/troubleshooting/agentcore/web_client_id") 
        print("   - /app/troubleshooting/agentcore/cognito_provider")
        print("   - /app/troubleshooting/agentcore/cognito_domain")
        print("   - /app/troubleshooting/agentcore/cognito_token_url")
        print("   - /app/troubleshooting/agentcore/cognito_discovery_url")
        print("   - And more...")
        print("")
        print("🎯 Test User: testuser / TestPassword123!")
        print("")
        print("📋 Next Steps:")
        print("   1. Deploy MCP Lambda: ./04-deploy-mcp-tool-lambda-cloudshell.sh")
        print("   2. Create gateway targets: ./05-create-gateway-targets-cloudshell.sh")
        print("   3. Deploy agent runtime: python 08-deploy-agent-runtime.py")
        print("   4. Test agent: python ../test/test_agent.py troubleshooting")
        
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
