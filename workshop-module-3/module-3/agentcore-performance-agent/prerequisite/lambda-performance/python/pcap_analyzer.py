"""
PCAP Analysis Module using tshark on TrafficMirroringTargetInstance

This module provides deep PCAP analysis capabilities by executing tshark commands
on the TrafficMirroringTargetInstance via AWS Systems Manager (SSM).

Author: Performance Analysis Team
"""

import json
import boto3
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class PCAPAnalyzer:
    """
    PCAP Analyzer that uses tshark on TrafficMirroringTargetInstance for deep packet analysis.
    """
    
    def __init__(self, region: str = 'us-east-1'):
        self.ec2_client = boto3.client('ec2', region_name=region)
        self.s3_client = boto3.client('s3', region_name=region)
        self.ssm_client = boto3.client('ssm', region_name=region)
        self.sts_client = boto3.client('sts', region_name=region)
        self.region = region
    
    def _get_account_id(self) -> str:
        """Get AWS account ID."""
        try:
            response = self.sts_client.get_caller_identity()
            return response['Account']
        except Exception as e:
            logger.error(f"Failed to get account ID: {str(e)}")
            raise
    
    def _find_traffic_mirroring_target_instance(self) -> Optional[str]:
        """
        Find the TrafficMirroringTargetInstance by tag name.
        
        Returns:
            Instance ID if found, None otherwise
        """
        try:
            logger.info("🔍 Searching for TrafficMirroringTargetInstance...")
            
            response = self.ec2_client.describe_instances(
                Filters=[
                    {'Name': 'tag:Name', 'Values': ['*TrafficMirroringTarget*', 'sample-app-TrafficMirroringTarget']},
                    {'Name': 'instance-state-name', 'Values': ['running']}
                ]
            )
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    instance_name = next((tag['Value'] for tag in instance.get('Tags', []) if tag['Key'] == 'Name'), 'Unknown')
                    logger.info(f"✅ Found TrafficMirroringTargetInstance: {instance_id} ({instance_name})")
                    return instance_id
            
            logger.warning("⚠️ No TrafficMirroringTargetInstance found")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error finding TrafficMirroringTargetInstance: {str(e)}")
            return None
    
    def _execute_ssm_command(self, instance_id: str, commands: List[str], timeout: int = 300) -> Dict[str, Any]:
        """
        Execute commands on EC2 instance via SSM.
        
        Args:
            instance_id: EC2 instance ID
            commands: List of shell commands to execute
            timeout: Command timeout in seconds
        
        Returns:
            Dict containing command output and status
        """
        try:
            logger.info(f"🚀 Executing SSM command on instance {instance_id}")
            logger.info(f"📝 Commands: {commands[:100]}...")  # Log first 100 chars
            
            # Send command
            response = self.ssm_client.send_command(
                InstanceIds=[instance_id],
                DocumentName='AWS-RunShellScript',
                Parameters={'commands': commands},
                TimeoutSeconds=timeout
            )
            
            command_id = response['Command']['CommandId']
            logger.info(f"✅ SSM command sent: {command_id}")
            
            # Wait for command completion
            max_wait = timeout
            wait_interval = 5
            elapsed = 0
            
            while elapsed < max_wait:
                time.sleep(wait_interval)
                elapsed += wait_interval
                
                try:
                    result = self.ssm_client.get_command_invocation(
                        CommandId=command_id,
                        InstanceId=instance_id
                    )
                    
                    status = result['Status']
                    logger.info(f"📊 Command status: {status} (elapsed: {elapsed}s)")
                    
                    if status in ['Success', 'Failed', 'Cancelled', 'TimedOut']:
                        return {
                            'status': status,
                            'stdout': result.get('StandardOutputContent', ''),
                            'stderr': result.get('StandardErrorContent', ''),
                            'command_id': command_id
                        }
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error checking command status: {str(e)}")
                    continue
            
            # Timeout
            logger.warning(f"⏰ Command timed out after {max_wait}s")
            return {
                'status': 'TimedOut',
                'stdout': '',
                'stderr': f'Command timed out after {max_wait} seconds',
                'command_id': command_id
            }
            
        except Exception as e:
            logger.error(f"❌ SSM command execution failed: {str(e)}")
            return {
                'status': 'Failed',
                'stdout': '',
                'stderr': str(e),
                'command_id': None
            }
    
    def _analyze_tcp_retransmissions(self, instance_id: str, pcap_path: str) -> Dict[str, Any]:
        """Analyze TCP retransmissions in PCAP file."""
        logger.info(f"🔍 Analyzing TCP retransmissions in {pcap_path}")
        
        command = f"""
        if [ -f "{pcap_path}" ]; then
            echo "File exists, analyzing..."
            tshark -r {pcap_path} -Y "tcp.analysis.retransmission" -T fields -e frame.number -e ip.src -e ip.dst -e tcp.srcport -e tcp.dstport 2>/dev/null | head -100
        else
            echo "ERROR: File not found: {pcap_path}"
            exit 1
        fi
        """
        
        result = self._execute_ssm_command(instance_id, [command], timeout=120)
        
        if result['status'] == 'Success' and result['stdout']:
            lines = [line for line in result['stdout'].strip().split('\n') if line and not line.startswith('ERROR')]
            return {
                'retransmission_count': len(lines),
                'retransmissions': lines[:20],  # First 20 for summary
                'analysis_successful': True
            }
        else:
            return {
                'retransmission_count': 0,
                'retransmissions': [],
                'analysis_successful': False,
                'error': result.get('stderr', 'Unknown error')
            }
    
    def _analyze_connection_issues(self, instance_id: str, pcap_path: str) -> Dict[str, Any]:
        """Analyze connection issues (RST, FIN flags)."""
        logger.info(f"🔍 Analyzing connection issues in {pcap_path}")
        
        command = f"""
        if [ -f "{pcap_path}" ]; then
            tshark -r {pcap_path} -Y "tcp.flags.reset==1 || tcp.flags.fin==1" -T fields -e frame.time -e ip.src -e ip.dst -e tcp.analysis.flags 2>/dev/null | head -100
        else
            echo "ERROR: File not found"
            exit 1
        fi
        """
        
        result = self._execute_ssm_command(instance_id, [command], timeout=120)
        
        if result['status'] == 'Success' and result['stdout']:
            lines = [line for line in result['stdout'].strip().split('\n') if line and not line.startswith('ERROR')]
            return {
                'connection_issue_count': len(lines),
                'issues': lines[:20],
                'analysis_successful': True
            }
        else:
            return {
                'connection_issue_count': 0,
                'issues': [],
                'analysis_successful': False,
                'error': result.get('stderr', 'Unknown error')
            }
    
    def _analyze_performance_stats(self, instance_id: str, pcap_path: str) -> Dict[str, Any]:
        """Get performance statistics."""
        logger.info(f"🔍 Analyzing performance statistics in {pcap_path}")
        
        command = f"""
        if [ -f "{pcap_path}" ]; then
            echo "=== IO Statistics ==="
            tshark -r {pcap_path} -q -z io,stat,1 2>/dev/null | head -20
            echo ""
            echo "=== TCP Conversations ==="
            tshark -r {pcap_path} -q -z conv,tcp 2>/dev/null | head -20
        else
            echo "ERROR: File not found"
            exit 1
        fi
        """
        
        result = self._execute_ssm_command(instance_id, [command], timeout=120)
        
        if result['status'] == 'Success' and result['stdout']:
            return {
                'statistics': result['stdout'],
                'analysis_successful': True
            }
        else:
            return {
                'statistics': '',
                'analysis_successful': False,
                'error': result.get('stderr', 'Unknown error')
            }
    
    def _analyze_high_latency(self, instance_id: str, pcap_path: str) -> Dict[str, Any]:
        """Analyze high latency connections."""
        logger.info(f"🔍 Analyzing high latency in {pcap_path}")
        
        command = f"""
        if [ -f "{pcap_path}" ]; then
            tshark -r {pcap_path} -Y "tcp.time_delta > 0.1" -T fields -e frame.time -e ip.src -e ip.dst -e tcp.time_delta 2>/dev/null | head -100
        else
            echo "ERROR: File not found"
            exit 1
        fi
        """
        
        result = self._execute_ssm_command(instance_id, [command], timeout=120)
        
        if result['status'] == 'Success' and result['stdout']:
            lines = [line for line in result['stdout'].strip().split('\n') if line and not line.startswith('ERROR')]
            return {
                'high_latency_count': len(lines),
                'high_latency_connections': lines[:20],
                'analysis_successful': True
            }
        else:
            return {
                'high_latency_count': 0,
                'high_latency_connections': [],
                'analysis_successful': False,
                'error': result.get('stderr', 'Unknown error')
            }
    
    def _upload_analysis_to_s3(self, s3_bucket: str, analysis_results: Dict[str, Any], pcap_file: str) -> str:
        """Upload analysis results to S3."""
        try:
            # Generate analysis file key
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
            pcap_filename = pcap_file.split('/')[-1].replace('.pcap', '')
            analysis_key = f"analyzed-content/{pcap_filename}-analysis-{timestamp}.json"
            
            logger.info(f"📤 Uploading analysis to s3://{s3_bucket}/{analysis_key}")
            
            self.s3_client.put_object(
                Bucket=s3_bucket,
                Key=analysis_key,
                Body=json.dumps(analysis_results, indent=2, default=str),
                ContentType='application/json'
            )
            
            logger.info(f"✅ Analysis uploaded successfully")
            return analysis_key
            
        except Exception as e:
            logger.error(f"❌ Failed to upload analysis to S3: {str(e)}")
            return None
    
    async def analyze_pcap_with_tshark(
        self,
        pcap_files: Optional[List[str]] = None,
        s3_bucket_name: Optional[str] = None,
        target_instance_id: Optional[str] = None,
        analysis_types: List[str] = ['retransmissions', 'connections', 'performance', 'latency']
    ) -> Dict[str, Any]:
        """
        Perform deep PCAP analysis using tshark on TrafficMirroringTargetInstance.
        
        Args:
            pcap_files: List of PCAP file S3 keys (if None, analyzes recent files)
            s3_bucket_name: S3 bucket name (auto-detected if not provided)
            target_instance_id: Target instance ID (auto-detected if not provided)
            analysis_types: Types of analysis to perform
        
        Returns:
            Dict containing analysis results and summary
        """
        try:
            logger.info("🔧 Starting analyze_pcap_with_tshark")
            
            # Get account ID
            account_id = self._get_account_id()
            
            # Auto-detect S3 bucket
            if not s3_bucket_name:
                s3_bucket_name = f"traffic-mirroring-analysis-{account_id}"
                logger.info(f"🪣 Auto-detected S3 bucket: {s3_bucket_name}")
            
            # Auto-detect target instance
            if not target_instance_id:
                target_instance_id = self._find_traffic_mirroring_target_instance()
                if not target_instance_id:
                    return {
                        'error': 'TrafficMirroringTargetInstance not found or not running',
                        'error_type': 'InstanceNotFound',
                        'status': 'failed',
                        'recommendations': [
                            'Ensure TrafficMirroringTargetInstance is running',
                            'Check instance tags contain "TrafficMirroringTarget"',
                            'Verify instance is in the correct region'
                        ]
                    }
            
            logger.info(f"🎯 Using target instance: {target_instance_id}")
            
            # Get PCAP files if not provided
            if not pcap_files:
                logger.info("📂 Listing recent PCAP files from S3...")
                try:
                    response = self.s3_client.list_objects_v2(
                        Bucket=s3_bucket_name,
                        Prefix='raw-captures/',
                        MaxKeys=10
                    )
                    
                    pcap_files = [
                        obj['Key'] for obj in response.get('Contents', [])
                        if obj['Key'].endswith('.pcap')
                    ]
                    
                    if not pcap_files:
                        return {
                            'error': 'No PCAP files found in S3 bucket',
                            'error_type': 'NoPCAPFiles',
                            'status': 'failed',
                            's3_bucket': s3_bucket_name,
                            'recommendations': [
                                'Verify traffic mirroring is active',
                                'Check PCAP files are being uploaded to S3',
                                'Ensure S3 bucket name is correct'
                            ]
                        }
                    
                    logger.info(f"✅ Found {len(pcap_files)} PCAP files")
                    
                except Exception as e:
                    return {
                        'error': f'Failed to list PCAP files: {str(e)}',
                        'error_type': 'S3ListError',
                        'status': 'failed'
                    }
            
            # Analyze each PCAP file
            analysis_results = []
            
            for pcap_file in pcap_files[:5]:  # Limit to 5 files to avoid timeout
                logger.info(f"📊 Analyzing {pcap_file}")
                
                # Construct path on target instance (S3 is mounted at /mnt/packet-captures via Mountpoint for Amazon S3)
                # Path structure from sample-app.yaml: /mnt/packet-captures/raw-captures/year=YYYY/month=MM/day=DD/instance-{ID}/capture-*.pcap
                pcap_path = f"/mnt/packet-captures/{pcap_file}"
                
                file_analysis = {
                    'pcap_file': pcap_file,
                    'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                    'analyses': {}
                }
                
                # Perform requested analyses
                if 'retransmissions' in analysis_types:
                    file_analysis['analyses']['retransmissions'] = self._analyze_tcp_retransmissions(
                        target_instance_id, pcap_path
                    )
                
                if 'connections' in analysis_types:
                    file_analysis['analyses']['connections'] = self._analyze_connection_issues(
                        target_instance_id, pcap_path
                    )
                
                if 'performance' in analysis_types:
                    file_analysis['analyses']['performance'] = self._analyze_performance_stats(
                        target_instance_id, pcap_path
                    )
                
                if 'latency' in analysis_types:
                    file_analysis['analyses']['latency'] = self._analyze_high_latency(
                        target_instance_id, pcap_path
                    )
                
                # Upload analysis to S3
                analysis_key = self._upload_analysis_to_s3(s3_bucket_name, file_analysis, pcap_file)
                file_analysis['analysis_s3_key'] = analysis_key
                
                analysis_results.append(file_analysis)
            
            # Generate summary
            summary = self._generate_summary(analysis_results)
            
            return {
                's3_bucket': s3_bucket_name,
                'target_instance_id': target_instance_id,
                'region': self.region,
                'account_id': account_id,
                'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                'files_analyzed': len(analysis_results),
                'analysis_results': analysis_results,
                'summary': summary,
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"❌ analyze_pcap_with_tshark failed: {str(e)}")
            logger.error(f"🔍 Exception details:", exc_info=True)
            return {
                'error': str(e),
                'error_type': type(e).__name__,
                'status': 'failed'
            }
    
    def _generate_summary(self, analysis_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary of all analyses."""
        total_retransmissions = 0
        total_connection_issues = 0
        total_high_latency = 0
        critical_issues = []
        recommendations = []
        
        for result in analysis_results:
            analyses = result.get('analyses', {})
            
            # Count retransmissions
            if 'retransmissions' in analyses:
                count = analyses['retransmissions'].get('retransmission_count', 0)
                total_retransmissions += count
                if count > 10:
                    critical_issues.append({
                        'type': 'high_retransmissions',
                        'severity': 'high',
                        'file': result['pcap_file'],
                        'count': count,
                        'description': f'High TCP retransmission rate detected: {count} retransmissions'
                    })
            
            # Count connection issues
            if 'connections' in analyses:
                count = analyses['connections'].get('connection_issue_count', 0)
                total_connection_issues += count
                if count > 5:
                    critical_issues.append({
                        'type': 'connection_resets',
                        'severity': 'medium',
                        'file': result['pcap_file'],
                        'count': count,
                        'description': f'Multiple connection resets/terminations detected: {count} issues'
                    })
            
            # Count high latency
            if 'latency' in analyses:
                count = analyses['latency'].get('high_latency_count', 0)
                total_high_latency += count
                if count > 20:
                    critical_issues.append({
                        'type': 'high_latency',
                        'severity': 'medium',
                        'file': result['pcap_file'],
                        'count': count,
                        'description': f'High latency connections detected: {count} connections >100ms'
                    })
        
        # Generate recommendations
        if total_retransmissions > 50:
            recommendations.append('Investigate network congestion - high retransmission rate detected')
            recommendations.append('Check for packet loss between source and destination')
            recommendations.append('Review MTU settings and network path')
        
        if total_connection_issues > 20:
            recommendations.append('Review application connection handling')
            recommendations.append('Check for firewall or security group issues')
            recommendations.append('Investigate potential application crashes or timeouts')
        
        if total_high_latency > 50:
            recommendations.append('Investigate network latency issues')
            recommendations.append('Check routing and network path optimization')
            recommendations.append('Review application response times')
        
        if not critical_issues:
            recommendations.append('No critical issues detected - network performance appears healthy')
        
        return {
            'total_retransmissions': total_retransmissions,
            'total_connection_issues': total_connection_issues,
            'total_high_latency_connections': total_high_latency,
            'critical_issues': critical_issues,
            'recommendations': recommendations,
            'overall_health': 'critical' if len(critical_issues) > 3 else 'warning' if len(critical_issues) > 0 else 'healthy'
        }
