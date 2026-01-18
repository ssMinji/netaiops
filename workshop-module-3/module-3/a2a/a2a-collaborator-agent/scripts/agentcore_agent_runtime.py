#!/usr/bin/env python3

import sys
import boto3
import click
import subprocess
import shlex
import os
import json
import yaml
from pathlib import Path

# Add parent directory to path to import utils
sys.path.append(str(Path(__file__).parent.parent))
from utils import get_ssm_parameter

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


@click.group()
def cli():
    """A2A Host Agent AgentCore Runtime Management"""
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


def update_main_agent_yaml_with_alb_dns():
    """Update main_agent.yaml with ALB DNS values from module3-config.json"""
    click.echo("🔧 Updating main_agent.yaml with ALB DNS values from module3-config.json...")
    
    # Path to module3-config.json (relative to current directory)
    module3_config_path = Path("../../module3-config.json")
    main_agent_yaml_path = Path("main_agent.yaml")
    
    # Check if module3-config.json exists
    if not module3_config_path.exists():
        click.echo(f"❌ module3-config.json not found at {module3_config_path}")
        click.echo("💡 Please ensure the file exists and you're running this script from the correct directory")
        sys.exit(1)
    
    # Check if main_agent.yaml exists
    if not main_agent_yaml_path.exists():
        click.echo(f"❌ main_agent.yaml not found at {main_agent_yaml_path}")
        sys.exit(1)
    
    try:
        # Read module3-config.json
        with open(module3_config_path, 'r') as f:
            module3_config = json.load(f)
        
        # Extract ALB DNS values
        connectivity_alb_dns = module3_config.get('agentcore_troubleshooting', {}).get('alb_dns')
        performance_alb_dns = module3_config.get('agentcore_performance', {}).get('alb_dns')
        
        if not connectivity_alb_dns:
            click.echo("❌ Missing alb_dns in agentcore_troubleshooting section of module3-config.json")
            sys.exit(1)
        
        if not performance_alb_dns:
            click.echo("⚠️  Missing alb_dns in agentcore_performance section of module3-config.json")
            click.echo("💡 This may be expected if performance agent hasn't been deployed yet")
            # We'll use a placeholder or skip this server
            performance_alb_dns = None
        
        click.echo(f"📝 Found connectivity ALB DNS: {connectivity_alb_dns}")
        if performance_alb_dns:
            click.echo(f"📝 Found performance ALB DNS: {performance_alb_dns}")
        
        # Create backup of original main_agent.yaml
        backup_path = main_agent_yaml_path.with_suffix('.yaml.backup')
        if main_agent_yaml_path.exists():
            import shutil
            shutil.copy2(main_agent_yaml_path, backup_path)
            click.echo(f"📋 Created backup: {backup_path}")
        
        # Read current main_agent.yaml
        with open(main_agent_yaml_path, 'r') as f:
            main_agent_config = yaml.safe_load(f)
        
        # Update servers section
        if 'servers' not in main_agent_config:
            main_agent_config['servers'] = []
        
        # Clear existing servers and add updated ones
        main_agent_config['servers'] = []
        
        # Add connectivity agent server
        connectivity_url = f"http://{connectivity_alb_dns}"
        main_agent_config['servers'].append(connectivity_url)
        
        # Add performance agent server if available
        if performance_alb_dns:
            performance_url = f"http://{performance_alb_dns}"
            main_agent_config['servers'].append(performance_url)
        
        # Write updated main_agent.yaml
        with open(main_agent_yaml_path, 'w') as f:
            yaml.dump(main_agent_config, f, default_flow_style=False, sort_keys=False)
        
        click.echo("✅ main_agent.yaml updated successfully with ALB DNS values")
        click.echo("📝 Updated servers:")
        click.echo(f"   - Connectivity Agent: {connectivity_url}")
        if performance_alb_dns:
            click.echo(f"   - Performance Agent: {performance_url}")
        else:
            click.echo("   - Performance Agent: (skipped - ALB DNS not available)")
        
    except json.JSONDecodeError as e:
        click.echo(f"❌ Error parsing module3-config.json: {e}")
        sys.exit(1)
    except yaml.YAMLError as e:
        click.echo(f"❌ Error parsing main_agent.yaml: {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error updating main_agent.yaml: {e}")
        # Restore backup if it exists
        if backup_path.exists():
            import shutil
            shutil.copy2(backup_path, main_agent_yaml_path)
            click.echo("🔄 Restored backup due to error")
        sys.exit(1)


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
@click.option('--name', required=True, help='Name for the A2A host agent runtime')
def create(name: str):
    """Create and deploy an A2A Host Agent AgentCore runtime using AgentCore CLI.
    
    This command creates a runtime for the A2A host agent that coordinates with remote agents.
    
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
    
    # Change to host directory (where agent.py is located)
    script_dir = Path(__file__).parent
    host_dir = script_dir.parent  # Go up from scripts to host directory
    os.chdir(host_dir)
    
    click.echo(f"🚀 Creating A2A Host Agent AgentCore runtime: {name}")
    click.echo(f"📁 Working directory: {host_dir}")
    
    # Check required files exist
    required_files = [host_dir / "main.py", host_dir / "agent.py"]
    for file_path in required_files:
        if not file_path.exists():
            click.echo(f"❌ Required file missing: {file_path}")
            sys.exit(1)
    
    # Update main_agent.yaml with ALB DNS values from module3-config.json
    update_main_agent_yaml_with_alb_dns()
    
    # Ensure SSM permissions before accessing SSM
    ensure_ssm_permissions()
    
    # Get execution role ARN from SSM (set by prerequisites)
    click.echo("🔍 Getting execution role from SSM parameters...")
    role_arn = get_ssm_parameter('/a2a/app/performance/agentcore/gateway_iam_role')
    if not role_arn:
        click.echo("❌ Could not get execution role from SSM")
        click.echo("💡 Make sure prerequisites are deployed first")
        sys.exit(1)
    click.echo(f"📝 Using execution role: {role_arn}")
    
    # Ensure execution role permissions (ECR, SSM, Lambda)
    ensure_execution_role_permissions(role_arn)
    
    # Remove existing config files that might conflict
    config_files = [
        host_dir / ".agentcore.yaml",
        host_dir / ".bedrock_agentcore.yaml"
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
        
        # Configure runtime with AgentCore CLI
        click.echo("🔧 Configuring AgentCore runtime for A2A Host Agent...")
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
            '--entrypoint', 'main.py',  # Standard AgentCore entrypoint
            '--execution-role', safe_role_arn, 
            '--name', safe_name,
            '--region', safe_region,
            '--requirements-file', 'requirements.txt',  # Use detected requirements.txt
            '--authorizer-config', oauth_config_json  # OAuth config as JSON (no shell escaping)
        ]
        
        click.echo(f"🎯 Configuring WITHOUT audience validation (JWT has no aud claim)")
        click.echo("🔧 Configuring with OAuth...")
        click.echo(f"   🔐 OAuth Discovery URL: {oauth_discovery_url}")  
        click.echo(f"   🆔 OAuth Web Client ID: {oauth_web_client_id}")
        click.echo(f"   🆔 OAuth Machine Client ID: {oauth_machine_client_id}")
        click.echo(f"   📋 OAuth Config JSON: {oauth_config_json}")
        click.echo("📋 Configure command: " + " ".join(configure_cmd[:-2]) + " --authorizer-config '<json>'")
        
        # SAFE SUBPROCESS CALL: shell=False and list of pre-validated arguments prevent command injection
        # Provide empty input to skip any prompts (press Enter for defaults)
        result = subprocess.run(
            configure_cmd,
            check=False, 
            capture_output=True, 
            text=True, 
            timeout=300,
            shell=False,
            input='\n\n\n\n\n'  # Provide newlines to accept defaults for any prompts
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
        
        # Launch runtime with auto-update (handles existing agent)
        click.echo("⚙️  Step 2/2: Launching A2A Host Agent AgentCore runtime...")
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
        
        click.echo(f"🎉 A2A Host Agent Runtime '{name}' deployed and verified successfully!")
        click.echo(f"📋 Next steps:")
        click.echo(f"   Test: Use invoke_agent.py to test the host agent")
        
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
