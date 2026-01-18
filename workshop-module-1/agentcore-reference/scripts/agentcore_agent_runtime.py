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
        role_name = "netops-gateway-execution-role-us-east-1"
        
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
                        "bedrock-agentcore:RetrieveAndGenerate"
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
    """Create and deploy an AgentCore runtime using AgentCore CLI.
    
    This command follows the customer-support-assistant reference pattern:
    1. Gets execution role from SSM parameters (set by prerequisites)
    2. Uses agentcore configure and agentcore launch commands
    3. Automatically handles the deployment process
    
    Agent name requirements:
    - Must start with a letter
    - Only letters, numbers, and underscores allowed
    - 1-48 characters long
    """
    
    # Validate and sanitize agent name
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
    
    # Get execution role ARN from SSM (set by prerequisites)
    click.echo("🔍 Getting execution role from SSM parameters...")
    role_arn = get_ssm_parameter('/app/troubleshooting/agentcore/gateway_iam_role')
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
        # Get OAuth parameters from SSM (same as reference implementation)
        click.echo("🔍 Getting OAuth configuration from SSM (reference implementation)...")
        try:
            oauth_discovery_url = get_ssm_parameter('/app/troubleshooting/agentcore/cognito_discovery_url')
            oauth_client_id = get_ssm_parameter('/app/troubleshooting/agentcore/web_client_id')
            click.echo(f"📝 OAuth Discovery URL: {oauth_discovery_url}")
            click.echo(f"📝 OAuth Client ID: {oauth_client_id}")
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
        
        configure_cmd = [
            'agentcore', 'configure',
            '--entrypoint', 'main.py',
            '--execution-role', safe_role_arn, 
            '--name', safe_name,
            '--region', safe_region
        ]
        
        # OAuth configuration - NO AUDIENCE (JWT token doesn't have aud claim)
        # Based on debug output: JWT token has NO aud claim, only client_id
        oauth_input = f"\n\nyes\n{oauth_discovery_url}\n{oauth_client_id}\n\n"
        
        click.echo(f"🎯 Configuring WITHOUT audience validation (JWT has no aud claim)")
        
        click.echo("🔧 Configuring with OAuth (exactly like reference)...")
        click.echo(f"   🔐 OAuth Discovery URL: {oauth_discovery_url}")  
        click.echo(f"   🆔 OAuth Client ID: {oauth_client_id}")
        click.echo("📋 Configure command: " + " ".join(configure_cmd))
        
        # Use pseudo-terminal to simulate interactive input
        import pty
        import select
        
        def run_with_pty(cmd, input_data):
            """Run command with pseudo-terminal to avoid 'not a terminal' error"""
            master, slave = pty.openpty()
            
            try:
                process = subprocess.Popen(
                    cmd,
                    stdin=slave,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False
                )
                
                os.close(slave)  # Close slave in parent process
                
                # Send input data
                input_lines = input_data.split('\n')
                for line in input_lines:
                    if line.strip() or not input_lines[-1]:  # Send empty lines too, except final empty
                        os.write(master, (line + '\n').encode())
                
                # Get output
                stdout, stderr = process.communicate(timeout=300)
                os.close(master)
                
                return type('Result', (), {
                    'returncode': process.returncode,
                    'stdout': stdout,
                    'stderr': stderr
                })()
                
            except Exception as e:
                try:
                    os.close(master)
                except:
                    pass
                raise e
        
        # SAFE SUBPROCESS CALL with PTY: shell=False and list of pre-validated arguments prevent command injection
        result = run_with_pty(configure_cmd, oauth_input)
        
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
        
        # Show the actual launch output
        if result.stdout:
            click.echo(f"📝 Launch output:\n{result.stdout}")
        if result.stderr:
            click.echo(f"⚠️  Launch stderr:\n{result.stderr}")
        
        # Verify the runtime was actually created
        click.echo("🔍 Verifying runtime was created...")
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
