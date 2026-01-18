#!/usr/bin/env python3

import sys
import boto3
import click
import subprocess
import shlex
import os
import json
from pathlib import Path
from utils import get_aws_region


def get_ssm_parameter(parameter_name: str) -> str:
    """Get parameter from SSM Parameter Store"""
    try:
        ssm = boto3.client('ssm', region_name=get_aws_region())
        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        return response['Parameter']['Value']
    except Exception as e:
        click.echo(f"Error retrieving SSM parameter {parameter_name}: {e}", err=True)
        sys.exit(1)


@click.group()
def cli():
    """NetOps AgentCore Runtime Management - Reference Implementation Style"""
    pass


def ensure_ssm_permissions():
    """Ensure the execution role has SSM permissions"""
    print("🔍 Checking SSM permissions for execution role...")
    
    try:
        iam = boto3.client('iam')
        role_name = "performance-gateway-execution-role"
        
        # Check attached managed policies
        attached_policies = iam.list_attached_role_policies(RoleName=role_name)
        ssm_policy_attached = any(
            'SSM' in policy['PolicyName'] or 'SSMReadOnly' in policy['PolicyName'] 
            for policy in attached_policies['AttachedPolicies']
        )
        
        if ssm_policy_attached:
            print("✅ SSM permissions already attached")
            return True
            
        # Check inline policies for SSM permissions
        try:
            policy_doc = iam.get_role_policy(RoleName=role_name, PolicyName="BedrockAgentCoreExecutionPolicy")
            policy_str = str(policy_doc['PolicyDocument'])
            if 'ssm:GetParameter' in policy_str:
                print("✅ SSM permissions found in inline policy")
                return True
        except iam.exceptions.NoSuchEntityException:
            pass
            
        # Add SSM permissions
        print("❌ SSM permissions missing - adding AmazonSSMReadOnlyAccess...")
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AmazonSSMReadOnlyAccess"
        )
        print("✅ SSM permissions added successfully!")
        return True
        
    except Exception as e:
        print(f"⚠️  Could not verify/add SSM permissions: {e}")
        print("🔧 Runtime may fail if SSM access is missing")
        return False


def verify_codebuild_role_trust_policy(role_name: str, max_attempts: int = 6, wait_seconds: int = 5):
    """Verify that the CodeBuild role trust policy is properly set and propagated.
    
    Args:
        role_name: Name of the CodeBuild role to verify
        max_attempts: Maximum number of verification attempts (default: 6)
        wait_seconds: Seconds to wait between attempts (default: 5)
    
    Returns:
        True if verification succeeds, False otherwise
    """
    import time
    
    try:
        iam = boto3.client('iam')
        
        print(f"🔍 Verifying trust policy propagation for {role_name}...")
        
        for attempt in range(1, max_attempts + 1):
            try:
                # Get the current assume role policy
                response = iam.get_role(RoleName=role_name)
                assume_role_doc = response['Role']['AssumeRolePolicyDocument']
                
                # Check if CodeBuild service is in the trust policy
                has_codebuild = False
                if 'Statement' in assume_role_doc:
                    for statement in assume_role_doc['Statement']:
                        if statement.get('Effect') == 'Allow':
                            principal = statement.get('Principal', {})
                            if isinstance(principal, dict):
                                service = principal.get('Service', '')
                                if service == 'codebuild.amazonaws.com' or \
                                   (isinstance(service, list) and 'codebuild.amazonaws.com' in service):
                                    has_codebuild = True
                                    break
                
                if has_codebuild:
                    print(f"✅ Trust policy verified and propagated (attempt {attempt}/{max_attempts})")
                    return True
                else:
                    print(f"⏳ Trust policy not yet propagated (attempt {attempt}/{max_attempts}), waiting {wait_seconds}s...")
                    time.sleep(wait_seconds)
                    
            except Exception as e:
                print(f"⚠️  Verification attempt {attempt}/{max_attempts} failed: {e}")
                if attempt < max_attempts:
                    time.sleep(wait_seconds)
        
        print(f"⚠️  Trust policy verification timed out after {max_attempts} attempts")
        return False
        
    except Exception as e:
        print(f"⚠️  Could not verify trust policy: {e}")
        return False


def fix_codebuild_role_trust_policy(region: str):
    """Fix the trust policy of CodeBuild role created by AgentCore SDK.
    
    The AgentCore SDK creates the CodeBuild role but doesn't set up proper trust policy.
    This function adds the necessary trust relationship with codebuild.amazonaws.com
    and waits for the change to propagate.
    """
    import time
    
    try:
        iam = boto3.client('iam')
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']
        
        # Generate the role name that AgentCore SDK creates
        # Format: AmazonBedrockAgentCoreSDKCodeBuild-{region}-{hash}
        # We need to find it by listing roles with this prefix
        role_name_prefix = f"AmazonBedrockAgentCoreSDKCodeBuild-{region}-"
        
        print(f"🔍 Looking for CodeBuild role with prefix: {role_name_prefix}")
        
        # List roles to find the CodeBuild role
        paginator = iam.get_paginator('list_roles')
        codebuild_role = None
        
        for page in paginator.paginate():
            for role in page['Roles']:
                if role['RoleName'].startswith(role_name_prefix):
                    codebuild_role = role
                    print(f"✅ Found CodeBuild role: {role['RoleName']}")
                    break
            if codebuild_role:
                break
        
        if not codebuild_role:
            print("ℹ️  CodeBuild role not yet created by AgentCore SDK")
            return False
        
        role_name = codebuild_role['RoleName']
        
        # Check if trust policy is already correct
        current_policy = codebuild_role.get('AssumeRolePolicyDocument', {})
        has_codebuild = False
        if 'Statement' in current_policy:
            for statement in current_policy['Statement']:
                if statement.get('Effect') == 'Allow':
                    principal = statement.get('Principal', {})
                    if isinstance(principal, dict):
                        service = principal.get('Service', '')
                        if service == 'codebuild.amazonaws.com' or \
                           (isinstance(service, list) and 'codebuild.amazonaws.com' in service):
                            has_codebuild = True
                            break
        
        if has_codebuild:
            print(f"✅ Trust policy already correct for {role_name}")
            return True
        
        # Define the correct trust policy for CodeBuild
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "codebuild.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        print(f"🔧 Updating trust policy for role: {role_name}")
        
        # Update the assume role policy
        iam.update_assume_role_policy(
            RoleName=role_name,
            PolicyDocument=json.dumps(trust_policy)
        )
        
        print(f"✅ Trust policy updated for {role_name}")
        
        # Wait and verify propagation with retry logic
        if verify_codebuild_role_trust_policy(role_name, max_attempts=6, wait_seconds=5):
            print(f"✅ Trust policy fully propagated and ready")
            return True
        else:
            print(f"⚠️  Trust policy update may not be fully propagated yet")
            return False
        
    except Exception as e:
        print(f"⚠️  Could not fix CodeBuild role trust policy: {e}")
        return False


def ensure_execution_role_permissions(role_arn: str):
    """Ensure the execution role has all required permissions (ECR, SSM, Lambda)"""
    print("🔍 Checking execution role permissions...")
    
    try:
        iam = boto3.client('iam')
        role_name = role_arn.split('/')[-1]  # Extract role name from ARN
        
        # Required managed policies
        required_policies = [
            ("arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly", "ECR"),
            ("arn:aws:iam::aws:policy/AmazonSSMReadOnlyAccess", "SSM"), 
            ("arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole", "Lambda")
        ]
        
        # Check currently attached policies
        attached_policies = iam.list_attached_role_policies(RoleName=role_name)
        attached_arns = [policy['PolicyArn'] for policy in attached_policies['AttachedPolicies']]
        
        # Attach missing policies
        for policy_arn, service in required_policies:
            if policy_arn not in attached_arns:
                print(f"🔧 Adding {service} permissions to execution role...")
                try:
                    iam.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
                    print(f"✅ {service} permissions added successfully!")
                except Exception as e:
                    print(f"⚠️  Could not attach {service} policy: {e}")
            else:
                print(f"✅ {service} permissions already attached")
        
        # Add inline policy for additional permissions (Lambda, SSM, BedrockAgentCore)
        inline_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "lambda:InvokeFunction",
                        "ssm:GetParameter",
                        "ssm:GetParameters",
                        "ssm:GetParametersByPath",
                        "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                        "bedrock-agentcore:InvokeAgent",
                        "bedrock-agentcore:RetrieveAndGenerate",
                        "bedrock-agentcore:RetrieveMemoryRecords",
                        "bedrock-agentcore:StoreMemoryRecords"
                    ],
                    "Resource": "*"
                }
            ]
        }
        
        try:
            iam.put_role_policy(
                RoleName=role_name,
                PolicyName="AgentCoreAdditionalPermissions",
                PolicyDocument=json.dumps(inline_policy)
            )
            print("✅ Additional Lambda/SSM permissions added via inline policy")
        except Exception as e:
            print(f"ℹ️  Inline policy may already exist: {e}")
        
        return True
        
    except Exception as e:
        print(f"⚠️  Could not verify/add execution role permissions: {e}")
        print("🔧 Runtime may fail due to permission issues")
        return False


@cli.command()
@click.option('--name', required=True, help='Name for the agent runtime')
def create(name: str):
    """Create and deploy an AgentCore runtime using AgentCore CLI (idempotent).
    
    This command follows the customer-support-assistant reference pattern:
    1. Checks if runtime already exists
    2. Gets execution role from SSM parameters (set by prerequisites)
    3. Uses agentcore configure and agentcore launch commands
    4. Automatically handles the deployment process
    
    Agent name requirements:
    - Must start with a letter
    - Only letters, numbers, and underscores allowed
    - 1-48 characters long
    """
    
    # STEP 1: Check if runtime already exists
    click.echo(f"🔍 Checking if agent runtime '{name}' already exists...")
    try:
        agentcore_control_client = boto3.client("bedrock-agentcore-control", region_name=get_aws_region())
        runtimes = agentcore_control_client.list_agent_runtimes()
        
        for runtime in runtimes.get("agentRuntimes", []):
            if runtime["agentRuntimeName"] == name:
                runtime_arn = runtime["agentRuntimeArn"]
                runtime_id = runtime["agentRuntimeId"]
                click.echo(f"✅ Agent runtime '{name}' already exists")
                click.echo(f"   Runtime ARN: {runtime_arn}")
                click.echo(f"   Runtime ID: {runtime_id}")
                click.echo("ℹ️  Skipping creation - runtime is already deployed")
                
                # Update module3-config.json with existing runtime ARN
                click.echo("📝 Updating module3-config.json with runtime ARN...")
                try:
                    script_dir = Path(__file__).parent
                    stage_root = script_dir.parent.parent
                    config_file = stage_root / "module3-config.json"
                    
                    if config_file.exists():
                        with open(config_file, 'r') as f:
                            config = json.load(f)
                        
                        if 'agentcore_performance' not in config:
                            config['agentcore_performance'] = {}
                        
                        config['agentcore_performance']['runtime_arn'] = runtime_arn
                        
                        with open(config_file, 'w') as f:
                            json.dump(config, f, indent=2)
                        
                        click.echo(f"✅ Updated module3-config.json with runtime ARN")
                    else:
                        click.echo(f"ℹ️  Config file not found: {config_file}")
                        
                except Exception as e:
                    click.echo(f"⚠️  Could not update config file: {e}")
                
                click.echo(f"🎉 Runtime '{name}' is already deployed and ready to use!")
                return
    except Exception as e:
        click.echo(f"⚠️  Could not check for existing runtime: {e}")
        click.echo("   Proceeding with creation attempt...")
    
    # STEP 2: Validate and sanitize agent name
    import re
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{0,47}$', name):
        click.echo("❌ Invalid agent name format!")
        click.echo("✅ Agent name requirements:")
        click.echo("   - Must start with a letter")
        click.echo("   - Only letters, numbers, and underscores allowed")
        click.echo("   - 1-48 characters long")
        click.echo("   - NO hyphens (-) allowed")
        click.echo()
        
        # Suggest a fixed name
        fixed_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if not re.match(r'^[a-zA-Z]', fixed_name):
            fixed_name = 'agent_' + fixed_name
        fixed_name = fixed_name[:48]  # Truncate if too long
        
        click.echo(f"💡 Suggested name: {fixed_name}")
        click.echo(f"💡 Try: python3 scripts/agentcore_agent_runtime.py create --name {fixed_name}")
        sys.exit(1)
    
    # Change to project directory (where main.py is located)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)
    
    click.echo(f"🚀 Creating AgentCore runtime: {name}")
    click.echo(f"📁 Working directory: {project_root}")
    
    # Check required files exist
    required_files = [project_root / "main.py", project_root / "agent_config"]
    for file_path in required_files:
        if not file_path.exists():
            click.echo(f"❌ Required file/directory missing: {file_path}")
            sys.exit(1)
    
    # Ensure SSM permissions before accessing SSM
    ensure_ssm_permissions()
    
    # Get execution role ARN from SSM (set by prerequisites)
    click.echo("🔍 Getting execution role from SSM parameters...")
    role_arn = get_ssm_parameter('/a2a/app/performance/agentcore/gateway_iam_role')
    click.echo(f"📝 Using execution role: {role_arn}")
    
    # Ensure execution role permissions (ECR, SSM, Lambda)
    ensure_execution_role_permissions(role_arn)
    
    # Remove existing config files that might conflict
    config_files = [
        project_root / ".agentcore.yaml",
        project_root / ".bedrock_agentcore.yaml"
    ]
    
    for config_file in config_files:
        if config_file.exists():
            click.echo(f"🗑️  Removing existing {config_file.name}")
            config_file.unlink()
    
    try:
        # Get OAuth parameters from SSM (support both web and machine clients)
        click.echo("🔍 Getting OAuth configuration from SSM (both web and machine clients)...")
        try:
            oauth_discovery_url = get_ssm_parameter('/a2a/app/performance/agentcore/cognito_discovery_url')
            oauth_web_client_id = get_ssm_parameter('/a2a/app/performance/agentcore/web_client_id')
            oauth_machine_client_id = get_ssm_parameter('/a2a/app/performance/agentcore/machine_client_id')
            click.echo(f"📝 OAuth Discovery URL: {oauth_discovery_url}")
            click.echo(f"📝 OAuth Web Client ID: {oauth_web_client_id}")
            click.echo(f"📝 OAuth Machine Client ID: {oauth_machine_client_id}")
        except Exception as e:
            click.echo(f"❌ Could not get OAuth parameters: {e}")
            click.echo("💡 Make sure prerequisites are deployed first: ./scripts/prereq.sh")
            sys.exit(1)
        
        # Configure runtime with AgentCore CLI (basic IAM like reference)
        click.echo("🔧 Configuring AgentCore runtime (basic IAM - reference style)...")
        click.echo("⚙️  Step 1/2: Setting up basic configuration...")
        
        # Sanitize external inputs to prevent command injection
        safe_role_arn = shlex.quote(role_arn)
        safe_name = shlex.quote(name)
        safe_region = shlex.quote(get_aws_region())
        
        # Create OAuth authorizer configuration as JSON
        # NO AUDIENCE field (JWT token doesn't have aud claim) - Based on debug output
        # Use the correct structure expected by Bedrock AgentCore API
        # IMPORTANT: Include BOTH web and machine client IDs to support both authentication flows
        oauth_config = {
            "customJWTAuthorizer": {
                "discoveryUrl": oauth_discovery_url,
                "allowedClients": [oauth_web_client_id, oauth_machine_client_id]
                # Note: allowedAudience field omitted entirely - JWT has no aud claim, only client_id
            }
        }
        oauth_config_json = json.dumps(oauth_config)
        
        configure_cmd = [
            'agentcore', 'configure',
            '--entrypoint', 'main.py',
            '--execution-role', safe_role_arn, 
            '--name', safe_name,
            '--region', safe_region,
            '--non-interactive',  # Use non-interactive mode
            '--authorizer-config', oauth_config_json  # Provide OAuth config as JSON
        ]
        
        click.echo(f"🎯 Configuring WITHOUT audience validation (JWT has no aud claim)")
        
        click.echo("🔧 Configuring with OAuth (non-interactive mode)...")
        click.echo(f"   🔐 OAuth Discovery URL: {oauth_discovery_url}")  
        click.echo(f"   🆔 OAuth Web Client ID: {oauth_web_client_id}")
        click.echo(f"   🆔 OAuth Machine Client ID: {oauth_machine_client_id}")
        click.echo(f"   📋 OAuth Config JSON: {oauth_config_json}")
        click.echo("📋 Configure command: " + " ".join(configure_cmd[:-2]) + " --non-interactive --authorizer-config '<json>'")
        
        # SAFE SUBPROCESS CALL: shell=False and list of pre-validated arguments prevent command injection
        result = subprocess.run(
            configure_cmd,  # nosemgrep: dangerous-subprocess-use-audit - safe list of validated strings with shell=False
            check=False, 
            capture_output=True, 
            text=True, 
            timeout=300,
            shell=False  # Explicitly prevent shell injection
        )
        
        if result.returncode != 0:
            click.echo("❌ Configuration failed")
            if result.stdout:
                click.echo(f"📝 STDOUT:\n{result.stdout}")
            if result.stderr:
                click.echo(f"❌ STDERR:\n{result.stderr}")
            sys.exit(1)
        
        click.echo("✅ Runtime configured successfully")
        if result.stdout:
            # Show relevant parts of configuration output
            lines = result.stdout.split('\n')
            for line in lines:
                if 'Configuration Summary' in line or 'Region:' in line or 'Account:' in line or 'Authorization:' in line:
                    click.echo(f"📋 {line}")
        
        # DON'T overwrite the OAuth config that agentcore configure just created!
        click.echo("✅ Using OAuth configuration from agentcore configure")
        click.echo("📋 Config file left intact with proper OAuth settings")
        
        # Launch runtime with auto-update (handles existing agent)
        click.echo("⚙️  Step 2/2: Launching AgentCore runtime...")
        click.echo("🚀 Using CodeBuild ARM64 deployment (fixes platform mismatch)")
        
        # Try to fix CodeBuild role trust policy proactively (if it exists from previous attempt)
        click.echo("🔧 Checking for CodeBuild role from previous attempts...")
        fix_codebuild_role_trust_policy(get_aws_region())
        
        launch_cmd = [
            'agentcore', 'launch', 
            '--auto-update-on-conflict'  # Handle existing agent
        ]
        
        click.echo("📋 Launch command: " + " ".join(launch_cmd))
        click.echo("⏳ This may take several minutes...")
        click.echo("   🔄 Building ARM64 container in CodeBuild")
        click.echo("   📦 Pushing to ECR repository")
        click.echo("   🚀 Deploying to Bedrock AgentCore")
        
        # Show real-time progress by streaming output
        # SAFE SUBPROCESS CALL: shell=False and list of pre-validated arguments prevent command injection
        process = subprocess.Popen(
            launch_cmd,  # nosemgrep: dangerous-subprocess-use-audit - safe list of validated strings with shell=False
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            shell=False  # Explicitly prevent shell injection
        )
        
        output_lines = []
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                output_lines.append(output.strip())
                # Show progress indicators
                if any(keyword in output for keyword in ['✅', '🔄', '❌', 'QUEUED', 'PROVISIONING', 'BUILD', 'COMPLETED']):
                    click.echo(f"   {output.strip()}")
        
        result_code = process.poll()
        full_output = '\n'.join(output_lines)
        
        # Create result object for compatibility
        class Result:
            def __init__(self, returncode, stdout):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = ''
        
        result = Result(result_code, full_output)
        
        # Check if launch failed due to CodeBuild role trust policy issue
        if result_code != 0 and 'CodeBuild is not authorized to perform: sts:AssumeRole' in full_output:
            click.echo("❌ Launch failed due to CodeBuild role trust policy issue")
            click.echo("🔧 Attempting to fix CodeBuild role trust policy...")
            
            # Fix the trust policy
            if fix_codebuild_role_trust_policy(get_aws_region()):
                click.echo("✅ Trust policy fixed, retrying launch...")
                
                # Retry the launch
                process = subprocess.Popen(
                    launch_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    shell=False
                )
                
                output_lines = []
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        output_lines.append(output.strip())
                        if any(keyword in output for keyword in ['✅', '🔄', '❌', 'QUEUED', 'PROVISIONING', 'BUILD', 'COMPLETED']):
                            click.echo(f"   {output.strip()}")
                
                result_code = process.poll()
                full_output = '\n'.join(output_lines)
                result = Result(result_code, full_output)
            else:
                click.echo("❌ Could not fix trust policy")
        
        # Show the actual launch output
        if result.stdout:
            click.echo(f"📝 Launch output:\n{result.stdout}")
        if result.stderr:
            click.echo(f"⚠️  Launch stderr:\n{result.stderr}")
        
        # Verify the runtime was actually created and capture runtime ARN
        click.echo("🔍 Verifying runtime was created...")
        runtime_arn = None
        try:
            agentcore_control_client = boto3.client("bedrock-agentcore-control", region_name=get_aws_region())
            
            # List runtimes to verify creation
            runtimes = agentcore_control_client.list_agent_runtimes()
            runtime_found = False
            
            for runtime in runtimes.get("agentRuntimes", []):
                if runtime["agentRuntimeName"] == name:
                    runtime_found = True
                    runtime_arn = runtime["agentRuntimeArn"]
                    click.echo(f"✅ Runtime verified in AWS: {runtime_arn}")
                    break
            
            if not runtime_found:
                click.echo(f"❌ Runtime '{name}' not found in AWS!")
                click.echo("🔍 Available runtimes:")
                for runtime in runtimes.get("agentRuntimes", []):
                    click.echo(f"   - {runtime['agentRuntimeName']}")
                
                if not runtimes.get("agentRuntimes"):
                    click.echo("   (No runtimes found)")
                
                click.echo("❌ Deployment may have failed silently!")
                sys.exit(1)
            
        except Exception as e:
            click.echo(f"⚠️  Could not verify runtime creation: {e}")
            runtime_arn = None
        
        # Update module3-config.json with runtime ARN
        if runtime_arn:
            click.echo("📝 Updating module3-config.json with runtime ARN...")
            try:
                # Get the stage root directory (two levels up from scripts)
                stage_root = script_dir.parent.parent
                config_file = stage_root / "module3-config.json"
                
                if config_file.exists():
                    # Load existing config
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                    
                    # Update or create the agentcore_performance section
                    if 'agentcore_performance' not in config:
                        config['agentcore_performance'] = {}
                    
                    config['agentcore_performance']['runtime_arn'] = runtime_arn
                    
                    # Write updated config
                    with open(config_file, 'w') as f:
                        json.dump(config, f, indent=2)
                    
                    click.echo(f"✅ Updated module3-config.json with runtime ARN")
                else:
                    click.echo(f"⚠️  Config file not found: {config_file}")
                    
            except Exception as e:
                click.echo(f"⚠️  Could not update config file: {e}")
        
        click.echo(f"🎉 Runtime '{name}' deployed and verified successfully!")
        click.echo(f"📋 Next steps:")
        click.echo(f"   Test: python test/test_agent.py {name} --prompt 'Hi'")
        
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ AgentCore command failed: {e}")
        if e.stdout:
            click.echo(f"STDOUT: {e.stdout}")
        if e.stderr:
            click.echo(f"STDERR: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        click.echo("❌ AgentCore CLI not found")
        click.echo("💡 Install with: pip install bedrock-agentcore")
        sys.exit(1)


@cli.command()
@click.argument('agent_name', type=str)
@click.option('--dry-run', is_flag=True, help='Show what would be deleted without actually deleting')
def delete(agent_name: str, dry_run: bool):
    """Delete an agent runtime by name from AWS Bedrock AgentCore.
    
    AGENT_NAME: Name of the agent runtime to delete
    """
    
    try:
        agentcore_control_client = boto3.client(
            "bedrock-agentcore-control", region_name=get_aws_region()
        )
    except Exception as e:
        click.echo(f"Error creating AWS client: {e}", err=True)
        sys.exit(1)
    
    agent_id = None
    found = False
    next_token = None
    
    click.echo(f"Searching for agent runtime: {agent_name}")
    
    try:
        while True:
            kwargs = {"maxResults": 20}
            if next_token:
                kwargs["nextToken"] = next_token
                
            agent_runtimes = agentcore_control_client.list_agent_runtimes(**kwargs)
            
            for agent_runtime in agent_runtimes.get("agentRuntimes", []):
                if agent_runtime["agentRuntimeName"] == agent_name:
                    agent_id = agent_runtime["agentRuntimeId"]
                    found = True
                    break
            
            if found:
                break
                
            next_token = agent_runtimes.get("nextToken")
            if not next_token:
                break
                
    except Exception as e:
        click.echo(f"Error listing agent runtimes: {e}", err=True)
        sys.exit(1)
    
    if found:
        click.echo(f"Found agent runtime '{agent_name}' with ID: {agent_id}")
        
        if dry_run:
            click.echo(f"[DRY RUN] Would delete agent runtime: {agent_name}")
            return
        
        try:
            agentcore_control_client.delete_agent_runtime(agentRuntimeId=agent_id)
            click.echo(f"Successfully deleted agent runtime: {agent_name}")
        except Exception as e:
            click.echo(f"Error deleting agent runtime: {e}", err=True)
            sys.exit(1)
    else:
        click.echo(f"Agent runtime '{agent_name}' not found", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
