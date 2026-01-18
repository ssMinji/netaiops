"""
AWS NetOps DNS Resolution Lambda Handler
Resolves DNS names from Route 53 Private Hosted Zones to find corresponding EC2 instances and ENIs
Updated: 2025-01-19 - DNS Resolution Focus
"""
import json
import logging
import os
import socket
from datetime import datetime
from typing import Dict, Any, Optional, List

import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DNS Tool Configuration
DNS_TOOLS = ['dns-resolve']
ALL_TOOLS = DNS_TOOLS


def is_aws_service_endpoint(hostname: str) -> bool:
    """
    Check if hostname is an AWS service endpoint that should be resolved via standard DNS.
    
    Args:
        hostname: The hostname to check
        
    Returns:
        True if it's an AWS service endpoint, False otherwise
    """
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
    """
    Resolve hostname using standard DNS resolution via socket module.
    
    Args:
        hostname: The hostname to resolve
        
    Returns:
        IP address if found, None otherwise
    """
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


def extract_tool_name(context, event: Dict[str, Any]) -> Optional[str]:
    """Extract tool name from Gateway context or event."""
    
    # Try Gateway context first
    if hasattr(context, 'client_context') and context.client_context:
        if hasattr(context.client_context, 'custom') and context.client_context.custom:
            tool_name = context.client_context.custom.get('bedrockAgentCoreToolName')
            if tool_name and '___' in tool_name:
                # Remove namespace prefix (e.g., "aws-tools___dns-resolve" -> "dns-resolve")
                return tool_name.split('___', 1)[1]
            elif tool_name:
                return tool_name
    
    # Fallback to event-based extraction
    for field in ['tool_name', 'toolName', 'name', 'method', 'action', 'function']:
        if field in event:
            return event[field]
    
    # Default to dns-resolve since this lambda only handles DNS
    return 'dns-resolve'


def resolve_dns_from_route53(dns_name: str, region: str = 'us-east-1', visited_names: Optional[List[str]] = None) -> Optional[str]:
    """
    Resolve DNS name using Route 53 Private Hosted Zones with CNAME chain support.
    
    Args:
        dns_name: The DNS name to resolve (e.g., app-frontend.examplecorp.com)
        region: AWS region to search in
        visited_names: List of already visited DNS names to prevent infinite loops
        
    Returns:
        IP address if found, None otherwise
    """
    try:
        # Initialize visited names list for cycle detection
        if visited_names is None:
            visited_names = []
        
        # Check for circular CNAME references
        if dns_name in visited_names:
            logger.error(f"Circular CNAME reference detected: {' -> '.join(visited_names)} -> {dns_name}")
            return None
        
        # Add current DNS name to visited list
        visited_names = visited_names + [dns_name]
        
        # Limit CNAME chain depth to prevent excessive recursion
        if len(visited_names) > 10:
            logger.error(f"CNAME chain too deep (>10): {' -> '.join(visited_names)}")
            return None
        
        route53_client = boto3.client('route53', region_name=region)
        
        # Get all Private Hosted Zones
        logger.info(f"Searching Private Hosted Zones for {dns_name} (chain: {' -> '.join(visited_names)})")
        
        # List all hosted zones and filter for private ones
        hosted_zones_response = route53_client.list_hosted_zones()
        private_zones = []
        
        for zone in hosted_zones_response['HostedZones']:
            if zone['Config'].get('PrivateZone', False):
                private_zones.append(zone)
                logger.info(f"Found private zone: {zone['Name']} (ID: {zone['Id']})")
        
        if not private_zones:
            logger.warning("No Private Hosted Zones found")
            return None
        
        # Search each private zone for the DNS record
        for zone in private_zones:
            zone_id = zone['Id'].split('/')[-1]  # Remove '/hostedzone/' prefix
            zone_name = zone['Name'].rstrip('.')  # Remove trailing dot
            
            # Check if the DNS name could belong to this zone
            # Improved zone matching logic
            dns_name_normalized = dns_name.lower()
            zone_name_normalized = zone_name.lower()
            
            if (dns_name_normalized.endswith('.' + zone_name_normalized) or 
                dns_name_normalized == zone_name_normalized or
                zone_name_normalized in dns_name_normalized):
                
                logger.info(f"Searching zone {zone_name} for record {dns_name}")
                
                try:
                    # List resource record sets in this zone
                    records_response = route53_client.list_resource_record_sets(
                        HostedZoneId=zone_id
                    )
                    
                    for record_set in records_response['ResourceRecordSets']:
                        record_name = record_set['Name'].rstrip('.')  # Remove trailing dot
                        record_type = record_set['Type']
                        
                        # Case-insensitive comparison for DNS names
                        if record_name.lower() == dns_name_normalized:
                            if record_type == 'A' and 'ResourceRecords' in record_set and record_set['ResourceRecords']:
                                ip_address = record_set['ResourceRecords'][0]['Value']
                                logger.info(f"Found A record: {dns_name} -> {ip_address} in zone {zone_name}")
                                return ip_address
                            elif record_type == 'CNAME' and 'ResourceRecords' in record_set and record_set['ResourceRecords']:
                                cname_target = record_set['ResourceRecords'][0]['Value'].rstrip('.')
                                logger.info(f"Found CNAME record: {dns_name} -> {cname_target} in zone {zone_name}")
                                
                                # Check if CNAME target is an AWS service endpoint
                                if is_aws_service_endpoint(cname_target):
                                    logger.info(f"CNAME target {cname_target} is an AWS service endpoint, using standard DNS")
                                    return resolve_with_standard_dns(cname_target)
                                else:
                                    # Recursively resolve the CNAME target with cycle detection
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


def find_aws_resources_by_ip(ip_address: str, region: str = 'us-east-1') -> List[Dict[str, Any]]:
    """
    Find EC2 instances and ENIs that have the specified private IP address.
    
    Args:
        ip_address: The private IP address to search for
        region: AWS region to search in
        
    Returns:
        List of found resources with their details
    """
    try:
        ec2_client = boto3.client('ec2', region_name=region)
        found_resources = []
        
        logger.info(f"Searching for AWS resources with IP {ip_address}")
        
        # Search EC2 instances
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
        
        # Process EC2 instances
        for reservation in instances_response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                instance_name = 'N/A'
                
                # Get instance name from tags
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        instance_name = tag['Value']
                        break
                
                found_resources.append({
                    'type': 'EC2 Instance',
                    'id': instance_id,
                    'name': instance_name,
                    'private_ip': instance['PrivateIpAddress'],
                    'state': instance['State']['Name'],
                    'vpc_id': instance.get('VpcId', 'N/A'),
                    'subnet_id': instance.get('SubnetId', 'N/A'),
                    'instance_type': instance.get('InstanceType', 'N/A'),
                    'availability_zone': instance.get('Placement', {}).get('AvailabilityZone', 'N/A')
                })
                logger.info(f"Found EC2 instance: {instance_id} ({instance_name})")
        
        # Search Network Interfaces (ENIs)
        eni_response = ec2_client.describe_network_interfaces(
            Filters=[
                {
                    'Name': 'private-ip-address',
                    'Values': [ip_address]
                }
            ]
        )
        
        # Process Network Interfaces
        for eni in eni_response['NetworkInterfaces']:
            eni_id = eni['NetworkInterfaceId']
            eni_description = eni.get('Description', 'N/A')
            attached_instance = eni.get('Attachment', {}).get('InstanceId', 'N/A')
            interface_type = eni.get('InterfaceType', 'interface')
            
            found_resources.append({
                'type': 'Network Interface (ENI)',
                'id': eni_id,
                'name': eni_description,
                'private_ip': eni['PrivateIpAddress'],
                'state': eni['Status'],
                'vpc_id': eni.get('VpcId', 'N/A'),
                'subnet_id': eni.get('SubnetId', 'N/A'),
                'attached_instance': attached_instance,
                'interface_type': interface_type
            })
            logger.info(f"Found ENI: {eni_id} ({eni_description})")
        
        return found_resources
        
    except Exception as e:
        logger.error(f"Error finding AWS resources by IP: {str(e)}")
        return []


def handle_dns_resolve(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle DNS resolution from Route 53 Private Hosted Zones to find EC2 instances or ENIs."""
    
    try:
        # Extract parameters
        hostname = event.get('hostname', '')
        dns_name = event.get('dns_name', hostname)  # Support both parameter names
        region = event.get('region', 'us-east-1')  # Allow region override
        
        if not dns_name:
            return {
                'success': False,
                'error': 'Missing required hostname or dns_name parameter',
                'tool': 'dns-resolve',
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        logger.info(f"DNS Resolution - Hostname: {dns_name}, Region: {region}")
        
        # Step 1: Resolve DNS name using Route 53 Private Hosted Zones
        ip_address = resolve_dns_from_route53(dns_name, region)
        
        if not ip_address:
            return {
                'success': False,
                'error': f"DNS resolution failed for {dns_name}. No A record or CNAME found in Route 53 Private Hosted Zones.",
                'tool': 'dns-resolve',
                'hostname': dns_name,
                'suggestions': [
                    "Verify the DNS name is correct",
                    "Check that Route 53 Private Hosted Zone exists for the domain",
                    "Ensure the A record or CNAME exists in the Private Hosted Zone",
                    "Confirm Lambda has permissions to access Route 53",
                    "Check for CNAME chains that may be broken or circular"
                ],
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        logger.info(f"Resolved {dns_name} to IP: {ip_address}")
        
        # Step 2: Find AWS resources with this IP address
        found_resources = find_aws_resources_by_ip(ip_address, region)
        
        # Step 3: Build response
        if found_resources:
            result_text = f"🔍 DNS RESOLUTION RESULTS:\n\n"
            result_text += f"Hostname: {dns_name}\n"
            result_text += f"Resolved IP: {ip_address} (via Route 53 Private Hosted Zone)\n"
            result_text += f"Region: {region}\n"
            result_text += f"Found {len(found_resources)} AWS resource(s):\n\n"
            
            # Separate instances and ENIs for better organization
            instances = [r for r in found_resources if r['type'] == 'EC2 Instance']
            enis = [r for r in found_resources if r['type'] == 'Network Interface (ENI)']
            
            # Display EC2 instances first
            if instances:
                result_text += "📟 EC2 Instances:\n"
                for i, resource in enumerate(instances, 1):
                    result_text += f"  {i}. Instance ID: {resource['id']}\n"
                    result_text += f"     Name: {resource['name']}\n"
                    result_text += f"     Private IP: {resource['private_ip']}\n"
                    result_text += f"     State: {resource['state']}\n"
                    result_text += f"     Type: {resource['instance_type']}\n"
                    result_text += f"     VPC: {resource['vpc_id']}\n"
                    result_text += f"     Subnet: {resource['subnet_id']}\n"
                    result_text += f"     AZ: {resource['availability_zone']}\n\n"
            
            # Display ENIs
            if enis:
                result_text += "🔌 Network Interfaces (ENIs):\n"
                for i, resource in enumerate(enis, 1):
                    result_text += f"  {i}. ENI ID: {resource['id']}\n"
                    result_text += f"     Description: {resource['name']}\n"
                    result_text += f"     Private IP: {resource['private_ip']}\n"
                    result_text += f"     State: {resource['state']}\n"
                    result_text += f"     Type: {resource['interface_type']}\n"
                    result_text += f"     VPC: {resource['vpc_id']}\n"
                    result_text += f"     Subnet: {resource['subnet_id']}\n"
                    if resource['attached_instance'] != 'N/A':
                        result_text += f"     Attached to Instance: {resource['attached_instance']}\n"
                    result_text += "\n"
            
            # Provide usage guidance for connectivity analysis
            result_text += "💡 Usage for Connectivity Analysis:\n"
            for resource in instances:
                result_text += f"   • For EC2 connectivity checks, use instance ID: {resource['id']}\n"
            
            for resource in enis:
                if resource['attached_instance'] != 'N/A':
                    result_text += f"   • ENI {resource['id']} is attached to instance {resource['attached_instance']}\n"
                else:
                    result_text += f"   • For ENI connectivity checks, use ENI ID: {resource['id']}\n"
            
            return {
                'success': True,
                'result': result_text,
                'tool': 'dns-resolve',
                'hostname': dns_name,
                'resolved_ip': ip_address,
                'region': region,
                'resources': found_resources,
                'resource_count': len(found_resources),
                'instance_ids': [r['id'] for r in instances],
                'eni_ids': [r['id'] for r in enis],
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        else:
            result_text = f"🔍 DNS RESOLUTION RESULTS:\n\n"
            result_text += f"Hostname: {dns_name}\n"
            result_text += f"Resolved IP: {ip_address} (via Route 53 Private Hosted Zone)\n"
            result_text += f"Region: {region}\n"
            result_text += f"❌ No AWS resources found with IP address {ip_address}\n\n"
            result_text += "This could mean:\n"
            result_text += "• The IP address resolves to an external resource\n"
            result_text += "• The resource is in a different AWS region\n"
            result_text += "• The resource is not an EC2 instance or ENI\n"
            result_text += "• Insufficient permissions to describe EC2 resources\n"
            result_text += f"• The resource with IP {ip_address} may have been terminated\n"
            
            return {
                'success': True,
                'result': result_text,
                'tool': 'dns-resolve',
                'hostname': dns_name,
                'resolved_ip': ip_address,
                'region': region,
                'resources': [],
                'resource_count': 0,
                'instance_ids': [],
                'eni_ids': [],
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
    except Exception as e:
        logger.error(f"DNS resolution error: {str(e)}")
        return {
            'success': False,
            'error': f"DNS Resolution Error: {str(e)}",
            'tool': 'dns-resolve',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }


def lambda_handler(event, context):
    """
    AWS NetOps DNS Resolution Lambda Handler
    
    Resolves DNS names from Route 53 Private Hosted Zones to find corresponding 
    EC2 instances and ENIs for network connectivity analysis.
    """
    logger.info("AWS NetOps DNS Resolution Lambda Handler - START")
    logger.info(f"Event: {json.dumps(event, default=str)}")
    
    try:
        # Extract tool name
        tool_name = extract_tool_name(context, event)
        logger.info(f"Tool: {tool_name}")
        
        if tool_name not in DNS_TOOLS:
            return {
                'success': False,
                'error': f"Unknown tool: {tool_name}. This Lambda only supports: {DNS_TOOLS}",
                'available_tools': DNS_TOOLS,
                'tool': tool_name,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        # Route to DNS resolver
        return handle_dns_resolve(event)
    
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        return {
            'success': False,
            'error': f"Internal error: {str(e)}",
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    finally:
        logger.info("AWS NetOps DNS Resolution Lambda Handler - END")
