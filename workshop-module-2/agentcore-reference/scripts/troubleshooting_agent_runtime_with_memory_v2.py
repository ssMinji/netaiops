#!/usr/bin/env python3

import sys
import boto3
import click
import subprocess
import shlex
import os
import json
from pathlib import Path

# Add the scripts directory to Python path for utils import
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

try:
    from utils import get_aws_region
except ImportError:
    # Fallback implementation if utils.py is not available
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


def get_ssm_parameter(parameter_name: str) -> str:
    """Get parameter from SSM Parameter Store"""
    try:
        ssm = boto3.client('ssm', region_name=get_aws_region())
        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        return response['Parameter']['Value']
    except Exception as e:
        click.echo(f"Error retrieving SSM parameter {parameter_name}: {e}", err=True)
        sys.exit(1)


def ensure_ssm_permissions(role_arn: str):
    """Ensure the execution role has SSM permissions"""
    print("🔍 Checking SSM permissions for execution role...")
    
    try:
        iam = boto3.client('iam')
        role_name = role_arn.split('/')[-1]  # Extract role name from ARN
        
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


def ensure_execution_role_permissions(role_arn: str):
    """Ensure the execution role has all required permissions (ECR, SSM, Lambda, Memory)"""
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
        
        # Add inline policy for additional permissions (Lambda, SSM, BedrockAgentCore, Memory)
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
                        "bedrock-agentcore:CreateEvent",
                        "bedrock-agentcore:GetMemory",
                        "bedrock-agentcore:ListMemories",
                        "bedrock-agentcore:ListEvents",
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream"
                    ],
                    "Resource": "*"
                }
            ]
        }
        
        try:
            iam.put_role_policy(
                RoleName=role_name,
                PolicyName="MemoryEnhancedAgentCorePermissions",
                PolicyDocument=json.dumps(inline_policy)
            )
            print("✅ Memory-enhanced permissions added via inline policy")
        except Exception as e:
            print(f"ℹ️  Inline policy may already exist: {e}")
        
        return True
        
    except Exception as e:
        print(f"⚠️  Could not verify/add execution role permissions: {e}")
        print("🔧 Runtime may fail due to permission issues")
        return False


@click.group()
def cli():
    """Memory-Enhanced Troubleshooting Agent Runtime Management"""
    pass


@cli.command()
@click.argument('agent_name', type=str)
def create(agent_name: str):
    """Create and deploy a Memory-Enhanced AgentCore runtime.
    
    This command creates a new agent runtime with memory capabilities:
    1. Uses the same Identity and Gateway as module-1
    2. Adds memory integration for context persistence
    3. Enables cross-session troubleshooting continuity
    
    Agent name requirements:
    - Must start with a letter
    - Only letters, numbers, and underscores allowed
    - 1-48 characters long
    """
    
    # Validate and sanitize agent name
    import re
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{0,47}$', agent_name):
        click.echo("❌ Invalid agent name format!")
        click.echo("✅ Agent name requirements:")
        click.echo("   - Must start with a letter")
        click.echo("   - Only letters, numbers, and underscores allowed")
        click.echo("   - 1-48 characters long")
        click.echo("   - NO hyphens (-) allowed")
        click.echo()
        
        # Suggest a fixed name
        fixed_name = re.sub(r'[^a-zA-Z0-9_]', '_', agent_name)
        if not re.match(r'^[a-zA-Z]', fixed_name):
            fixed_name = 'agent_' + fixed_name
        fixed_name = fixed_name[:48]  # Truncate if too long
        
        click.echo(f"💡 Suggested name: {fixed_name}")
        click.echo(f"💡 Try: python3 scripts/troubleshooting_agent_runtime_with_memory.py create {fixed_name}")
        sys.exit(1)
    
    # Change to project directory (where main.py is located)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)
    
    click.echo(f"🧠 Creating Memory-Enhanced AgentCore runtime: {agent_name}")
    click.echo(f"📁 Working directory: {project_root}")
    
    # Check required files exist
    required_files = [project_root / "main.py", project_root / "agent_config"]
    for file_path in required_files:
        if not file_path.exists():
            click.echo(f"❌ Required file/directory missing: {file_path}")
            sys.exit(1)
    
    # Check memory integration
    click.echo("🧠 Checking memory integration...")
    try:
        memory_id = get_ssm_parameter("/examplecorp/agentcore/memory_id")
        if memory_id:
            click.echo(f"✅ Memory ID found: {memory_id}")
        else:
            click.echo("⚠️  Memory ID not found in SSM")
            click.echo("💡 Run: python3 scripts/setup_examplecorp_memory.py")
            sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Memory check failed: {e}")
        click.echo("💡 Make sure module-2 memory is set up first")
        sys.exit(1)
    
    # Get execution role ARN from SSM (same as module-1)
    click.echo("🔍 Getting execution role from SSM parameters...")
    role_arn = get_ssm_parameter('/app/troubleshooting/agentcore/gateway_iam_role')
    click.echo(f"📝 Using execution role: {role_arn}")
    
    # Ensure SSM permissions for the execution role
    ensure_ssm_permissions(role_arn)
    
    # Ensure execution role permissions (ECR, SSM, Lambda, Memory)
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
        # Get OAuth parameters from SSM (same as module-1)
        click.echo("🔍 Getting OAuth configuration from SSM (same as module-1)...")
        try:
            oauth_discovery_url = get_ssm_parameter('/app/troubleshooting/agentcore/cognito_discovery_url')
            oauth_client_id = get_ssm_parameter('/app/troubleshooting/agentcore/web_client_id')
            click.echo(f"📝 OAuth Discovery URL: {oauth_discovery_url}")
            click.echo(f"📝 OAuth Client ID: {oauth_client_id}")
        except Exception as e:
            click.echo(f"❌ Could not get OAuth parameters: {e}")
            click.echo("💡 Make sure module-1 prerequisites are deployed first")
            sys.exit(1)
        
        # Configure runtime with AgentCore CLI (same infrastructure as module-1)
        click.echo("🔧 Configuring Memory-Enhanced AgentCore runtime...")
        click.echo("⚙️  Creating configuration file directly...")
        
        # Get AWS account info
        try:
            from utils import get_account_id
        except ImportError:
            def get_account_id():
                sts = boto3.client('sts')
                return sts.get_caller_identity()['Account']
        
        account_id = str(get_account_id())
        region = get_aws_region()
        
        # Create .bedrock_agentcore.yaml directly (bypass interactive configure)
        config_content = f"""agents:
  {agent_name}:
    deployment: container
    entrypoint: main.py
    name: {agent_name}
    requirements: requirements.txt
    aws:
      account: "{account_id}"
      region: {region}
      execution_role: {role_arn}
    authorization:
      type: oauth
      oauth_discovery_url: {oauth_discovery_url}
      oauth_client_ids:
        - {oauth_client_id}
default_agent: {agent_name}
"""
        
        config_path = project_root / ".bedrock_agentcore.yaml"
        click.echo(f"📝 Writing config to: {config_path}")
        config_path.write_text(config_content)
        
        click.echo("✅ Configuration file created successfully")
        click.echo(f"📋 Config saved to: {config_path}")
        
        # Create ECR repository first
        click.echo("⚙️  Step 2/4: Creating ECR repository...")
        ecr_repo_name = f"bedrock-agentcore-{agent_name}"
        ecr_uri = None
        
        try:
            ecr = boto3.client('ecr', region_name=get_aws_region())
            response = ecr.create_repository(repositoryName=ecr_repo_name)
            ecr_uri = response['repository']['repositoryUri']
            click.echo(f"✅ Created ECR repository: {ecr_repo_name}")
        except Exception as e:
            if 'RepositoryAlreadyExistsException' in str(e):
                click.echo(f"✅ ECR repository already exists: {ecr_repo_name}")
                # Get existing repository URI
                response = ecr.describe_repositories(repositoryNames=[ecr_repo_name])
                ecr_uri = response['repositories'][0]['repositoryUri']
            else:
                click.echo(f"⚠️  ECR creation warning: {e}")
        
        # Update config with ECR repository URI
        if ecr_uri:
            config_content = f"""agents:
  {agent_name}:
    deployment: container
    entrypoint: main.py
    name: {agent_name}
    requirements: requirements.txt
    aws:
      account: "{account_id}"
      region: {region}
      execution_role: {role_arn}
      ecr_repository: {ecr_uri}
    authorization:
      type: oauth
      oauth_discovery_url: {oauth_discovery_url}
      oauth_client_ids:
        - {oauth_client_id}
default_agent: {agent_name}
"""
            config_path.write_text(config_content)
            click.echo(f"✅ Updated config with ECR URI: {ecr_uri}")
        
        click.echo("🧠 Memory integration will be automatically enabled via SSM parameter")
        
        # Launch runtime with auto-update (handles existing agent)
        click.echo("⚙️  Step 3/4: Launching Memory-Enhanced AgentCore runtime...")
        click.echo("🚀 Using CodeBuild ARM64 deployment with memory capabilities")
        
        launch_cmd = [
            'agentcore', 'launch', 
            '--auto-update-on-conflict'  # Handle existing agent
        ]
        
        click.echo("📋 Launch command: " + " ".join(launch_cmd))
        click.echo("⏳ This may take several minutes...")
        click.echo("   🔄 Building ARM64 container with memory integration")
        click.echo("   📦 Pushing to ECR repository")
        click.echo("   🚀 Deploying to Bedrock AgentCore")
        
        # Show real-time progress by streaming output
        # SAFE SUBPROCESS CALL: shell=False and list of pre-validated arguments prevent command injection
        process = subprocess.Popen(
            launch_cmd,
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
        
        # Show the actual launch output
        if result.stdout:
            click.echo(f"📝 Launch output:\n{result.stdout}")
        if result.stderr:
            click.echo(f"⚠️  Launch stderr:\n{result.stderr}")
        
        # Verify the runtime was actually created
        click.echo("🔍 Verifying memory-enhanced runtime was created...")
        try:
            agentcore_control_client = boto3.client("bedrock-agentcore-control", region_name=get_aws_region())
            
            # List runtimes to verify creation
            runtimes = agentcore_control_client.list_agent_runtimes()
            runtime_found = False
            
            for runtime in runtimes.get("agentRuntimes", []):
                if runtime["agentRuntimeName"] == agent_name:
                    runtime_found = True
                    runtime_arn = runtime["agentRuntimeArn"]
                    click.echo(f"✅ Memory-enhanced runtime verified in AWS: {runtime_arn}")
                    break
            
            if not runtime_found:
                click.echo(f"❌ Runtime '{agent_name}' not found in AWS!")
                click.echo("🔍 Available runtimes:")
                for runtime in runtimes.get("agentRuntimes", []):
                    click.echo(f"   - {runtime['agentRuntimeName']}")
                
                if not runtimes.get("agentRuntimes"):
                    click.echo("   (No runtimes found)")
                
                click.echo("❌ Deployment may have failed silently!")
                sys.exit(1)
            
            # Configure OAuth after deployment
            click.echo("🔐 Configuring OAuth authorization...")
            try:
                runtime_id = runtime_arn.split('/')[-1]
                
                # Get current runtime details
                runtime_response = agentcore_control_client.get_agent_runtime(
                    agentRuntimeId=runtime_id
                )
                
                # Extract required fields from response
                runtime_data = runtime_response
                if 'agentRuntime' in runtime_response:
                    runtime_data = runtime_response['agentRuntime']
                
                # Update with OAuth configuration
                agentcore_control_client.update_agent_runtime(
                    agentRuntimeId=runtime_id,
                    agentRuntimeArtifact=runtime_data['agentRuntimeArtifact'],
                    roleArn=runtime_data['roleArn'],
                    networkConfiguration=runtime_data['networkConfiguration'],
                    authorizerConfiguration={
                        'customJWTAuthorizer': {
                            'discoveryUrl': oauth_discovery_url,
                            'allowedClients': [oauth_client_id]
                        }
                    }
                )
                click.echo("✅ OAuth configuration applied successfully")
            except KeyError as e:
                click.echo(f"⚠️  OAuth configuration error - missing field: {e}")
                click.echo(f"📋 Runtime response keys: {list(runtime_response.keys())}")
                click.echo("💡 You may need to configure OAuth manually")
            except Exception as e:
                click.echo(f"⚠️  OAuth configuration warning: {e}")
                click.echo("💡 You may need to configure OAuth manually")
            
        except Exception as e:
            click.echo(f"⚠️  Could not verify runtime creation: {e}")
        
        click.echo(f"🎉 Memory-Enhanced Runtime '{agent_name}' deployed and verified successfully!")
        click.echo(f"🧠 Memory Integration: ENABLED")
        click.echo(f"📋 Next steps:")
        click.echo(f"   Test: python test/test_agent_with_memory.py {agent_name} --interactive")
        click.echo(f"   Memory capabilities: User permissions, platform knowledge, session context, procedures")
        
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
    """Delete a memory-enhanced agent runtime by name from AWS Bedrock AgentCore.
    
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
    
    click.echo(f"Searching for memory-enhanced agent runtime: {agent_name}")
    
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
        click.echo(f"Found memory-enhanced agent runtime '{agent_name}' with ID: {agent_id}")
        
        if dry_run:
            click.echo(f"[DRY RUN] Would delete memory-enhanced agent runtime: {agent_name}")
            return
        
        try:
            agentcore_control_client.delete_agent_runtime(agentRuntimeId=agent_id)
            click.echo(f"Successfully deleted memory-enhanced agent runtime: {agent_name}")
        except Exception as e:
            click.echo(f"Error deleting agent runtime: {e}", err=True)
            sys.exit(1)
    else:
        click.echo(f"Memory-enhanced agent runtime '{agent_name}' not found", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
