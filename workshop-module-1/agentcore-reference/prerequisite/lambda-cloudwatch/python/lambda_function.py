import json
import boto3
import os
import socket
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Initialize AWS clients
cloudwatch = boto3.client('cloudwatch')
logs_client = boto3.client('logs')
ec2_client = boto3.client('ec2')
rds_client = boto3.client('rds')
lambda_client = boto3.client('lambda')
route53_client = boto3.client('route53')

def lambda_handler(event, context):
    """
    Main Lambda handler for CloudWatch tools.
    Handles alarms, logs, and metrics operations.
    """
    try:
        print(f"Received event: {json.dumps(event)}")
        
        # Extract the tool name and parameters - support both nested and flat parameter structures
        tool_name = event.get('tool_name', event.get('operation', ''))
        
        # Check if parameters are nested or at root level
        if 'parameters' in event:
            # Nested structure: {"tool_name": "get_metric_data", "parameters": {...}}
            parameters = event.get('parameters', {})
        else:
            # Flat structure: {"operation": "get_metric_data", "metric_name": "CPUUtilization", ...}
            parameters = {k: v for k, v in event.items() if k not in ['tool_name', 'operation']}
        
        print(f"Extracted tool_name: {tool_name}")
        print(f"Extracted parameters: {json.dumps(parameters)}")
        
        if tool_name == 'describe_alarms':
            return describe_alarms(parameters)
        elif tool_name == 'get_metric_data':
            return get_metric_data(parameters)
        elif tool_name == 'query_logs':
            return query_logs(parameters)
        elif tool_name == 'list_log_groups':
            return list_log_groups(parameters)
        elif tool_name == 'get_log_events':
            return get_log_events(parameters)
        elif tool_name == 'create_alarm':
            return create_alarm(parameters)
        elif tool_name == 'delete_alarm':
            return delete_alarm(parameters)
        elif tool_name == 'query_vpc_flow_logs':
            return query_vpc_flow_logs(parameters)
        elif tool_name == 'resolve_hostname_to_eni':
            return resolve_hostname_to_eni(parameters)
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': f'Unknown tool: {tool_name}',
                    'available_tools': [
                        'describe_alarms', 'get_metric_data', 'query_logs',
                        'list_log_groups', 'get_log_events', 'create_alarm', 'delete_alarm',
                        'query_vpc_flow_logs', 'resolve_hostname_to_eni'
                    ]
                })
            }
            
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Internal error: {str(e)}'
            })
        }

def describe_alarms(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Describe CloudWatch alarms with optional filtering."""
    try:
        alarm_names = parameters.get('alarm_names', [])
        state_value = parameters.get('state_value')  # OK, ALARM, INSUFFICIENT_DATA
        max_records = parameters.get('max_records', 100)
        
        kwargs = {'MaxRecords': min(max_records, 100)}
        
        if alarm_names:
            kwargs['AlarmNames'] = alarm_names
        if state_value:
            kwargs['StateValue'] = state_value
            
        response = cloudwatch.describe_alarms(**kwargs)
        
        alarms = []
        for alarm in response.get('MetricAlarms', []):
            alarms.append({
                'AlarmName': alarm.get('AlarmName'),
                'AlarmDescription': alarm.get('AlarmDescription'),
                'StateValue': alarm.get('StateValue'),
                'StateReason': alarm.get('StateReason'),
                'MetricName': alarm.get('MetricName'),
                'Namespace': alarm.get('Namespace'),
                'Statistic': alarm.get('Statistic'),
                'Threshold': alarm.get('Threshold'),
                'ComparisonOperator': alarm.get('ComparisonOperator'),
                'AlarmArn': alarm.get('AlarmArn'),
                'StateUpdatedTimestamp': alarm.get('StateUpdatedTimestamp').isoformat() if alarm.get('StateUpdatedTimestamp') else None
            })
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'alarms': alarms,
                'count': len(alarms)
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to describe alarms: {str(e)}'})
        }

def get_metric_data(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Get CloudWatch metric data."""
    try:
        namespace = parameters.get('namespace', 'AWS/EC2')
        metric_name = parameters.get('metric_name', 'CPUUtilization')
        dimensions_input = parameters.get('dimensions', {})
        start_time = parameters.get('start_time')
        end_time = parameters.get('end_time')
        period = parameters.get('period', 300)
        statistic = parameters.get('statistic', 'Average')
        
        print(f"Processing metric request - Namespace: {namespace}, Metric: {metric_name}")
        print(f"Dimensions input: {dimensions_input}")
        
        # Convert dimensions from dict to list format expected by CloudWatch API
        dimensions = []
        if isinstance(dimensions_input, dict):
            for key, value in dimensions_input.items():
                dimensions.append({
                    'Name': key,
                    'Value': value
                })
        elif isinstance(dimensions_input, list):
            dimensions = dimensions_input
        
        print(f"Converted dimensions: {dimensions}")
        
        # Handle relative time formats
        if start_time and isinstance(start_time, str):
            if start_time.endswith('h'):
                hours = int(start_time[:-1])
                start_dt = datetime.utcnow() - timedelta(hours=hours)
            elif start_time.endswith('d'):
                days = int(start_time[:-1])
                start_dt = datetime.utcnow() - timedelta(days=days)
            else:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        else:
            start_dt = datetime.utcnow() - timedelta(hours=1)
        
        if end_time and isinstance(end_time, str):
            if end_time == 'now':
                end_dt = datetime.utcnow()
            else:
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()
        
        print(f"Time range: {start_dt} to {end_dt}")
        
        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_dt,
            EndTime=end_dt,
            Period=period,
            Statistics=[statistic]
        )
        
        print(f"CloudWatch response: {len(response.get('Datapoints', []))} datapoints")
        
        datapoints = []
        for point in response.get('Datapoints', []):
            datapoints.append({
                'Timestamp': point.get('Timestamp').isoformat(),
                'Value': point.get(statistic),
                'Unit': point.get('Unit')
            })
            
        # Sort by timestamp
        datapoints.sort(key=lambda x: x['Timestamp'])
        
        result = {
            'statusCode': 200,
            'body': json.dumps({
                'metric_name': metric_name,
                'namespace': namespace,
                'statistic': statistic,
                'dimensions': dimensions,
                'start_time': start_dt.isoformat(),
                'end_time': end_dt.isoformat(),
                'period': period,
                'datapoints': datapoints,
                'count': len(datapoints)
            })
        }
        
        print(f"Returning result with {len(datapoints)} datapoints")
        return result
        
    except Exception as e:
        print(f"Error in get_metric_data: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to get metric data: {str(e)}'})
        }

def query_logs(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Query CloudWatch Logs using CloudWatch Logs Insights."""
    try:
        log_group_name = parameters.get('log_group_name')
        query_string = parameters.get('query_string', 'fields @timestamp, @message | sort @timestamp desc | limit 100')
        start_time = parameters.get('start_time')
        end_time = parameters.get('end_time')
        
        if not log_group_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'log_group_name is required'})
            }
            
        # Default to last hour if no time range specified
        if not start_time:
            start_time = int((datetime.utcnow() - timedelta(hours=1)).timestamp())
        else:
            start_time = int(datetime.fromisoformat(start_time.replace('Z', '+00:00')).timestamp())
            
        if not end_time:
            end_time = int(datetime.utcnow().timestamp())
        else:
            end_time = int(datetime.fromisoformat(end_time.replace('Z', '+00:00')).timestamp())
        
        # Start the query
        response = logs_client.start_query(
            logGroupName=log_group_name,
            startTime=start_time,
            endTime=end_time,
            queryString=query_string
        )
        
        query_id = response['queryId']
        
        # Poll for results (with timeout)
        import time
        max_wait = 30  # seconds
        wait_time = 0
        
        while wait_time < max_wait:
            result = logs_client.get_query_results(queryId=query_id)
            
            if result['status'] == 'Complete':
                events = []
                for result_row in result.get('results', []):
                    event = {}
                    for field in result_row:
                        event[field['field']] = field['value']
                    events.append(event)
                    
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'log_group': log_group_name,
                        'query': query_string,
                        'events': events,
                        'count': len(events)
                    })
                }
            elif result['status'] == 'Failed':
                return {
                    'statusCode': 500,
                    'body': json.dumps({'error': 'Query failed'})
                }
                
            time.sleep(1)
            wait_time += 1
            
        return {
            'statusCode': 408,
            'body': json.dumps({'error': 'Query timeout'})
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to query logs: {str(e)}'})
        }

def list_log_groups(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """List CloudWatch Log Groups."""
    try:
        name_prefix = parameters.get('name_prefix', '')
        limit = parameters.get('limit', 50)
        
        kwargs = {'limit': min(limit, 50)}
        if name_prefix:
            kwargs['logGroupNamePrefix'] = name_prefix
            
        response = logs_client.describe_log_groups(**kwargs)
        
        log_groups = []
        for group in response.get('logGroups', []):
            log_groups.append({
                'logGroupName': group.get('logGroupName'),
                'creationTime': group.get('creationTime'),
                'retentionInDays': group.get('retentionInDays'),
                'storedBytes': group.get('storedBytes'),
                'arn': group.get('arn')
            })
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'log_groups': log_groups,
                'count': len(log_groups)
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to list log groups: {str(e)}'})
        }

def get_log_events(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Get log events from a specific log stream."""
    try:
        log_group_name = parameters.get('log_group_name')
        log_stream_name = parameters.get('log_stream_name')
        start_time = parameters.get('start_time')
        end_time = parameters.get('end_time')
        limit = parameters.get('limit', 100)
        
        if not log_group_name or not log_stream_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'log_group_name and log_stream_name are required'})
            }
            
        kwargs = {
            'logGroupName': log_group_name,
            'logStreamName': log_stream_name,
            'limit': min(limit, 1000)
        }
        
        if start_time:
            kwargs['startTime'] = int(datetime.fromisoformat(start_time.replace('Z', '+00:00')).timestamp() * 1000)
        if end_time:
            kwargs['endTime'] = int(datetime.fromisoformat(end_time.replace('Z', '+00:00')).timestamp() * 1000)
            
        response = logs_client.get_log_events(**kwargs)
        
        events = []
        for event in response.get('events', []):
            events.append({
                'timestamp': datetime.fromtimestamp(event['timestamp'] / 1000).isoformat(),
                'message': event['message']
            })
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'log_group': log_group_name,
                'log_stream': log_stream_name,
                'events': events,
                'count': len(events)
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to get log events: {str(e)}'})
        }

def create_alarm(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Create a CloudWatch alarm."""
    try:
        alarm_name = parameters.get('alarm_name')
        alarm_description = parameters.get('alarm_description', '')
        metric_name = parameters.get('metric_name')
        namespace = parameters.get('namespace')
        statistic = parameters.get('statistic', 'Average')
        period = parameters.get('period', 300)
        evaluation_periods = parameters.get('evaluation_periods', 1)
        threshold = parameters.get('threshold')
        comparison_operator = parameters.get('comparison_operator', 'GreaterThanThreshold')
        dimensions = parameters.get('dimensions', [])
        
        if not all([alarm_name, metric_name, namespace, threshold]):
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'alarm_name, metric_name, namespace, and threshold are required'})
            }
            
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            AlarmDescription=alarm_description,
            MetricName=metric_name,
            Namespace=namespace,
            Statistic=statistic,
            Period=period,
            EvaluationPeriods=evaluation_periods,
            Threshold=float(threshold),
            ComparisonOperator=comparison_operator,
            Dimensions=dimensions
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Alarm {alarm_name} created successfully',
                'alarm_name': alarm_name
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to create alarm: {str(e)}'})
        }

def delete_alarm(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a CloudWatch alarm."""
    try:
        alarm_names = parameters.get('alarm_names', [])
        
        if not alarm_names:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'alarm_names list is required'})
            }
            
        cloudwatch.delete_alarms(AlarmNames=alarm_names)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Deleted {len(alarm_names)} alarm(s)',
                'deleted_alarms': alarm_names
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to delete alarms: {str(e)}'})
        }

def resolve_hostname_to_eni(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve hostname to ENI IDs and associated AWS resources."""
    try:
        hostname = parameters.get('hostname')
        
        if not hostname:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'hostname is required'})
            }
        
        print(f"Resolving hostname: {hostname}")
        
        # Try to resolve hostname to IP address first
        try:
            ip_address = socket.gethostbyname(hostname)
            print(f"Resolved {hostname} to IP: {ip_address}")
        except socket.gaierror:
            print(f"Could not resolve hostname {hostname} via DNS")
            ip_address = None
        
        resources = []
        eni_ids = []
        
        # Search for EC2 instances by hostname tag or private DNS name
        try:
            ec2_response = ec2_client.describe_instances(
                Filters=[
                    {
                        'Name': 'tag:Name',
                        'Values': [hostname, hostname.split('.')[0]]  # Try both FQDN and short name
                    },
                    {
                        'Name': 'instance-state-name',
                        'Values': ['running', 'stopped']
                    }
                ]
            )
            
            for reservation in ec2_response.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    instance_id = instance.get('InstanceId')
                    private_ip = instance.get('PrivateIpAddress')
                    
                    # Get ENI IDs for this instance
                    for eni in instance.get('NetworkInterfaces', []):
                        eni_id = eni.get('NetworkInterfaceId')
                        if eni_id:
                            eni_ids.append(eni_id)
                    
                    resources.append({
                        'type': 'EC2',
                        'resource_id': instance_id,
                        'private_ip': private_ip,
                        'public_ip': instance.get('PublicIpAddress'),
                        'vpc_id': instance.get('VpcId'),
                        'subnet_id': instance.get('SubnetId'),
                        'eni_ids': [eni.get('NetworkInterfaceId') for eni in instance.get('NetworkInterfaces', [])],
                        'state': instance.get('State', {}).get('Name')
                    })
                    
        except Exception as e:
            print(f"Error searching EC2 instances: {str(e)}")
        
        # Search for RDS instances by hostname or identifier
        try:
            rds_response = rds_client.describe_db_instances()
            
            for db_instance in rds_response.get('DBInstances', []):
                db_identifier = db_instance.get('DBInstanceIdentifier')
                endpoint = db_instance.get('Endpoint', {})
                endpoint_address = endpoint.get('Address', '')
                
                # Check if hostname matches DB endpoint or identifier
                if hostname in endpoint_address or hostname == db_identifier:
                    # For RDS, we need to find the ENI through VPC security groups
                    vpc_security_groups = db_instance.get('VpcSecurityGroups', [])
                    subnet_group = db_instance.get('DBSubnetGroup', {})
                    
                    resources.append({
                        'type': 'RDS',
                        'resource_id': db_identifier,
                        'endpoint': endpoint_address,
                        'port': endpoint.get('Port'),
                        'vpc_id': subnet_group.get('VpcId'),
                        'subnet_ids': [subnet.get('SubnetIdentifier') for subnet in subnet_group.get('Subnets', [])],
                        'security_groups': [sg.get('VpcSecurityGroupId') for sg in vpc_security_groups],
                        'engine': db_instance.get('Engine'),
                        'status': db_instance.get('DBInstanceStatus')
                    })
                    
        except Exception as e:
            print(f"Error searching RDS instances: {str(e)}")
        
        # If we have an IP address, search for ENIs with that IP
        if ip_address:
            try:
                eni_response = ec2_client.describe_network_interfaces(
                    Filters=[
                        {
                            'Name': 'private-ip-address',
                            'Values': [ip_address]
                        }
                    ]
                )
                
                for eni in eni_response.get('NetworkInterfaces', []):
                    eni_id = eni.get('NetworkInterfaceId')
                    if eni_id and eni_id not in eni_ids:
                        eni_ids.append(eni_id)
                        
                        # Add ENI details to resources if not already found
                        attachment = eni.get('Attachment', {})
                        resources.append({
                            'type': 'ENI',
                            'resource_id': eni_id,
                            'private_ip': eni.get('PrivateIpAddress'),
                            'vpc_id': eni.get('VpcId'),
                            'subnet_id': eni.get('SubnetId'),
                            'attached_instance': attachment.get('InstanceId'),
                            'status': eni.get('Status'),
                            'interface_type': eni.get('InterfaceType')
                        })
                        
            except Exception as e:
                print(f"Error searching ENIs by IP: {str(e)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'hostname': hostname,
                'resolved_ip': ip_address,
                'eni_ids': eni_ids,
                'resources': resources,
                'count': len(resources)
            })
        }
        
    except Exception as e:
        print(f"Error in resolve_hostname_to_eni: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to resolve hostname to ENI: {str(e)}'})
        }

def query_vpc_flow_logs(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Query VPC Flow Logs with hostname to ENI-ID translation."""
    try:
        # Parameters for the query
        log_group_name = parameters.get('log_group_name')
        source_hostname = parameters.get('source_hostname')
        dest_hostname = parameters.get('dest_hostname')
        source_ip = parameters.get('source_ip')
        dest_ip = parameters.get('dest_ip')
        source_eni = parameters.get('source_eni')
        dest_eni = parameters.get('dest_eni')
        start_time = parameters.get('start_time')
        end_time = parameters.get('end_time')
        action = parameters.get('action')  # ACCEPT, REJECT, or both
        protocol = parameters.get('protocol')  # TCP, UDP, ICMP, etc.
        port = parameters.get('port')
        limit = parameters.get('limit', 100)
        
        print(f"VPC Flow Logs query parameters: {parameters}")
        
        # Resolve hostnames to ENI IDs if provided
        source_enis = []
        dest_enis = []
        
        if source_hostname:
            print(f"Resolving source hostname: {source_hostname}")
            resolve_result = resolve_hostname_to_eni({'hostname': source_hostname})
            if resolve_result['statusCode'] == 200:
                resolve_data = json.loads(resolve_result['body'])
                source_enis.extend(resolve_data.get('eni_ids', []))
                if not source_ip and resolve_data.get('resolved_ip'):
                    source_ip = resolve_data['resolved_ip']
        
        if dest_hostname:
            print(f"Resolving destination hostname: {dest_hostname}")
            resolve_result = resolve_hostname_to_eni({'hostname': dest_hostname})
            if resolve_result['statusCode'] == 200:
                resolve_data = json.loads(resolve_result['body'])
                dest_enis.extend(resolve_data.get('eni_ids', []))
                if not dest_ip and resolve_data.get('resolved_ip'):
                    dest_ip = resolve_data['resolved_ip']
        
        if source_eni:
            source_enis.append(source_eni)
        if dest_eni:
            dest_enis.append(dest_eni)
        
        print(f"Resolved ENIs - Source: {source_enis}, Dest: {dest_enis}")
        
        # Build the CloudWatch Logs Insights query
        query_parts = ["fields @timestamp, srcaddr, dstaddr, srcport, dstport, protocol, action, interfaceid"]
        
        # Add filters based on available parameters
        filters = []
        
        if source_enis:
            eni_filter = " or ".join([f'interfaceid = "{eni}"' for eni in source_enis])
            filters.append(f"({eni_filter})")
        
        if dest_enis:
            eni_filter = " or ".join([f'interfaceid = "{eni}"' for eni in dest_enis])
            if filters:
                filters.append(f"({eni_filter})")
            else:
                filters.append(f"({eni_filter})")
        
        if source_ip:
            filters.append(f'srcaddr = "{source_ip}"')
        
        if dest_ip:
            filters.append(f'dstaddr = "{dest_ip}"')
        
        if action:
            filters.append(f'action = "{action.upper()}"')
        
        if protocol:
            if protocol.upper() == 'TCP':
                filters.append('protocol = "6"')
            elif protocol.upper() == 'UDP':
                filters.append('protocol = "17"')
            elif protocol.upper() == 'ICMP':
                filters.append('protocol = "1"')
            else:
                filters.append(f'protocol = "{protocol}"')
        
        if port:
            filters.append(f'(srcport = "{port}" or dstport = "{port}")')
        
        # Combine filters
        if filters:
            query_parts.append("filter " + " and ".join(filters))
        
        # Add sorting and limit
        query_parts.extend([
            "sort @timestamp desc",
            f"limit {min(limit, 1000)}"
        ])
        
        query_string = " | ".join(query_parts)
        print(f"Generated query: {query_string}")
        
        # Use the existing query_logs function with our generated query
        query_params = {
            'log_group_name': log_group_name,
            'query_string': query_string,
            'start_time': start_time,
            'end_time': end_time
        }
        
        result = query_logs(query_params)
        
        # Enhance the result with hostname resolution info
        if result['statusCode'] == 200:
            result_data = json.loads(result['body'])
            result_data['hostname_resolution'] = {
                'source_hostname': source_hostname,
                'dest_hostname': dest_hostname,
                'source_enis': source_enis,
                'dest_enis': dest_enis,
                'resolved_source_ip': source_ip,
                'resolved_dest_ip': dest_ip
            }
            result['body'] = json.dumps(result_data)
        
        return result
        
    except Exception as e:
        print(f"Error in query_vpc_flow_logs: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to query VPC flow logs: {str(e)}'})
        }
