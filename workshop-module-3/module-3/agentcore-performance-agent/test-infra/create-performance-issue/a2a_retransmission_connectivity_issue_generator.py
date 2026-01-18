#!/usr/bin/env python3
"""
A2A Workshop Retransmission Issue Generator

This script creates retransmission errors by modifying OS TCP settings on the bastion server.
The issues can then be resolved using the A2A collaborator agent working with the performance agent.

The script modifies:
- TCP buffer sizes (severely limits them)
- TCP window scaling (disables it)
- TCP retransmission timeouts (reduces them)

This creates conditions that cause retransmissions visible in Network Flow Monitor.
Traffic path: Bastion (TCP issues here) → RDS Database
"""

import boto3
import time
import logging
import argparse
import sys
import os
import subprocess
from typing import Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class A2ARetransmissionIssueGenerator:
    def __init__(self, region: str = "us-east-1", stack_name: str = "sample-application"):
        self.region = region
        self.stack_name = stack_name
        self.ec2_client = boto3.client('ec2', region_name=region)
        self.ssm_client = boto3.client('ssm', region_name=region)
        self.cf_client = boto3.client('cloudformation', region_name=region)
        
    def get_stack_outputs(self) -> dict:
        """Get CloudFormation stack outputs"""
        try:
            response = self.cf_client.describe_stacks(StackName=self.stack_name)
            outputs = {}
            
            if response['Stacks']:
                stack_outputs = response['Stacks'][0].get('Outputs', [])
                for output in stack_outputs:
                    outputs[output['OutputKey']] = output['OutputValue']
                    
            logger.info(f"Retrieved {len(outputs)} stack outputs from {self.stack_name}")
            return outputs
            
        except Exception as e:
            logger.error(f"Error getting stack outputs: {e}")
            return {}
    
    def find_reporting_server(self) -> str:
        """Find the reporting server instance ID using CloudFormation outputs"""
        try:
            # Get from stack outputs
            stack_outputs = self.get_stack_outputs()
            
            # Try to get instance ID directly from stack outputs
            if 'ReportingInstanceId' in stack_outputs:
                instance_id = stack_outputs['ReportingInstanceId']
                logger.info(f"Found reporting server instance ID from stack outputs: {instance_id}")
                return instance_id
            
            # Fallback: Find reporting server by name tag
            response = self.ec2_client.describe_instances(
                Filters=[
                    {
                        'Name': 'instance-state-name',
                        'Values': ['running']
                    },
                    {
                        'Name': 'tag:Name',
                        'Values': ['RIV-Reporting-Instance']
                    }
                ]
            )
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_name = "Unknown"
                    for tag in instance.get('Tags', []):
                        if tag['Key'] == 'Name':
                            instance_name = tag['Value']
                            break
                    logger.info(f"Found reporting server: {instance_name} ({instance['InstanceId']})")
                    return instance['InstanceId']
            
            logger.error("No reporting server found")
            logger.error("Make sure the CloudFormation stack is deployed with the latest template")
            return None
            
        except Exception as e:
            logger.error(f"Error finding reporting server: {e}")
            return None
    
    def execute_ssm_command(self, instance_id: str, commands: list, timeout: int = 300) -> Tuple[str, str, bool]:
        """Execute commands on instance via SSM (increased timeout to 5 minutes for package installation)"""
        try:
            response = self.ssm_client.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={'commands': commands},
                TimeoutSeconds=timeout
            )
            
            command_id = response['Command']['CommandId']
            logger.info(f"Sent SSM command {command_id} to {instance_id}")
            
            # Wait for completion
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    result = self.ssm_client.get_command_invocation(
                        CommandId=command_id,
                        InstanceId=instance_id
                    )
                    
                    status = result.get('Status')
                    if status in ['Success', 'Failed', 'Cancelled', 'TimedOut']:
                        stdout = result.get('StandardOutputContent', '')
                        stderr = result.get('StandardErrorContent', '')
                        success = status == 'Success'
                        return stdout, stderr, success
                    
                    time.sleep(2)
                    
                except self.ssm_client.exceptions.InvocationDoesNotExist:
                    time.sleep(2)
                    continue
                    
            return '', 'Command timed out', False
            
        except Exception as e:
            logger.error(f"Error executing SSM command: {e}")
            return "", str(e), False
    
    def create_retransmission_issue(self, instance_id: str) -> bool:
        """Create retransmission issue by modifying TCP OS settings on reporting server"""
        
        commands = [
            "#!/bin/bash",
            "echo 'A2A Workshop - Creating retransmission issue on reporting server'",
            "echo 'Modifying TCP settings to cause retransmissions visible in Network Flow Monitor'",
            "echo 'Traffic path: Reporting Server (TCP issues here) → RDS Database'",
            "",
            "",
            "# Create backup of current settings",
            "echo 'Backing up current TCP settings...'",
            "mkdir -p /tmp/tcp_backup",
            "sysctl net.core.rmem_max | cut -d= -f2 | tr -d ' ' > /tmp/tcp_backup/rmem_max.bak",
            "sysctl net.core.wmem_max | cut -d= -f2 | tr -d ' ' > /tmp/tcp_backup/wmem_max.bak",
            "sysctl net.ipv4.tcp_rmem | cut -d= -f2 | tr -d ' ' > /tmp/tcp_backup/tcp_rmem.bak",
            "sysctl net.ipv4.tcp_wmem | cut -d= -f2 | tr -d ' ' > /tmp/tcp_backup/tcp_wmem.bak",
            "sysctl net.ipv4.tcp_window_scaling | cut -d= -f2 | tr -d ' ' > /tmp/tcp_backup/tcp_window_scaling.bak",
            "sysctl net.ipv4.tcp_retries2 | cut -d= -f2 | tr -d ' ' > /tmp/tcp_backup/tcp_retries2.bak",
            "",
            "echo 'Current settings backed up to /tmp/tcp_backup/'",
            "",
            "# Apply EXTREMELY problematic TCP settings that will cause retransmissions even with light traffic",
            "echo 'Applying EXTREMELY problematic TCP settings...'",
            "",
            "# EXTREMELY limit TCP receive and send buffer sizes",
            "# Note: Using 4096 as minimum accepted by kernel (2048 gets rejected)",
            "sudo sysctl -w net.core.rmem_max=4096",
            "sudo sysctl -w net.core.wmem_max=4096",
            "sudo sysctl -w net.ipv4.tcp_rmem='512 1024 4096'",
            "sudo sysctl -w net.ipv4.tcp_wmem='512 1024 4096'",
            "",
            "# Disable TCP window scaling (causes performance issues)",
            "sudo sysctl -w net.ipv4.tcp_window_scaling=0",
            "",
            "# VERY aggressive retransmission settings (causes frequent retransmissions)",
            "sudo sysctl -w net.ipv4.tcp_retries2=1",
            "sudo sysctl -w net.ipv4.tcp_syn_retries=1",
            "",
            "# VERY aggressive timeouts (causes premature retransmissions)",
            "sudo sysctl -w net.ipv4.tcp_fin_timeout=3",
            "sudo sysctl -w net.ipv4.tcp_keepalive_time=10",
            "sudo sysctl -w net.ipv4.tcp_keepalive_intvl=3",
            "sudo sysctl -w net.ipv4.tcp_keepalive_probes=2",
            "",
            "# Reduce RTO (Retransmission Timeout) settings to trigger faster retransmissions",
            "sudo sysctl -w net.ipv4.tcp_rto_min=20",
            "",
            "# Disable TCP timestamps to make retransmissions more likely",
            "sudo sysctl -w net.ipv4.tcp_timestamps=0",
            "",
            "# Reduce TCP memory pressure thresholds",
            "sudo sysctl -w net.ipv4.tcp_mem='512 1024 4096'",
            "",
            "# Add packet loss simulation using tc (traffic control)",
            "echo 'Adding 5% packet loss to increase retransmissions...'",
            "# Check if tc is available, install if needed",
            "if ! command -v tc &> /dev/null; then",
            "    echo 'Installing iproute-tc...'",
            "    sudo yum install -y iproute-tc 2>&1 || sudo dnf install -y iproute-tc 2>&1",
            "fi",
            "",
            "# Get the primary network interface",
            "PRIMARY_IFACE=$(ip route | grep default | awk '{print $5}' | head -n1)",
            "echo \"Primary interface: $PRIMARY_IFACE\"",
            "",
            "# Remove any existing qdisc",
            "sudo tc qdisc del dev $PRIMARY_IFACE root 2>/dev/null || true",
            "",
            "# Add packet loss (5%) and delay (50ms) to simulate poor network conditions",
            "sudo tc qdisc add dev $PRIMARY_IFACE root netem loss 5% delay 50ms 20ms",
            "echo 'Network impairment added: 5% packet loss, 50ms±20ms delay'",
            "",
            "# Give sysctl changes a moment to fully apply",
            "sleep 1",
            "",
            "echo 'Problematic TCP settings applied successfully!'",
            "echo ''",
            "echo 'Current problematic settings:'",
            "echo '  TCP receive buffer max: '$(sudo sysctl -n net.core.rmem_max)",
            "echo '  TCP send buffer max: '$(sudo sysctl -n net.core.wmem_max)",
            "echo '  TCP receive memory: '$(sudo sysctl -n net.ipv4.tcp_rmem)",
            "echo '  TCP send memory: '$(sudo sysctl -n net.ipv4.tcp_wmem)",
            "echo '  TCP window scaling: '$(sudo sysctl -n net.ipv4.tcp_window_scaling)",
            "echo '  TCP retries: '$(sudo sysctl -n net.ipv4.tcp_retries2)",
            "",
            "echo 'ISSUE CREATED: TCP settings configured to cause retransmissions on REPORTING SERVER'",
            "echo 'These settings will cause:'",
            "echo '  - Small buffer sizes leading to buffer overflows'",
            "echo '  - Disabled window scaling reducing throughput'",
            "echo '  - Aggressive timeouts causing premature retransmissions'",
            "echo ''",
            "echo 'Network traffic FROM reporting server will now experience retransmissions'",
            "echo 'Traffic path: Reporting Server (TCP issues) → RDS Database'",
            "echo 'Use the A2A collaborator agent to diagnose and fix this issue'"
        ]
        
        logger.info("Creating retransmission issue on reporting server...")
        stdout, stderr, success = self.execute_ssm_command(instance_id, commands)
        
        if success:
            logger.info("✅ Retransmission issue created successfully")
            logger.info("TCP settings have been modified to cause retransmissions")
            logger.info("")
            logger.info("=" * 70)
            logger.info("UPDATED TCP SETTINGS ON BASTION SERVER")
            logger.info("=" * 70)
            if stdout:
                # Print the full output to show all settings
                logger.info(stdout)
            logger.info("=" * 70)
        else:
            logger.error("❌ Failed to create retransmission issue")
            if stderr:
                logger.error("Error: " + stderr)
            
        return success
    
    def fix_retransmission_issue(self, instance_id: str) -> bool:
        """Fix the retransmission issue by restoring proper TCP OS settings AND removing network impairment"""
        
        commands = [
            "#!/bin/bash",
            "echo 'A2A Workshop - Fixing retransmission issue on reporting server'",
            "echo 'Restoring proper TCP settings and removing network impairment...'",
            "",
            "# CRITICAL: Remove tc qdisc network impairment (packet loss and delay)",
            "echo 'Removing network impairment (tc qdisc)...'",
            "PRIMARY_IFACE=$(ip route | grep default | awk '{print $5}' | head -n1)",
            "echo \"Primary interface: $PRIMARY_IFACE\"",
            "",
            "# Remove any existing qdisc (this removes the 5% packet loss and 50ms delay)",
            "sudo tc qdisc del dev $PRIMARY_IFACE root 2>/dev/null && echo 'Network impairment removed successfully' || echo 'No network impairment found (already clean)'",
            "",
            "# Verify qdisc is removed",
            "echo 'Current qdisc status:'",
            "sudo tc qdisc show dev $PRIMARY_IFACE",
            "",
            "# Restore optimal TCP buffer sizes",
            "echo 'Restoring optimal TCP buffer sizes...'",
            "sudo sysctl -w net.core.rmem_max=134217728",
            "sudo sysctl -w net.core.wmem_max=134217728",
            "sudo sysctl -w net.ipv4.tcp_rmem='4096 87380 134217728'",
            "sudo sysctl -w net.ipv4.tcp_wmem='4096 16384 134217728'",
            "",
            "# Re-enable TCP window scaling",
            "sudo sysctl -w net.ipv4.tcp_window_scaling=1",
            "",
            "# Restore proper TCP retransmission settings",
            "sudo sysctl -w net.ipv4.tcp_retries2=15",
            "sudo sysctl -w net.ipv4.tcp_syn_retries=6",
            "",
            "# Restore proper TCP timeouts",
            "sudo sysctl -w net.ipv4.tcp_fin_timeout=60",
            "sudo sysctl -w net.ipv4.tcp_keepalive_time=7200",
            "sudo sysctl -w net.ipv4.tcp_keepalive_intvl=75",
            "sudo sysctl -w net.ipv4.tcp_keepalive_probes=9",
            "",
            "# Restore proper RTO settings",
            "sudo sysctl -w net.ipv4.tcp_rto_min=200",
            "",
            "# Re-enable TCP timestamps",
            "sudo sysctl -w net.ipv4.tcp_timestamps=1",
            "",
            "# Restore TCP memory pressure thresholds",
            "sudo sysctl -w net.ipv4.tcp_mem='94500000 126000000 189000000'",
            "",
            "echo 'Optimal TCP settings restored successfully!'",
            "echo ''",
            "echo 'Current restored settings:'",
            "echo '  TCP receive buffer max: '$(sysctl -n net.core.rmem_max)",
            "echo '  TCP send buffer max: '$(sysctl -n net.core.wmem_max)",
            "echo '  TCP receive memory: '$(sysctl -n net.ipv4.tcp_rmem)",
            "echo '  TCP send memory: '$(sysctl -n net.ipv4.tcp_wmem)",
            "echo '  TCP window scaling: '$(sysctl -n net.ipv4.tcp_window_scaling)",
            "echo '  TCP retries: '$(sysctl -n net.ipv4.tcp_retries2)",
            "echo '  TCP timestamps: '$(sysctl -n net.ipv4.tcp_timestamps)",
            "",
            "echo 'ISSUE FIXED: TCP settings restored to optimal values on REPORTING SERVER'",
            "echo 'Network impairment (packet loss and delay) removed'",
            "echo 'Network connectivity from reporting server should now work properly'",
            "echo 'Traffic path: Reporting Server (TCP fixed, no impairment) → RDS Database'",
            "echo 'Retransmissions should be eliminated'"
        ]
        
        logger.info("Fixing retransmission issue on reporting server...")
        stdout, stderr, success = self.execute_ssm_command(instance_id, commands)
        
        if success:
            logger.info("✅ Retransmission issue fixed successfully")
            logger.info("TCP settings have been restored to optimal values")
            if stdout:
                logger.info("Output: " + stdout[-800:] if len(stdout) > 800 else stdout)
        else:
            logger.error("❌ Failed to fix retransmission issue")
            if stderr:
                logger.error("Error: " + stderr)
            
        return success
    
    def run_support_ticket_creation(self) -> bool:
        """Run the create-support-ticket.py script"""
        try:
            # Get the directory where this script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            support_ticket_script = os.path.join(script_dir, 'create-support-ticket.py')
            
            # Check if the support ticket script exists
            if not os.path.exists(support_ticket_script):
                logger.error(f"❌ Support ticket script not found: {support_ticket_script}")
                return False
            
            logger.info("🎫 Creating support ticket...")
            logger.info("=" * 60)
            
            # Run the support ticket creation script
            result = subprocess.run(
                [sys.executable, support_ticket_script],
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )
            
            # Log the output
            if result.stdout:
                logger.info("Support ticket script output:")
                logger.info(result.stdout)
            
            if result.stderr:
                logger.warning("Support ticket script warnings/errors:")
                logger.warning(result.stderr)
            
            if result.returncode == 0:
                logger.info("✅ Support ticket creation completed successfully")
                return True
            else:
                logger.error(f"❌ Support ticket creation failed with return code: {result.returncode}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("❌ Support ticket creation timed out")
            return False
        except Exception as e:
            logger.error(f"❌ Error running support ticket creation: {e}")
            return False

    def run_break_connectivity_script(self) -> bool:
        """Download and run the module-3-break-connectivity.py script"""
        try:
            logger.info("🔗 Downloading and running break connectivity script...")
            logger.info("=" * 60)
            
            # Get the current directory where this script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            
            # URL for the break connectivity script
            script_url = "https://ws-assets-prod-iad-r-iad-ed304a55c2ca1aee.s3.us-east-1.amazonaws.com/175c4803-9b26-4229-a39d-16d9ebdf4aab/break-scripts/module-3-break-connectivity.py"
            script_filename = "module-3-break-connectivity.py"
            script_path = os.path.join(script_dir, script_filename)
            
            # Download the script using curl
            logger.info(f"Downloading script from: {script_url}")
            curl_result = subprocess.run(
                ["curl", script_url, "--output", script_path],
                capture_output=True,
                text=True,
                timeout=60  # 1 minute timeout for download
            )
            
            if curl_result.returncode != 0:
                logger.error(f"❌ Failed to download script with curl: {curl_result.stderr}")
                return False
            
            # Check if the file was downloaded successfully
            if not os.path.exists(script_path):
                logger.error(f"❌ Downloaded script not found: {script_path}")
                return False
            
            logger.info(f"✅ Script downloaded successfully to: {script_path}")
            
            # Run the downloaded script using python3
            logger.info("Executing break connectivity script...")
            python_result = subprocess.run(
                ["python3", script_path],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for execution
            )
            
            # Log the output
            if python_result.stdout:
                logger.info("Break connectivity script output:")
                logger.info(python_result.stdout)
            
            if python_result.stderr:
                logger.warning("Break connectivity script warnings/errors:")
                logger.warning(python_result.stderr)
            
            if python_result.returncode == 0:
                logger.info("✅ Break connectivity script execution completed successfully")
                return True
            else:
                logger.error(f"❌ Break connectivity script execution failed with return code: {python_result.returncode}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("❌ Break connectivity script operation timed out")
            return False
        except Exception as e:
            logger.error(f"❌ Error running break connectivity script: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(
        description="A2A Workshop Retransmission Issue Generator - Create/Fix TCP retransmission issues"
    )
    parser.add_argument(
        '--action',
        choices=['create', 'fix'],
        required=True,
        help='Action to perform: create retransmission issue or fix issue'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    
    args = parser.parse_args()
    
    generator = A2ARetransmissionIssueGenerator(region=args.region)
    
    # Find reporting server
    instance_id = generator.find_reporting_server()
    if not instance_id:
        logger.error("❌ Could not find reporting server instance")
        sys.exit(1)
    
    try:
        if args.action == 'create':
            logger.info("🔧 Creating retransmission issue for A2A workshop testing...")
            success = generator.create_retransmission_issue(instance_id)
            
            if success:
                logger.info("✅ Retransmission issue created successfully!")
                logger.info("📋 Next steps:")
                logger.info("1. Traffic from reporting server to RDS will experience retransmissions")
                logger.info("2. Traffic path: Reporting Server (TCP issues) → RDS Database")
                logger.info("3. Check Network Flow Monitor for retransmission metrics")
                logger.info("4. Use A2A collaborator agent to diagnose and fix the issue")
                logger.info("5. Example prompt: 'I'm experiencing network performance issues from reporting server to RDS'")
                
                # Run support ticket creation after successful issue creation
                logger.info("\n" + "=" * 60)
                logger.info("CREATING SUPPORT TICKET")
                logger.info("=" * 60)
                ticket_success = generator.run_support_ticket_creation()
                
                # Run break connectivity script after support ticket creation
                logger.info("\n" + "=" * 60)
                logger.info("RUNNING BREAK CONNECTIVITY SCRIPT")
                logger.info("=" * 60)
                break_connectivity_success = generator.run_break_connectivity_script()
                
                # Report final status
                logger.info("\n" + "=" * 60)
                logger.info("FINAL WORKFLOW STATUS")
                logger.info("=" * 60)
                
                if ticket_success and break_connectivity_success:
                    logger.info("✅ Complete workflow finished successfully!")
                    logger.info("   - Retransmission issue: ✅ Created")
                    logger.info("   - Support ticket: ✅ Created")
                    logger.info("   - Break connectivity script: ✅ Executed")
                elif ticket_success and not break_connectivity_success:
                    logger.warning("⚠️ Workflow partially completed")
                    logger.info("   - Retransmission issue: ✅ Created")
                    logger.info("   - Support ticket: ✅ Created")
                    logger.info("   - Break connectivity script: ❌ Failed")
                elif not ticket_success and break_connectivity_success:
                    logger.warning("⚠️ Workflow partially completed")
                    logger.info("   - Retransmission issue: ✅ Created")
                    logger.info("   - Support ticket: ❌ Failed")
                    logger.info("   - Break connectivity script: ✅ Executed")
                else:
                    logger.warning("⚠️ Retransmission issue created but additional steps failed")
                    logger.info("   - Retransmission issue: ✅ Created")
                    logger.info("   - Support ticket: ❌ Failed")
                    logger.info("   - Break connectivity script: ❌ Failed")
                
                sys.exit(0)
            else:
                logger.error("❌ Failed to create retransmission issue")
                sys.exit(1)
                
        elif args.action == 'fix':
            logger.info("🔧 Fixing retransmission issue...")
            success = generator.fix_retransmission_issue(instance_id)
            
            if success:
                logger.info("✅ Retransmission issue fixed successfully!")
                logger.info("📋 Network performance from reporting server should now be optimal")
                sys.exit(0)
            else:
                logger.error("❌ Failed to fix retransmission issue")
                sys.exit(1)
                
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
