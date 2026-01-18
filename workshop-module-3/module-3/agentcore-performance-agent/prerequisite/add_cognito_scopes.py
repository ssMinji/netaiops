#!/usr/bin/env python3
"""
Script to add gateway:read and gateway:write scopes to the deployed Cognito stack.
This script updates the ResourceServer in the troubleshooting-agentcore-cognito stack
to include the new scopes and updates the UserPoolClients to use them.

It also updates the module3-config.json file with the Cognito configuration values.

Usage:
    python3 add_cognito_scopes.py <stack_name> <region> <account_id> [config_file_path]
    
Example:
    python3 add_cognito_scopes.py troubleshooting-agentcore-cognito us-east-1 237616366264
    python3 add_cognito_scopes.py troubleshooting-agentcore-cognito us-east-1 237616366264 /path/to/module3-config.json
"""

import boto3
import sys
import time
import json
import os
from botocore.exceptions import ClientError

def get_stack_resources(cfn_client, stack_name):
    """Get resources from the CloudFormation stack."""
    try:
        response = cfn_client.describe_stack_resources(StackName=stack_name)
        resources = {}
        for resource in response['StackResources']:
            resources[resource['LogicalResourceId']] = resource['PhysicalResourceId']
        return resources
    except ClientError as e:
        print(f"Error getting stack resources: {e}")
        sys.exit(1)

def get_resource_server_identifier(cognito_client, user_pool_id):
    """Get the current resource server identifier."""
    try:
        response = cognito_client.list_resource_servers(
            UserPoolId=user_pool_id,
            MaxResults=50
        )
        if response['ResourceServers']:
            return response['ResourceServers'][0]['Identifier']
        return None
    except ClientError as e:
        print(f"Error getting resource server: {e}")
        return None

def update_resource_server(cognito_client, user_pool_id, identifier):
    """Update the resource server to include gateway:read and gateway:write scopes."""
    try:
        # Get current resource server
        response = cognito_client.describe_resource_server(
            UserPoolId=user_pool_id,
            Identifier=identifier
        )
        
        current_scopes = response['ResourceServer'].get('Scopes', [])
        scope_names = [scope['ScopeName'] for scope in current_scopes]
        
        print(f"Current scopes: {scope_names}")
        
        # Add new scopes if they don't exist
        new_scopes = []
        if 'gateway:read' not in scope_names:
            new_scopes.append({
                'ScopeName': 'gateway:read',
                'ScopeDescription': 'Read access to gateway'
            })
        if 'gateway:write' not in scope_names:
            new_scopes.append({
                'ScopeName': 'gateway:write',
                'ScopeDescription': 'Write access to gateway'
            })
        
        if not new_scopes:
            print("Scopes gateway:read and gateway:write already exist!")
            return True
        
        # Combine existing and new scopes
        all_scopes = current_scopes + new_scopes
        
        print(f"Adding new scopes: {[s['ScopeName'] for s in new_scopes]}")
        
        # Update resource server
        cognito_client.update_resource_server(
            UserPoolId=user_pool_id,
            Identifier=identifier,
            Name=response['ResourceServer']['Name'],
            Scopes=all_scopes
        )
        
        print("✓ Resource server updated successfully")
        return True
        
    except ClientError as e:
        print(f"Error updating resource server: {e}")
        return False

def update_user_pool_client(cognito_client, user_pool_id, client_id, client_name, identifier):
    """Update user pool client to include new scopes."""
    try:
        # Get current client configuration
        response = cognito_client.describe_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=client_id
        )
        
        client = response['UserPoolClient']
        current_scopes = client.get('AllowedOAuthScopes', [])
        
        print(f"\n{client_name} current scopes: {current_scopes}")
        
        # Add new scopes
        new_scopes = [
            f"{identifier}/gateway:read",
            f"{identifier}/gateway:write"
        ]
        
        # Combine with existing scopes (avoid duplicates)
        updated_scopes = list(set(current_scopes + new_scopes))
        
        print(f"{client_name} updated scopes: {updated_scopes}")
        
        # Update client
        update_params = {
            'UserPoolId': user_pool_id,
            'ClientId': client_id,
            'ClientName': client.get('ClientName'),
            'AllowedOAuthScopes': updated_scopes,
            'AllowedOAuthFlows': client.get('AllowedOAuthFlows', []),
            'AllowedOAuthFlowsUserPoolClient': client.get('AllowedOAuthFlowsUserPoolClient', False),
            'CallbackURLs': client.get('CallbackURLs', []),
            'LogoutURLs': client.get('LogoutURLs', []),
            'SupportedIdentityProviders': client.get('SupportedIdentityProviders', []),
            'RefreshTokenValidity': client.get('RefreshTokenValidity', 30),
            'AccessTokenValidity': client.get('AccessTokenValidity', 60),
            'IdTokenValidity': client.get('IdTokenValidity', 60),
            'TokenValidityUnits': client.get('TokenValidityUnits', {}),
            'EnableTokenRevocation': client.get('EnableTokenRevocation', True)
        }
        
        # Add ExplicitAuthFlows if present (for machine client)
        if 'ExplicitAuthFlows' in client:
            update_params['ExplicitAuthFlows'] = client['ExplicitAuthFlows']
        
        cognito_client.update_user_pool_client(**update_params)
        
        print(f"✓ {client_name} updated successfully")
        return True
        
    except ClientError as e:
        print(f"Error updating {client_name}: {e}")
        return False

def update_ssm_parameter(ssm_client, parameter_name, new_value):
    """Update SSM parameter with new scope value."""
    try:
        # Check if parameter exists
        try:
            response = ssm_client.get_parameter(Name=parameter_name)
            current_value = response['Parameter']['Value']
            print(f"\nCurrent value of {parameter_name}: {current_value}")
        except ClientError:
            print(f"Parameter {parameter_name} not found, will create it")
            current_value = ""
        
        # Update parameter
        ssm_client.put_parameter(
            Name=parameter_name,
            Value=new_value,
            Type='String',
            Overwrite=True,
            Description='OAuth2 scope for Cognito auth (updated with gateway scopes)'
        )
        
        print(f"✓ Updated {parameter_name} to: {new_value}")
        return True
        
    except ClientError as e:
        print(f"Error updating SSM parameter {parameter_name}: {e}")
        return False

def update_config_file(config_file_path, machine_client_id, cognito_provider, cognito_auth_scope, cognito_discovery_url):
    """Update the module3-config.json file with Cognito values."""
    try:
        # Read existing config
        if not os.path.exists(config_file_path):
            print(f"Warning: Config file not found at {config_file_path}")
            return False
        
        with open(config_file_path, 'r') as f:
            config = json.load(f)
        
        # Determine which section to update based on the cognito_provider value
        # If it contains 'troubleshooting', update agentcore_troubleshooting
        # If it contains 'performance', update agentcore_performance
        if 'troubleshooting' in cognito_provider.lower():
            section_key = 'agentcore_troubleshooting'
        elif 'performance' in cognito_provider.lower():
            section_key = 'agentcore_performance'
        else:
            # Default to troubleshooting if we can't determine
            section_key = 'agentcore_troubleshooting'
        
        # Ensure the section exists
        if section_key not in config:
            config[section_key] = {}
        
        # Update values
        config[section_key]['machine_client_id'] = machine_client_id
        config[section_key]['cognito_provider'] = cognito_provider
        config[section_key]['cognito_auth_scope'] = cognito_auth_scope
        config[section_key]['cognito_discovery_url'] = cognito_discovery_url
        
        # Write back to file
        with open(config_file_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"\n✓ Updated {config_file_path}")
        print(f"  Section: {section_key}")
        print(f"  machine_client_id: {machine_client_id}")
        print(f"  cognito_provider: {cognito_provider}")
        print(f"  cognito_auth_scope: {cognito_auth_scope}")
        print(f"  cognito_discovery_url: {cognito_discovery_url}")
        
        return True
        
    except Exception as e:
        print(f"Error updating config file: {e}")
        return False

def main():
    """Main function to update Cognito resources."""
    # Parse command line arguments
    if len(sys.argv) < 4 or len(sys.argv) > 5:
        print("Error: Invalid number of arguments")
        print("\nUsage:")
        print("    python3 add_cognito_scopes.py <stack_name> <region> <account_id> [config_file_path]")
        print("\nExample:")
        print("    python3 add_cognito_scopes.py troubleshooting-agentcore-cognito us-east-1 237616366264")
        print("    python3 add_cognito_scopes.py troubleshooting-agentcore-cognito us-east-1 237616366264 /path/to/module3-config.json")
        sys.exit(1)
    
    stack_name = sys.argv[1]
    region = sys.argv[2]
    account_id = sys.argv[3]
    
    # Default config file path or use provided one
    if len(sys.argv) == 5:
        config_file_path = sys.argv[4]
    else:
        # Default to module3-config.json in the module-3 directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_file_path = os.path.join(script_dir, '..', '..', 'module3-config.json')
    
    print(f"Starting Cognito scope update for stack: {stack_name}")
    print(f"Region: {region}")
    print(f"Account: {account_id}\n")
    
    # Initialize AWS clients
    cfn_client = boto3.client('cloudformation', region_name=region)
    cognito_client = boto3.client('cognito-idp', region_name=region)
    ssm_client = boto3.client('ssm', region_name=region)
    
    # Get stack resources
    print("Getting stack resources...")
    resources = get_stack_resources(cfn_client, stack_name)
    
    user_pool_id = resources.get('UserPool')
    web_client_id = resources.get('WebUserPoolClient')
    machine_client_id = resources.get('MachineUserPoolClient')
    
    if not all([user_pool_id, web_client_id, machine_client_id]):
        print("Error: Could not find all required resources in stack")
        sys.exit(1)
    
    print(f"User Pool ID: {user_pool_id}")
    print(f"Web Client ID: {web_client_id}")
    print(f"Machine Client ID: {machine_client_id}\n")
    
    # Get resource server identifier
    print("Getting resource server identifier...")
    identifier = get_resource_server_identifier(cognito_client, user_pool_id)
    
    if not identifier:
        print("Error: Could not find resource server")
        sys.exit(1)
    
    print(f"Resource Server Identifier: {identifier}\n")
    
    # Step 1: Update Resource Server with new scopes
    print("=" * 60)
    print("Step 1: Updating Resource Server")
    print("=" * 60)
    if not update_resource_server(cognito_client, user_pool_id, identifier):
        print("Failed to update resource server")
        sys.exit(1)
    
    # Wait a bit for changes to propagate
    print("\nWaiting for changes to propagate...")
    time.sleep(2)
    
    # Step 2: Update Web Client
    print("\n" + "=" * 60)
    print("Step 2: Updating Web User Pool Client")
    print("=" * 60)
    if not update_user_pool_client(cognito_client, user_pool_id, web_client_id, "WebUserPoolClient", identifier):
        print("Failed to update web client")
        sys.exit(1)
    
    # Step 3: Update Machine Client
    print("\n" + "=" * 60)
    print("Step 3: Updating Machine User Pool Client")
    print("=" * 60)
    if not update_user_pool_client(cognito_client, user_pool_id, machine_client_id, "MachineUserPoolClient", identifier):
        print("Failed to update machine client")
        sys.exit(1)
    
    # Step 4: Update SSM Parameter
    print("\n" + "=" * 60)
    print("Step 4: Updating SSM Parameter")
    print("=" * 60)
    
    # Construct the new scope value
    new_scope_value = f"{identifier}/gateway:read {identifier}/gateway:write"
    
    # Try both possible SSM parameter paths
    ssm_paths = [
        '/app/troubleshooting/agentcore/cognito_auth_scope',
        '/a2a/app/performance/agentcore/cognito_auth_scope'
    ]
    
    updated_any = False
    for param_path in ssm_paths:
        try:
            ssm_client.get_parameter(Name=param_path)
            if update_ssm_parameter(ssm_client, param_path, new_scope_value):
                updated_any = True
        except ClientError:
            print(f"Parameter {param_path} does not exist, skipping...")
    
    if not updated_any:
        print("Warning: No SSM parameters were updated. You may need to update them manually.")
    
    print("\n" + "=" * 60)
    print("✓ All Cognito updates completed successfully!")
    print("=" * 60)
    print("\nNew scopes added:")
    print(f"  - {identifier}/gateway:read")
    print(f"  - {identifier}/gateway:write")
    print("\nThese scopes are now available for both Web and Machine clients.")
    
    # Step 5: Update config file
    print("\n" + "=" * 60)
    print("Step 5: Updating Configuration File")
    print("=" * 60)
    
    # Get cognito provider from SSM or construct it
    cognito_provider = None
    try:
        # Try to get from SSM first
        for param_path in ['/app/troubleshooting/agentcore/cognito_provider', '/a2a/app/performance/agentcore/cognito_provider']:
            try:
                response = ssm_client.get_parameter(Name=param_path)
                cognito_provider = response['Parameter']['Value']
                print(f"Found cognito_provider in SSM: {cognito_provider}")
                break
            except ClientError:
                continue
    except Exception as e:
        print(f"Could not retrieve cognito_provider from SSM: {e}")
    
    # If not found in SSM, we'll skip the config update
    if not cognito_provider:
        print("Warning: Could not determine cognito_provider value. Skipping config file update.")
        print("You may need to update the config file manually.")
    else:
        # Get discovery URL from SSM
        discovery_url = None
        try:
            for param_path in ['/app/troubleshooting/agentcore/cognito_discovery_url', '/a2a/app/performance/agentcore/cognito_discovery_url']:
                try:
                    response = ssm_client.get_parameter(Name=param_path)
                    discovery_url = response['Parameter']['Value']
                    break
                except ClientError:
                    continue
        except Exception:
            pass
        
        if not discovery_url:
            discovery_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration"
        
        # Update config file
        update_config_file(
            config_file_path,
            machine_client_id,
            cognito_provider,
            new_scope_value,
            discovery_url
        )
    
    print("\n" + "=" * 60)
    print("✓ All updates completed successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
