"""
AWS NetOps Connectivity Lambda Handler
Unified connectivity tool that analyzes network paths and can fix connectivity issues
Combines VPC Reachability Analyzer (check) and Security Group fixes (fix)
Updated: 2025-10-02 - Unified Connectivity Tool
"""
import json
import logging
import os
import socket
from datetime import datetime
from typing import Dict, Any, Optional
import boto3
import time

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Connectivity Tool Configuration
CONNECTIVITY_TOOLS = ['connectivity']
ALL_TOOLS = CONNECTIVITY_TOOLS


def is_aws_service_endpoint(hostname: str) -> bool:
    """Check if hostname is an AWS service endpoint."""
    aws_service_patterns = [
        '.rds.amazonaws.com',
        '.elb.amazonaws.com',
        '.elasticache.amazonaws.com',
        '.redshift.amazonaws.com',
        '.es.amazonaws.com',
        '.opensearch.amazonaws.com',
        '.elasticbeanstalk.com',
        '.cloudfront.net',
        '.s3.amazonaws.com',
        '.execute-api.amazonaws.com'
    ]
    hostname_lower = hostname.lower()
    return any(hostname_lower.endswith(pattern) for pattern in aws_service_patterns)


def resolve_with_standard_dns(hostname: str) -> Optional[str]:
    """Resolve hostname using standard DNS resolution via socket module."""
    try:
        logger.info(f"Resolving {hostname} using standard DNS")
        ip_address = socket.gethostbyname(hostname)
        logger.info(f"Standard DNS resolved {hostname} -> {ip_address}")
        return ip_address
    except socket.gaierror as e:
        logger.warning(f"Standard DNS resolution failed for {hostname}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error in standard DNS resolution for {hostname}: {str(e)}")
        return None


def resolve_dns_from_route53(dns_name: str, region: str = 'us-east-1', visited_names: Optional[list] = None) -> Optional[str]:
    """Resolve DNS name using Route 53 Private Hosted Zones with CNAME chain support."""
    try:
        if visited_names is None:
            visited_names = []
        
        if dns_name in visited_names:
            logger.error(f"Circular CNAME reference detected: {' -> '.join(visited_names)} -> {dns_name}")
            return None
        
        visited_names = visited_names + [dns_name]
        
        if len(visited_names) > 10:
            logger.error(f"CNAME chain too deep (>10): {' -> '.join(visited_names)}")
            return None
        
        route53_client = boto3.client('route53', region_name=region)
        
        logger.info(f"Searching Private Hosted Zones for {dns_name}")
        
        hosted_zones_response = route53_client.list_hosted_zones()
        private_zones = []
        
        for zone in hosted_zones_response['HostedZones']:
            if zone['Config'].get('PrivateZone', False):
                private_zones.append(zone)
        
        if not private_zones:
            logger.warning("No Private Hosted Zones found")
            return None
        
        for zone in private_zones:
            zone_id = zone['Id'].split('/')[-1]
            zone_name = zone['Name'].rstrip('.')
            
            dns_name_normalized = dns_name.lower()
            zone_name_normalized = zone_name.lower()
            
            if (dns_name_normalized.endswith('.' + zone_name_normalized) or 
                dns_name_normalized == zone_name_normalized or
                zone_name_normalized in dns_name_normalized):
                
                try:
                    records_response = route53_client.list_resource_record_sets(HostedZoneId=zone_id)
                    
                    for record_set in records_response['ResourceRecordSets']:
                        record_name = record_set['Name'].rstrip('.')
                        record_type = record_set['Type']
                        
                        if record_name.lower() == dns_name_normalized:
                            if record_type == 'A' and 'ResourceRecords' in record_set and record_set['ResourceRecords']:
                                ip_address = record_set['ResourceRecords'][0]['Value']
                                logger.info(f"Found A record: {dns_name} -> {ip_address}")
                                return ip_address
                            elif record_type == 'CNAME' and 'ResourceRecords' in record_set and record_set['ResourceRecords']:
                                cname_target = record_set['ResourceRecords'][0]['Value'].rstrip('.')
                                logger.info(f"Found CNAME record: {dns_name} -> {cname_target}")
                                
                                if is_aws_service_endpoint(cname_target):
                                    logger.info(f"CNAME target {cname_target} is an AWS service endpoint, using standard DNS")
                                    return resolve_with_standard_dns(cname_target)
                                else:
                                    logger.info(f"CNAME target {cname_target} is not an AWS service, continuing with Route 53 resolution")
                                    return resolve_dns_from_route53(cname_target, region, visited_names)
                            
                except Exception as zone_error:
                    logger.warning(f"Error searching zone {zone_name}: {str(zone_error)}")
                    continue
        
        logger.warning(f"DNS name {dns_name} not found in any Private Hosted Zone")
        return None
        
    except Exception as e:
        logger.error(f"Route 53 DNS resolution error: {str(e)}")
        return None


def resolve_resource_to_instance_id(resource: str, region: str = 'us-east-1') -> Optional[str]:
    """Resolve a resource (hostname or instance ID) to an instance ID. ONLY for EC2 instances, NOT databases."""
    try:
        # If it's already an instance ID, return it
        if resource.startswith('i-') and len(resource) >= 10:
            logger.info(f"Resource {resource} is already an instance ID")
            return resource
        
        # Try to resolve as hostname
        logger.info(f"Attempting to resolve hostname {resource} to instance ID")
        ip_address = resolve_dns_from_route53(resource, region)
        
        if not ip_address:
            logger.warning(f"Could not resolve hostname {resource}")
            return None
        
        logger.info(f"Resolved {resource} to IP {ip_address}, now finding EC2 instance ONLY")
        
        # Find EC2 instance with this IP - ONLY EC2 instances, not ENIs or databases
        ec2_client = boto3.client('ec2', region_name=region)
        instances_response = ec2_client.describe_instances(
            Filters=[
                {
                    'Name': 'private-ip-address',
                    'Values': [ip_address]
                },
                {
                    'Name': 'instance-state-name',
                    'Values': ['pending', 'running', 'shutting-down', 'stopping', 'stopped']
                }
            ]
        )
        
        for reservation in instances_response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                logger.info(f"Found EC2 instance {instance_id} for hostname {resource}")
                return instance_id
        
        logger.warning(f"No EC2 instance found with IP {ip_address} for hostname {resource}")
        return None
        
    except Exception as e:
        logger.error(f"Error resolving resource {resource}: {str(e)}")
        return None


def resolve_resource_to_ip(resource: str, region: str = 'us-east-1') -> Optional[str]:
    """Resolve a resource (hostname or instance ID) to an IP address. ALWAYS returns IP, never ENI ID."""
    try:
        # If it's already an IP address, return it directly
        import re
        ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        if re.match(ip_pattern, resource):
            logger.info(f"Resource {resource} is already an IP address, using directly")
            return resource
        
        # If it's an instance ID, get its IP
        if resource.startswith('i-') and len(resource) >= 10:
            logger.info(f"Resource {resource} is an instance ID, getting its IP")
            ec2_client = boto3.client('ec2', region_name=region)
            instances_response = ec2_client.describe_instances(InstanceIds=[resource])
            
            for reservation in instances_response['Reservations']:
                for instance in reservation['Instances']:
                    ip_address = instance['PrivateIpAddress']
                    logger.info(f"Instance {resource} has IP {ip_address}")
                    return ip_address
            return None
        
        # Try to resolve as hostname - ALWAYS return IP address, never ENI ID
        logger.info(f"Attempting to resolve hostname {resource} to IP address")
        ip_address = resolve_dns_from_route53(resource, region)
        
        if ip_address:
            logger.info(f"Resolved hostname {resource} to IP {ip_address} - USING IP ADDRESS ONLY")
            return ip_address
        
        logger.warning(f"Could not resolve hostname {resource}")
        return None
        
    except Exception as e:
        logger.error(f"Error resolving resource {resource} to IP: {str(e)}")
        return None


def extract_tool_name(context, event: Dict[str, Any]) -> Optional[str]:
    """Extract tool name from Gateway context or event."""
    
    # Try Gateway context first
    if hasattr(context, 'client_context') and context.client_context:
        if hasattr(context.client_context, 'custom') and context.client_context.custom:
            tool_name = context.client_context.custom.get('bedrockAgentCoreToolName')
            if tool_name and '___' in tool_name:
                # Remove namespace prefix (e.g., "connectivity-tool___connectivity" -> "connectivity")
                return tool_name.split('___', 1)[1]
            elif tool_name:
                return tool_name
    
    # Fallback to event-based extraction
    for field in ['tool_name', 'toolName', 'name', 'method', 'action', 'function']:
        if field in event:
            return event[field]
    
    # Default to connectivity since this lambda only handles connectivity
    return 'connectivity'


def run_vpc_reachability_analysis(source_resource: str, destination_resource: str, protocol: str, port: str) -> Dict[str, Any]:
    """Run VPC Reachability Analyzer to check connectivity."""
    try:
        # Create EC2 client
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        
        # Step 1: Resolve resources according to strict rules
        logger.info("Resolving source and destination resources...")
        
        # Source should ALWAYS be an instance ID
        source_instance_id = resolve_resource_to_instance_id(source_resource)
        if not source_instance_id:
            return {
                'success': False,
                'error': f"Could not resolve source resource '{source_resource}' to an instance ID"
            }
        
        # Check if destination is a database (contains 'database' in name OR is an IP address)
        # If it's an IP address, assume it's a database destination since agent resolved it
        import re
        ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        is_ip_address = re.match(ip_pattern, destination_resource)
        is_database_destination = 'database' in destination_resource.lower() or bool(is_ip_address)
        
        logger.info(f"Database destination check: '{destination_resource}' -> is_ip={bool(is_ip_address)}, is_database_destination={is_database_destination}")
        
        if is_database_destination:
            # For database destinations: ALWAYS use IP address
            dest_ip = resolve_resource_to_ip(destination_resource)
            if not dest_ip:
                return {
                    'success': False,
                    'error': f"Could not resolve database destination '{destination_resource}' to IP address"
                }
            dest_instance_id = None
            logger.info(f"Database destination detected - using IP: {dest_ip}")
        else:
            # For non-database destinations: prefer instance ID, fallback to IP
            dest_instance_id = resolve_resource_to_instance_id(destination_resource)
            dest_ip = resolve_resource_to_ip(destination_resource)
            logger.info(f"Non-database destination - instance_id={dest_instance_id}, ip={dest_ip}")
        
        logger.info(f"Resolved source: {source_resource} -> {source_instance_id}")
        logger.info(f"Resolved destination: {destination_resource} -> instance_id={dest_instance_id}, ip={dest_ip}")
        
        # Step 2: Create Network Insights Path with strict configuration
        logger.info("Creating Network Insights Path...")
        
        # Build source ARN
        account_id = boto3.client('sts').get_caller_identity()['Account']
        source_arn = f"arn:aws:ec2:us-east-1:{account_id}:instance/{source_instance_id}"
        
        path_params = {
            'Source': source_arn,
            'Protocol': protocol.lower()
        }
        
        # Configure destination based on type
        if is_database_destination:
            # Database: Use FilterAtSource for additional packet header (no main DestinationIp)
            filter_at_source = {
                'DestinationAddress': dest_ip
            }
            
            # Set port (default to 3306 for databases)
            if port:
                filter_at_source['DestinationPortRange'] = {
                    'FromPort': int(port),
                    'ToPort': int(port)
                }
            else:
                filter_at_source['DestinationPortRange'] = {
                    'FromPort': 3306,
                    'ToPort': 3306
                }
                logger.info("Database destination - defaulting to port 3306")
            
            path_params['FilterAtSource'] = filter_at_source
            logger.info(f"Database destination - using FilterAtSource with DestinationAddress: {dest_ip} and port range")
        else:
            # Non-database: prefer instance ID, fallback to IP
            if dest_instance_id:
                dest_arn = f"arn:aws:ec2:us-east-1:{account_id}:instance/{dest_instance_id}"
                path_params['Destination'] = dest_arn
                logger.info(f"Non-database destination - using Destination instance: {dest_instance_id}")
            elif dest_ip:
                path_params['DestinationIp'] = dest_ip
                logger.info(f"Non-database destination - using DestinationIp: {dest_ip}")
            else:
                return {
                    'success': False,
                    'error': f"Could not resolve destination resource '{destination_resource}' to instance ID or IP address"
                }
            
            # Set port for non-database destinations
            if port:
                path_params['DestinationPort'] = int(port)
        
        logger.info(f"Network Insights Path parameters: {path_params}")
        
        # Create the path
        path_response = ec2_client.create_network_insights_path(**path_params)
        path_id = path_response['NetworkInsightsPath']['NetworkInsightsPathId']
        logger.info(f"Created path: {path_id}")
        
        # Step 2: Start Network Insights Analysis
        logger.info("Starting Network Insights Analysis...")
        try:
            analysis_response = ec2_client.start_network_insights_analysis(NetworkInsightsPathId=path_id)
            analysis_id = analysis_response['NetworkInsightsAnalysis']['NetworkInsightsAnalysisId']
            logger.info(f"Started analysis: {analysis_id}")
        except Exception as start_error:
            logger.error(f"Failed to start analysis: {str(start_error)}")
            # Clean up the path if analysis fails to start
            try:
                ec2_client.delete_network_insights_path(NetworkInsightsPathId=path_id)
            except:
                pass
            return {
                'success': False,
                'error': f"Failed to start VPC Reachability Analysis: {str(start_error)}"
            }
        
        # Step 3: Wait for analysis to complete
        logger.info("Waiting for analysis to complete...")
        max_wait_time = 60  # 1 minute max wait
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            analysis_status = ec2_client.describe_network_insights_analyses(NetworkInsightsAnalysisIds=[analysis_id])
            status = analysis_status['NetworkInsightsAnalyses'][0]['Status']
            
            if status == 'succeeded':
                analysis_result = analysis_status['NetworkInsightsAnalyses'][0]
                logger.info("Analysis completed successfully")
                
                # Parse results
                network_path_found = analysis_result.get('NetworkPathFound', False)
                explanations = analysis_result.get('Explanations', [])
                
                # Keep the analysis for reference - don't auto-delete
                logger.info(f"Analysis retained: {analysis_id}, Path: {path_id}")
                logger.info("Use AWS Console or CLI to clean up analysis and path when no longer needed")
                
                return {
                    'success': True,
                    'network_path_found': network_path_found,
                    'explanations': explanations,
                    'analysis_id': analysis_id,
                    'path_id': path_id
                }
            
            elif status == 'failed':
                error_msg = f"VPC Reachability Analysis failed for path {path_id}"
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
            
            # AWS VPC Reachability Analyzer polling interval - required for service
            analysis_poll_interval = 5
            logger.info(f"Waiting {analysis_poll_interval}s before next status check...")
            # INTENTIONAL DELAY: AWS VPC Reachability Analyzer service requires polling intervals between status checks to prevent API throttling
            time.sleep(analysis_poll_interval)  # nosemgrep: arbitrary-sleep
        
        # Analysis timed out
        return {
            'success': False,
            'error': f"VPC Reachability Analysis timed out after {max_wait_time} seconds"
        }
        
    except Exception as e:
        logger.error(f"VPC Reachability Analyzer error: {str(e)}")
        return {
            'success': False,
            'error': f"VPC Reachability Analyzer Error: {str(e)}"
        }


def apply_connectivity_fix(source_resource: str, destination_resource: str, protocol: str, port: str) -> Dict[str, Any]:
    """Apply least privilege security group rules to fix connectivity issues."""
    try:
        # Create AWS clients
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        
        # Step 1: Resolve resources and get details for least privilege rules
        logger.info("Resolving resources for connectivity fix...")
        
        # Get source instance ID and IP
        source_instance_id = resolve_resource_to_instance_id(source_resource)
        if not source_instance_id:
            return {
                'success': False,
                'error': f"Could not resolve source resource '{source_resource}' to an instance ID for security group fix"
            }
        
        source_instance = ec2_client.describe_instances(InstanceIds=[source_instance_id])['Reservations'][0]['Instances'][0]
        source_private_ip = source_instance['PrivateIpAddress']
        
        # Check if destination is a database (contains 'database' in name OR is an IP address)
        import re
        ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        is_ip_address = re.match(ip_pattern, destination_resource)
        is_database_destination = 'database' in destination_resource.lower() or bool(is_ip_address)
        
        if is_database_destination:
            # For database destinations: find ENI with the IP address to get security groups
            dest_ip = resolve_resource_to_ip(destination_resource)
            if not dest_ip:
                return {
                    'success': False,
                    'error': f"Could not resolve database destination '{destination_resource}' to IP address"
                }
            
            logger.info(f"Database destination detected - finding ENI with IP: {dest_ip}")
            
            # Find ENI with this IP address to get security groups
            eni_response = ec2_client.describe_network_interfaces(
                Filters=[
                    {
                        'Name': 'private-ip-address',
                        'Values': [dest_ip]
                    }
                ]
            )
            
            if not eni_response['NetworkInterfaces']:
                return {
                    'success': False,
                    'error': f"Could not find network interface with IP {dest_ip} for database destination"
                }
            
            # Get security groups from the ENI
            eni = eni_response['NetworkInterfaces'][0]
            dest_security_groups = [sg['GroupId'] for sg in eni['Groups']]
            dest_private_ip = dest_ip
            
            logger.info(f"Found ENI {eni['NetworkInterfaceId']} with security groups: {dest_security_groups}")
        else:
            # For non-database destinations: get instance details
            dest_instance_id = resolve_resource_to_instance_id(destination_resource)
            if not dest_instance_id:
                return {
                    'success': False,
                    'error': f"Could not resolve destination resource '{destination_resource}' to an instance ID"
                }
            
            dest_instance = ec2_client.describe_instances(InstanceIds=[dest_instance_id])['Reservations'][0]['Instances'][0]
            dest_private_ip = dest_instance['PrivateIpAddress']
            dest_security_groups = [sg['GroupId'] for sg in dest_instance['SecurityGroups']]
        
        logger.info(f"Source IP: {source_private_ip}, Destination IP: {dest_private_ip}")
        logger.info(f"Destination Security Groups: {dest_security_groups}")
        
        # Step 2: Apply least privilege security group rule
        logger.info("Applying least privilege security group rule...")
        
        fix_applied = False
        applied_rules = []
        
        for sg_id in dest_security_groups:
            try:
                # Add ingress rule with /32 source IP (least privilege)
                rule_description = f"Connectivity fix: Allow {protocol} {port} from {source_resource}"
                
                if protocol.upper() == 'ICMP':
                    # ICMP rule
                    ec2_client.authorize_security_group_ingress(
                        GroupId=sg_id,
                        IpPermissions=[
                            {
                                'IpProtocol': 'icmp',
                                'FromPort': -1,
                                'ToPort': -1,
                                'IpRanges': [
                                    {
                                        'CidrIp': f'{source_private_ip}/32',
                                        'Description': rule_description
                                    }
                                ]
                            }
                        ]
                    )
                else:
                    # TCP/UDP rule
                    port_num = int(port) if port else 80
                    ec2_client.authorize_security_group_ingress(
                        GroupId=sg_id,
                        IpPermissions=[
                            {
                                'IpProtocol': protocol.lower(),
                                'FromPort': port_num,
                                'ToPort': port_num,
                                'IpRanges': [
                                    {
                                        'CidrIp': f'{source_private_ip}/32',
                                        'Description': rule_description
                                    }
                                ]
                            }
                        ]
                    )
                
                applied_rules.append({
                    'security_group': sg_id,
                    'rule': f'{protocol} {port} from {source_private_ip}/32',
                    'description': rule_description
                })
                fix_applied = True
                logger.info(f"Applied rule to {sg_id}: {protocol} {port} from {source_private_ip}/32")
                
                # Only need to apply to one security group typically
                break
                
            except Exception as rule_error:
                # Check if rule already exists (this is actually success!)
                if "InvalidPermission.Duplicate" in str(rule_error) or "already exists" in str(rule_error):
                    applied_rules.append({
                        'security_group': sg_id,
                        'rule': f'{protocol} {port} from {source_private_ip}/32',
                        'description': f"Rule already exists - {rule_description}"
                    })
                    fix_applied = True
                    logger.info(f"Rule already exists in {sg_id}: {protocol} {port} from {source_private_ip}/32 (this is good!)")
                    break
                else:
                    logger.warning(f"Failed to apply rule to {sg_id}: {rule_error}")
                    # Continue to next security group
                    continue
        
        if not fix_applied:
            return {
                'success': False,
                'error': 'Failed to apply security group rules to any security group'
            }
        
        # Step 3: Wait for AWS to propagate the changes  
        logger.info("Waiting for AWS to propagate security group changes...")
        # Required: AWS security group changes need time to propagate across AZs
        propagation_delay = 5
        logger.info(f"Waiting {propagation_delay}s for AWS security group propagation...")
        # INTENTIONAL DELAY: AWS service requirement - security group changes need time to propagate across availability zones
        time.sleep(propagation_delay)  # nosemgrep: arbitrary-sleep
        
        return {
            'success': True,
            'fix_applied': True,
            'applied_rules': applied_rules
        }
        
    except Exception as e:
        logger.error(f"Connectivity Fix error: {str(e)}")
        return {
            'success': False,
            'error': f"Connectivity Fix Error: {str(e)}"
        }


def handle_connectivity(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle unified connectivity tool - both check and fix functionality."""
    
    try:
        # Extract parameters
        source_resource = event.get('source_resource', '')
        destination_resource = event.get('destination_resource', '')
        protocol = event.get('protocol', 'TCP').upper()
        port = event.get('port', '')
        action = event.get('action', 'check')  # Default to check
        user_query = event.get('query', '')
        session_id = event.get('session_id', '')
        
        logger.info(f"Connectivity Tool - Source: {source_resource}, Dest: {destination_resource}, Protocol: {protocol}, Port: {port}, Action: {action}")
        
        # Validate required parameters
        if not source_resource or not destination_resource:
            return {
                'success': False,
                'error': 'Missing required source_resource or destination_resource parameters',
                'tool': 'connectivity',
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        # Set default port for database connections if not specified
        if not port and 'database' in destination_resource.lower():
            port = '3306'  # MySQL default port
            logger.info(f"No port specified for database destination, defaulting to MySQL port 3306")
        
        # Handle different actions
        if action == 'check':
            # Get resolved values for display
            source_instance_id = resolve_resource_to_instance_id(source_resource)
            dest_ip = resolve_resource_to_ip(destination_resource)
            is_database_destination = 'database' in destination_resource.lower()
            
            # Run connectivity analysis only
            analysis_result = run_vpc_reachability_analysis(source_resource, destination_resource, protocol, port)
            
            if not analysis_result['success']:
                return {
                    'success': False,
                    'error': analysis_result['error'],
                    'tool': 'connectivity',
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
            
            # Build human-readable response
            network_path_found = analysis_result['network_path_found']
            explanations = analysis_result.get('explanations', [])
            
            if network_path_found:
                result_text = f"✅ CONNECTIVITY ANALYSIS RESULTS:\n\n"
                result_text += f"Network path found: YES\n"
                result_text += f"Source: {source_resource}"
                if source_instance_id and source_instance_id != source_resource:
                    result_text += f" (resolved to instance: {source_instance_id})"
                result_text += f"\n"
                result_text += f"Destination: {destination_resource}"
                if dest_ip and dest_ip != destination_resource:
                    result_text += f" (resolved to IP: {dest_ip})"
                result_text += f"\n"
                result_text += f"Protocol: {protocol}\n"
                if port:
                    result_text += f"Port: {port}\n"
                elif is_database_destination:
                    result_text += f"Port: 3306 (MySQL default)\n"
                result_text += f"\nThe network path analysis indicates that connectivity should work between these resources.\n"
                
                # Add configuration details based on destination type
                result_text += f"\n📋 VPC Reachability Analyzer Configuration:\n"
                result_text += f"• Source: Instance ID {source_instance_id}\n"
                
                if is_database_destination:
                    result_text += f"• Destination: IP {dest_ip} (database)\n"
                    result_text += f"• Destination Port: {port if port else '3306'} (MySQL)\n"
                else:
                    result_text += f"• Destination: IP {dest_ip}\n"
                    if port:
                        result_text += f"• Destination Port: {port}\n"
                
                result_text += f"• Protocol: {protocol}\n"
            else:
                result_text = f"❌ CONNECTIVITY ANALYSIS RESULTS:\n\n"
                result_text += f"Network path found: NO\n"
                result_text += f"Source: {source_resource}"
                if source_instance_id and source_instance_id != source_resource:
                    result_text += f" (resolved to instance: {source_instance_id})"
                result_text += f"\n"
                result_text += f"Destination: {destination_resource}"
                if dest_ip and dest_ip != destination_resource:
                    result_text += f" (resolved to IP: {dest_ip})"
                result_text += f"\n"
                result_text += f"Protocol: {protocol}\n"
                if port:
                    result_text += f"Port: {port}\n"
                elif is_database_destination:
                    result_text += f"Port: 3306 (MySQL default)\n"
                result_text += f"\nThe analysis found issues preventing connectivity:\n"
                
                # Add explanations
                if explanations:
                    result_text += "\nDetailed Findings:\n"
                    for i, explanation in enumerate(explanations[:5], 1):  # Limit to 5 explanations
                        direction = explanation.get('Direction', 'Unknown')
                        explanation_code = explanation.get('ExplanationCode', 'No code')
                        result_text += f"{i}. Direction: {direction}, Issue: {explanation_code}\n"
                
                # Add configuration details based on destination type
                result_text += f"\n📋 VPC Reachability Analyzer Configuration:\n"
                result_text += f"• Source: Instance ID {source_instance_id}\n"
                
                if is_database_destination:
                    result_text += f"• Destination: IP {dest_ip} (database)\n"
                    result_text += f"• Destination Port: {port if port else '3306'} (MySQL)\n"
                else:
                    result_text += f"• Destination: IP {dest_ip}\n"
                    if port:
                        result_text += f"• Destination Port: {port}\n"
                
                result_text += f"• Protocol: {protocol}\n"
            
            return {
                'success': True,
                'result': result_text,
                'tool': 'connectivity',
                'action': 'check',
                'network_path_found': network_path_found,
                'analysis_id': analysis_result.get('analysis_id'),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        elif action == 'fix':
            # Apply security group fixes
            fix_result = apply_connectivity_fix(source_resource, destination_resource, protocol, port)
            
            if not fix_result['success']:
                return {
                    'success': False,
                    'error': fix_result['error'],
                    'tool': 'connectivity',
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
            
            # Build fix confirmation response
            applied_rules = fix_result.get('applied_rules', [])
            
            result_text = f"✅ CONNECTIVITY FIX APPLIED SUCCESSFULLY!\n\n"
            result_text += f"Fixed connectivity for:\n"
            result_text += f"• Source: {source_resource}\n"
            result_text += f"• Destination: {destination_resource}\n"
            result_text += f"• Protocol: {protocol}\n"
            if port:
                result_text += f"• Port: {port}\n\n"
            
            result_text += f"Security Group Changes Applied:\n"
            for rule in applied_rules:
                result_text += f"• {rule['security_group']}: {rule['rule']}\n"
            
            result_text += f"\nThe security group rules have been updated. Please run connectivity check again to verify the fix worked."
            
            return {
                'success': True,
                'result': result_text,
                'tool': 'connectivity',
                'action': 'fix',
                'fix_applied': True,
                'applied_rules': applied_rules,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        else:
            return {
                'success': False,
                'error': f"Unknown action: {action}. Supported actions are 'check' and 'fix'",
                'tool': 'connectivity',
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
    except Exception as e:
        logger.error(f"Connectivity tool error: {str(e)}")
        return {
            'success': False,
            'error': f"Connectivity Tool Error: {str(e)}",
            'tool': 'connectivity',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }


def lambda_handler(event, context):
    """
    AWS NetOps Connectivity Lambda Handler
    
    Unified connectivity tool that analyzes network paths using VPC Reachability Analyzer
    and can automatically fix connectivity issues by applying security group rules.
    """
    logger.info("AWS NetOps Connectivity Lambda Handler - START")
    logger.info(f"Event: {json.dumps(event, default=str)}")
    
    try:
        # Extract tool name
        tool_name = extract_tool_name(context, event)
        logger.info(f"Tool: {tool_name}")
        
        if tool_name not in CONNECTIVITY_TOOLS:
            return {
                'success': False,
                'error': f"Unknown tool: {tool_name}. This Lambda only supports: {CONNECTIVITY_TOOLS}",
                'available_tools': CONNECTIVITY_TOOLS,
                'tool': tool_name,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        # Route to connectivity handler
        return handle_connectivity(event)
    
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        return {
            'success': False,
            'error': f"Internal error: {str(e)}",
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    finally:
        logger.info("AWS NetOps Connectivity Lambda Handler - END")
