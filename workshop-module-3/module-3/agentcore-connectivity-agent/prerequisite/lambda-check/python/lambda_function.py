"""
AWS NetOps Agent Gateway Lambda Handler - Network Operations Version
Handles AWS network operations tools via Strands Agent integration with VPC Reachability Analyzer
Updated: 2025-01-06 - Network Operations Focus
"""
import json
import logging
import os
import boto3
from datetime import datetime
from typing import Dict, Any, Optional

# Import Strands components at module level
try:
    from strands import Agent
    from strands.models import BedrockModel
    from strands_tools import use_aws, calculator, think, current_time
    STRANDS_AVAILABLE = True
    logging.info("Strands modules imported successfully")
except ImportError as e:
    STRANDS_AVAILABLE = False
    logging.error(f"Failed to import Strands modules: {e}")

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# VPC Reachability Analyzer Tool Configuration
SERVICE_QUERIES = {
    'connectivity-check': "Use AWS VPC Reachability Analyzer to analyze network paths, troubleshoot connectivity issues, and identify reachability problems. Perform comprehensive path analysis between sources and destinations, analyze security group rules, NACL rules, route tables, and network ACLs that may affect connectivity. Provide detailed troubleshooting insights and remediation recommendations.",
    'connectivity-fix': "Automatically fix connectivity issues identified by connectivity-check tool. Apply least permissive security group rules using /32 instance CIDRs. Validate fixes by re-running connectivity analysis. Store intermediate results in agent memory."
}

BASIC_TOOLS = ['hello_world', 'get_time']
NETWORK_TOOLS = list(SERVICE_QUERIES.keys())
ALL_TOOLS = BASIC_TOOLS + NETWORK_TOOLS


def extract_tool_name(context, event: Dict[str, Any]) -> Optional[str]:
    """Extract tool name from Gateway context or event."""
    
    # Try Gateway context first
    if hasattr(context, 'client_context') and context.client_context:
        if hasattr(context.client_context, 'custom') and context.client_context.custom:
            tool_name = context.client_context.custom.get('bedrockAgentCoreToolName')
            if tool_name and '___' in tool_name:
                # Remove namespace prefix (e.g., "aws-tools___hello_world" -> "hello_world")
                return tool_name.split('___', 1)[1]
            elif tool_name:
                return tool_name
    
    # Fallback to event-based extraction
    for field in ['tool_name', 'toolName', 'name', 'method', 'action', 'function']:
        if field in event:
            return event[field]
    
    # Infer from event structure
    if isinstance(event, dict):
        if 'name' in event and len(event) == 1:
            return 'hello_world'  # Typical hello_world structure
        elif len(event) == 0:
            return 'get_time'  # Empty args typically means get_time
    
    return None


def handle_hello_world(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle hello_world tool."""
    name = event.get('name', 'World')
    message = f"Hello, {name}! This message is from a Lambda function via AWS Operations Agent Gateway."
    
    return {
        'success': True,
        'result': message,
        'tool': 'hello_world',
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }


def handle_get_time(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_time tool."""
    current_time = datetime.utcnow().isoformat() + 'Z'
    
    return {
        'success': True,
        'result': f"Current UTC time: {current_time}",
        'tool': 'get_time',
        'timestamp': current_time
    }


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
    import socket
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


def handle_vpc_reachability_analyzer(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle VPC Reachability Analyzer with proper resource resolution and path deduplication."""
    import boto3
    import time
    
    try:
        # Extract parameters with defaults
        source_resource = event.get('source_resource', '')
        destination_resource = event.get('destination_resource', '')
        protocol = event.get('protocol', 'TCP').upper()
        port = event.get('port', '3306')  # Default to 3306 for database connectivity
        user_query = event.get('query', '')
        
        logger.info(f"Direct VPC Analysis - Source: {source_resource}, Dest: {destination_resource}, Protocol: {protocol}, Port: {port}")
        
        # Validate required parameters
        if not source_resource or not destination_resource:
            return {
                'success': False,
                'error': 'Missing required source_resource or destination_resource parameters',
                'tool': 'vpc_reachability_analyzer',
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        # Create EC2 client
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        
        # Step 1: Resolve resources according to strict rules
        logger.info("Resolving source and destination resources...")
        
        # Source should ALWAYS be an instance ID
        source_instance_id = resolve_resource_to_instance_id(source_resource)
        if not source_instance_id:
            return {
                'success': False,
                'error': f"Could not resolve source resource '{source_resource}' to an instance ID",
                'tool': 'vpc_reachability_analyzer',
                'timestamp': datetime.utcnow().isoformat() + 'Z'
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
                    'error': f"Could not resolve database destination '{destination_resource}' to IP address",
                    'tool': 'vpc_reachability_analyzer',
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
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
        
        # Step 2: Build Network Insights Path parameters
        logger.info("Building Network Insights Path parameters...")
        
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
                    'error': f"Could not resolve destination resource '{destination_resource}' to instance ID or IP address",
                    'tool': 'vpc_reachability_analyzer',
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
            
            # Set port for non-database destinations
            if port:
                path_params['DestinationPort'] = int(port)
        
        logger.info(f"Network Insights Path parameters: {path_params}")
        
        # Step 3: Create Network Insights Path
        logger.info("Creating Network Insights Path...")
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
                'error': f"Failed to start VPC Reachability Analysis: {str(start_error)}",
                'tool': 'vpc_reachability_analyzer',
                'timestamp': datetime.utcnow().isoformat() + 'Z'
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
                
                # Build human-readable response
                if network_path_found:
                    result_text = f"✅ CONNECTIVITY ANALYSIS RESULTS:\n\n"
                    result_text += f"Network path found: YES\n"
                    result_text += f"Source: {source_resource}\n"
                    result_text += f"Destination: {destination_resource}\n"
                    result_text += f"Protocol: {protocol}\n"
                    if port:
                        result_text += f"Port: {port}\n"
                    result_text += f"\nThe network path analysis indicates that connectivity should work between these instances.\n"
                else:
                    result_text = f"❌ CONNECTIVITY ANALYSIS RESULTS:\n\n"
                    result_text += f"Network path found: NO\n"
                    result_text += f"Source: {source_resource}\n" 
                    result_text += f"Destination: {destination_resource}\n"
                    result_text += f"Protocol: {protocol}\n"
                    if port:
                        result_text += f"Port: {port}\n"
                    result_text += f"\nThe analysis found issues preventing connectivity:\n"
                
                # Add explanations
                if explanations:
                    result_text += "\nDetailed Findings:\n"
                    for i, explanation in enumerate(explanations[:5], 1):  # Limit to 5 explanations
                        direction = explanation.get('Direction', 'Unknown')
                        explanation_code = explanation.get('ExplanationCode', 'No code')
                        result_text += f"{i}. Direction: {direction}, Issue: {explanation_code}\n"
                
                # Keep the analysis for reference - don't auto-delete
                logger.info(f"Analysis retained: {analysis_id}, Path: {path_id}")
                logger.info("Use AWS Console or CLI to clean up analysis and path when no longer needed")
                
                return {
                    'success': True,
                    'result': result_text,
                    'tool': 'vpc_reachability_analyzer',
                    'analysis_id': analysis_id,
                    'network_path_found': network_path_found,
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
            
            elif status == 'failed':
                error_msg = f"VPC Reachability Analysis failed for path {path_id}"
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'tool': 'vpc_reachability_analyzer',
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
            
            # AWS VPC Reachability Analyzer polling interval - required for service
            analysis_poll_interval = 5
            logger.info(f"Waiting {analysis_poll_interval}s before next status check...")
            # INTENTIONAL DELAY: AWS VPC Reachability Analyzer service requires polling intervals between status checks to prevent API throttling
            time.sleep(analysis_poll_interval)  # nosemgrep: arbitrary-sleep
        
        # Analysis timed out
        return {
            'success': False,
            'error': f"VPC Reachability Analysis timed out after {max_wait_time} seconds",
            'tool': 'vpc_reachability_analyzer',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
    except Exception as e:
        logger.error(f"VPC Reachability Analyzer error: {str(e)}")
        return {
            'success': False,
            'error': f"VPC Reachability Analyzer Error: {str(e)}",
            'tool': 'vpc_reachability_analyzer',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }


def handle_aws_service_tool(tool_name: str, event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle AWS service tools using Strands Agent."""
    
    # Special handling for VPC Reachability Analyzer
    if tool_name == 'connectivity-check':
        return handle_vpc_reachability_analyzer(event)
    
    # Check if Strands is available
    if not STRANDS_AVAILABLE:
        return {
            'success': False,
            'error': f"Strands modules not available for {tool_name}. Please check Lambda dependencies.",
            'tool': tool_name,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    try:
        # Get the natural language query from the simplified schema
        user_query = event.get('query', '')
        if not user_query:
            return {
                'success': False,
                'error': f"Missing required 'query' parameter for {tool_name}",
                'tool': tool_name,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        logger.info(f"Initializing Strands Agent for: {tool_name}")
        
        # Initialize Bedrock model
        bedrock_model = BedrockModel(
            region_name='us-east-1',
            model_id='global.anthropic.claude-opus-4-5-20251101-v1:0',
            temperature=0.1,
            system_prompt="""You are an AWS service specialist focused on network operations and troubleshooting."""
        )
        
        # Create Strands Agent
        agent = Agent(model=bedrock_model, tools=[use_aws, calculator, think, current_time])
        
        # Build the final query combining service context with user query
        service_context = SERVICE_QUERIES.get(tool_name, f"AWS {tool_name.replace('_read_operations', '').upper()} service operations")
        final_query = f"AWS Service: {tool_name.replace('_read_operations', '').upper()}\nUser Request: {user_query}\nContext: {service_context}\n\nExecute this AWS operation and return structured results."
        
        logger.info(f"Executing simplified query for {tool_name}: {user_query}")
        
        # Execute query
        response = agent(final_query)
        
        # Extract response text
        response_text = ""
        if hasattr(response, 'message') and 'content' in response.message:
            for content_block in response.message['content']:
                if content_block.get('type') == 'text' or 'text' in content_block:
                    response_text += content_block.get('text', '')
        else:
            response_text = str(response)
        
        logger.info(f"Response length: {len(response_text)} characters")
        
        return {
            'success': True,
            'result': response_text,
            'tool': tool_name,
            'service': tool_name.replace('_read_operations', '').replace('_', '-'),
            'user_query': user_query,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
    except Exception as e:
        logger.error(f"AWS service tool error: {str(e)}")
        return {
            'success': False,
            'error': f"AWS Service Tool Error: {str(e)}",
            'tool': tool_name,
            'service': tool_name.replace('_read_operations', '').replace('_', '-'),
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }


def lambda_handler(event, context):
    """
    AWS Operations Agent Gateway Lambda Handler - Optimized Version
    
    Handles basic tools (hello_world, get_time) and AWS service tools
    via Strands Agent integration with comprehensive error handling.
    """
    logger.info("AWS Operations Agent Gateway Lambda Handler - START")
    logger.info(f"Event: {json.dumps(event, default=str)}")
    
    try:
        # Extract tool name
        tool_name = extract_tool_name(context, event)
        logger.info(f"Tool: {tool_name}")
        
        if not tool_name:
            return {
                'success': False,
                'error': 'Unable to determine tool name from context or event',
                'available_tools': ALL_TOOLS,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        
        # Route to appropriate handler
        if tool_name == 'hello_world':
            return handle_hello_world(event)
        
        elif tool_name == 'get_time':
            return handle_get_time(event)
        
        elif tool_name in NETWORK_TOOLS:
            return handle_aws_service_tool(tool_name, event)
        
        else:
            # Unknown tool
            return {
                'success': False,
                'error': f"Unknown tool: {tool_name}",
                'available_tools': ALL_TOOLS,
                'total_tools': len(ALL_TOOLS),
                'categories': {
                    'basic': BASIC_TOOLS,
                    'network_services': NETWORK_TOOLS
                },
                'tool': tool_name,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
    
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        return {
            'success': False,
            'error': f"Internal error: {str(e)}",
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    finally:
        logger.info("AWS NetOps Agent Gateway Lambda Handler - END")
