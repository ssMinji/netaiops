#!/usr/bin/env python3
"""
A2A Collaborator AgentCore Runtime Test - Machine-to-Machine Authentication
This script uses client_credentials flow to avoid browser authentication
"""

import json
import requests
import urllib.parse
import uuid
import sys
import os
import click
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure we can import local utilities
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import boto3
import yaml


def get_aws_region() -> str:
    """Get the current AWS region."""
    try:
        session = boto3.Session()
        return session.region_name or 'us-east-1'
    except Exception:
        return 'us-east-1'


def get_ssm_parameter(parameter_name: str) -> str:
    """Get parameter from AWS Systems Manager Parameter Store"""
    try:
        ssm = boto3.client('ssm', region_name=get_aws_region())
        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        return response['Parameter']['Value']
    except Exception as e:
        logger.error(f"Could not retrieve SSM parameter {parameter_name}: {e}")
        raise


def read_config(config_file: str) -> dict:
    """Read configuration from YAML file"""
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return yaml.safe_load(f) or {}
        else:
            logger.warning(f"Configuration file {config_file} not found")
            return {}
    except Exception as e:
        logger.error(f"Error reading configuration file {config_file}: {e}")
        return {}


def check_connectivity_restored():
    """Check if connectivity between reporting.examplecorp.com and database.examplecorp.com has been restored."""
    try:
        # Initialize AWS clients with region
        region = get_aws_region()
        ec2_client = boto3.client('ec2', region_name=region)
        
        print("\n🔍 Checking if connectivity has been restored...")
        
        # Get existing network insight paths created by the agent
        try:
            paths_response = ec2_client.describe_network_insights_paths()
            network_paths = paths_response.get('NetworkInsightsPaths', [])
            
            print(f"✓ Found {len(network_paths)} existing network insight paths")
            
            path_analyses = []
            connectivity_restored = False
            
            # Check each path and get its analysis status
            for path in network_paths:
                path_id = path.get('NetworkInsightsPathId')
                source = path.get('Source', 'Unknown')
                destination = path.get('Destination', 'Unknown')
                
                print(f"  📍 Analyzing path: {path_id}")
                print(f"     Source: {source}")
                print(f"     Destination: {destination}")
                
                # Get the latest analysis for this path
                try:
                    analyses_response = ec2_client.describe_network_insights_analyses(
                        NetworkInsightsPathId=path_id
                    )
                    analyses = analyses_response.get('NetworkInsightsAnalyses', [])
                    
                    if analyses:
                        # Get the most recent analysis
                        latest_analysis = sorted(analyses, key=lambda x: x.get('StartDate', ''), reverse=True)[0]
                        analysis_id = latest_analysis.get('NetworkInsightsAnalysisId')
                        status = latest_analysis.get('Status', 'unknown')
                        network_path_found = latest_analysis.get('NetworkPathFound', False)
                        
                        # Determine reachability status
                        if status == 'succeeded' and network_path_found:
                            reachability_status = 'Reachable'
                            connectivity_restored = True
                        elif status == 'succeeded' and not network_path_found:
                            reachability_status = 'Not reachable'
                        else:
                            reachability_status = f'Analysis {status}'
                        
                        path_analyses.append({
                            'path_id': path_id,
                            'analysis_id': analysis_id,
                            'status': reachability_status,
                            'source': source,
                            'destination': destination
                        })
                        
                        print(f"     Status: {reachability_status}")
                    else:
                        print(f"     No analyses found for path {path_id}")
                        path_analyses.append({
                            'path_id': path_id,
                            'analysis_id': 'no-analysis',
                            'status': 'No analysis available',
                            'source': source,
                            'destination': destination
                        })
                        
                except Exception as analysis_error:
                    print(f"     ⚠ Error getting analysis for path {path_id}: {analysis_error}")
                    path_analyses.append({
                        'path_id': path_id,
                        'analysis_id': 'error',
                        'status': 'Analysis error',
                        'source': source,
                        'destination': destination
                    })
            
            # If no existing paths found, fall back to basic security group check
            if not network_paths:
                print("  No existing network insight paths found, checking security groups...")
                
                # Find the DatabaseSecurityGroup
                sg_response = ec2_client.describe_security_groups()
                security_groups = sg_response.get('SecurityGroups', [])
                
                database_sg_id = None
                for sg in security_groups:
                    sg_name = sg.get('GroupName', '')
                    if 'sample-application-DatabaseSecurityGroup' in sg_name:
                        database_sg_id = sg.get('GroupId')
                        break
                
                if database_sg_id:
                    # Check if there's any rule allowing MySQL access
                    sg_details = ec2_client.describe_security_groups(GroupIds=[database_sg_id])
                    sg_info = sg_details['SecurityGroups'][0]
                    
                    mysql_rules_found = []
                    for rule in sg_info.get('IpPermissions', []):
                        protocol = rule.get('IpProtocol')
                        from_port = rule.get('FromPort')
                        to_port = rule.get('ToPort')
                        
                        if protocol == 'tcp' and from_port == 3306 and to_port == 3306:
                            for ip_range in rule.get('IpRanges', []):
                                cidr = ip_range.get('CidrIp', '')
                                if (cidr == '10.1.0.0/16' or cidr.startswith('10.1.') or cidr == '0.0.0.0/0'):
                                    mysql_rules_found.append(cidr)
                    
                    if mysql_rules_found:
                        connectivity_restored = True
                        path_analyses.append({
                            'path_id': database_sg_id,
                            'analysis_id': 'security-group-check',
                            'status': 'Reachable',
                            'source': 'reporting.examplecorp.com',
                            'destination': 'database.examplecorp.com'
                        })
                    else:
                        path_analyses.append({
                            'path_id': database_sg_id,
                            'analysis_id': 'security-group-check',
                            'status': 'Not reachable',
                            'source': 'reporting.examplecorp.com',
                            'destination': 'database.examplecorp.com'
                        })
            
            # Create comprehensive path analysis result
            path_analysis = {
                'connectivity_restored': connectivity_restored,
                'path_analyses': path_analyses,
                'total_paths_checked': len(path_analyses),
                'analysis_timestamp': __import__('datetime').datetime.now().isoformat(),
                'validation_method': 'network_insights_path_analysis'
            }
            
            if connectivity_restored:
                print("✅ Connectivity restored based on path analysis")
            else:
                print("❌ Connectivity not restored based on path analysis")
            
            return connectivity_restored, path_analysis
            
        except Exception as path_error:
            print(f"⚠ Error getting network insight paths: {path_error}")
            return False, None
        
    except Exception as e:
        print(f"⚠ Error checking connectivity: {e}")
        return False, None


def close_ticket_by_subject(subject_pattern: str, message: str = "Issue resolved by A2A_CollaboratorAgent"):
    """Close a ticket by matching subject pattern - no validation checks."""
    try:
        region = get_aws_region()
        ssm_client = boto3.client('ssm', region_name=region)
        lambda_client = boto3.client('lambda', region_name=region)
        
        print(f"\n🎫 Looking for ticket with subject containing: '{subject_pattern}'")
        
        # Try API Gateway first
        try:
            response = ssm_client.get_parameter(Name='/examplecorp/support/api-gateway-url')
            api_gateway_url = response['Parameter']['Value']
            
            import urllib.request
            req = urllib.request.Request(f"{api_gateway_url}/tickets")
            req.add_header('User-Agent', 'A2A_CollaboratorAgent/1.0')
            req.add_header('Accept', 'application/json')
            
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    result = json.loads(response.read().decode('utf-8'))
                    tickets = result.get('tickets', [])
                    
                    # Find ticket by subject pattern
                    target_ticket = None
                    for ticket in sorted(tickets, key=lambda x: x.get('created_at', ''), reverse=True):
                        if subject_pattern.lower() in ticket.get('subject', '').lower():
                            target_ticket = ticket
                            break
                    
                    if not target_ticket:
                        print(f"⚠ No ticket found with subject containing: '{subject_pattern}'")
                        print("  Available tickets:")
                        for ticket in tickets[:5]:  # Show first 5 tickets
                            print(f"    - {ticket.get('subject', 'No subject')}")
                        return False
                    
                    ticket_id = target_ticket.get('id')
                    print(f"✓ Found ticket: {ticket_id} - {target_ticket.get('subject')}")
                    
                    # Add correspondence
                    correspondence_data = {
                        "author": "A2A_CollaboratorAgent",
                        "message": message,
                        "message_type": "system"
                    }
                    
                    data = json.dumps(correspondence_data).encode('utf-8')
                    req = urllib.request.Request(
                        f"{api_gateway_url}/tickets/{ticket_id}/correspondence",
                        data=data,
                        headers={
                            'Content-Type': 'application/json',
                            'User-Agent': 'A2A_CollaboratorAgent/1.0'
                        }
                    )
                    req.get_method = lambda: 'POST'
                    
                    with urllib.request.urlopen(req, timeout=30) as response:
                        if response.status == 201:
                            print("✅ Successfully added correspondence")
                            
                            # Close the ticket
                            close_data = json.dumps({"status": "closed"}).encode('utf-8')
                            close_req = urllib.request.Request(
                                f"{api_gateway_url}/tickets/{ticket_id}",
                                data=close_data,
                                headers={
                                    'Content-Type': 'application/json',
                                    'User-Agent': 'A2A_CollaboratorAgent/1.0'
                                }
                            )
                            close_req.get_method = lambda: 'PUT'
                            
                            with urllib.request.urlopen(close_req, timeout=30) as close_response:
                                if close_response.status in [200, 204]:
                                    print("✅ Successfully closed ticket")
                                    return True
                                else:
                                    print(f"⚠ Failed to close ticket: HTTP {close_response.status}")
                                    return False
                        else:
                            print(f"⚠ Failed to add correspondence: HTTP {response.status}")
                            return False
                            
        except Exception as api_error:
            print(f"⚠ API Gateway method failed: {api_error}")
            print("  Trying Lambda fallback...")
            
            # Fallback to Lambda
            try:
                functions_response = lambda_client.list_functions()
                support_function_name = None
                
                for func in functions_response.get('Functions', []):
                    func_name = func.get('FunctionName', '')
                    if 'support-ticket' in func_name.lower():
                        support_function_name = func_name
                        break
                
                if support_function_name:
                    # Get tickets via Lambda
                    lambda_event = {
                        'path': '/tickets',
                        'httpMethod': 'GET',
                        'headers': {'Content-Type': 'application/json'}
                    }
                    
                    response = lambda_client.invoke(
                        FunctionName=support_function_name,
                        InvocationType='RequestResponse',
                        Payload=json.dumps(lambda_event)
                    )
                    
                    result = json.loads(response['Payload'].read().decode('utf-8'))
                    
                    if result.get('statusCode') == 200:
                        body = json.loads(result.get('body', '{}'))
                        tickets = body.get('tickets', [])
                        
                        # Find ticket by subject pattern
                        target_ticket = None
                        for ticket in sorted(tickets, key=lambda x: x.get('created_at', ''), reverse=True):
                            if subject_pattern.lower() in ticket.get('subject', '').lower():
                                target_ticket = ticket
                                break
                        
                        if not target_ticket:
                            print(f"⚠ No ticket found with subject containing: '{subject_pattern}'")
                            return False
                        
                        ticket_id = target_ticket.get('id')
                        print(f"✓ Found ticket: {ticket_id} - {target_ticket.get('subject')}")
                        
                        # Add correspondence via Lambda
                        correspondence_data = {
                            "author": "A2A_CollaboratorAgent",
                            "message": message,
                            "message_type": "system"
                        }
                        
                        lambda_event = {
                            'path': f'/tickets/{ticket_id}/correspondence',
                            'httpMethod': 'POST',
                            'body': json.dumps(correspondence_data),
                            'headers': {'Content-Type': 'application/json'}
                        }
                        
                        response = lambda_client.invoke(
                            FunctionName=support_function_name,
                            InvocationType='RequestResponse',
                            Payload=json.dumps(lambda_event)
                        )
                        
                        result = json.loads(response['Payload'].read().decode('utf-8'))
                        
                        if result.get('statusCode') == 201:
                            print("✅ Successfully added correspondence via Lambda")
                            
                            # Close ticket via Lambda
                            close_event = {
                                'path': f'/tickets/{ticket_id}',
                                'httpMethod': 'PUT',
                                'body': json.dumps({"status": "closed"}),
                                'headers': {'Content-Type': 'application/json'}
                            }
                            
                            close_response = lambda_client.invoke(
                                FunctionName=support_function_name,
                                InvocationType='RequestResponse',
                                Payload=json.dumps(close_event)
                            )
                            
                            close_result = json.loads(close_response['Payload'].read().decode('utf-8'))
                            
                            if close_result.get('statusCode') == 200:
                                print("✅ Successfully closed ticket via Lambda")
                                return True
                            else:
                                print(f"⚠ Failed to close ticket via Lambda: {close_result.get('statusCode')}")
                                return False
                        else:
                            print(f"⚠ Failed to add correspondence via Lambda: {result.get('statusCode')}")
                            return False
                    else:
                        print(f"⚠ Failed to get tickets via Lambda: {result.get('statusCode')}")
                        return False
                else:
                    print("⚠ Could not find support ticket Lambda function")
                    return False
                    
            except Exception as lambda_error:
                print(f"⚠ Lambda method failed: {lambda_error}")
                return False
                
    except Exception as e:
        print(f"⚠ Error closing ticket: {e}")
        return False


def close_multiple_tickets():
    """Close multiple tickets for both connectivity and performance issues when user exits."""
    ticket_subjects = [
        "ExampleCorp - Reporting down for Imaging Platform - Triaging using A2A",
        "ExampleCorp - Retransmission issues found for Imaging Platform - Triaging using A2A"
    ]
    
    print("\n🎫 Closing multiple support tickets...")
    
    for subject in ticket_subjects:
        print(f"\n📋 Processing ticket with subject: {subject}")
        success = close_ticket_by_subject(
            subject, 
            "Issues resolved by A2A_CollaboratorAgent - connectivity and performance restored"
        )
        if success:
            print(f"✅ Successfully closed ticket: {subject}")
        else:
            print(f"⚠ Failed to close ticket: {subject}")


def add_ticket_correspondence():
    """Add correspondence to the most recent support ticket indicating connectivity is restored."""
    try:
        # First check if connectivity has actually been restored
        connectivity_restored, path_analysis = check_connectivity_restored()
        if not connectivity_restored:
            print("⚠ Connectivity not restored yet - skipping correspondence update")
            print("💡 Please restore the security group rule first:")
            print("   aws ec2 authorize-security-group-ingress --group-id <SG-ID> --protocol tcp --port 3306 --cidr 10.1.0.0/16")
            return
        
        # Initialize AWS clients with region
        region = get_aws_region()
        ssm_client = boto3.client('ssm', region_name=region)
        lambda_client = boto3.client('lambda', region_name=region)
        
        print("\n🎫 Adding correspondence to support ticket...")
        
        # Try to get the support ticket API Gateway URL
        try:
            response = ssm_client.get_parameter(Name='/examplecorp/support/api-gateway-url')
            api_gateway_url = response['Parameter']['Value']
            print(f"✓ Found support API Gateway URL: {api_gateway_url}")
            
            # Get the most recent ticket
            import urllib.request
            req = urllib.request.Request(f"{api_gateway_url}/tickets")
            req.add_header('User-Agent', 'AgentCoreRuntime/1.0')
            req.add_header('Accept', 'application/json')
            
            print(f"🔍 Fetching tickets from: {api_gateway_url}/tickets")
            
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    result = json.loads(response.read().decode('utf-8'))
                    tickets = result.get('tickets', [])
                    print(f"✓ Retrieved {len(tickets)} tickets from API")
                    
                    if tickets:
                        # Find the most recent ticket with "ExampleCorp - Reporting down" in the subject
                        target_ticket = None
                        for ticket in sorted(tickets, key=lambda x: x.get('created_at', ''), reverse=True):
                            if "ExampleCorp - Reporting down for Imaging Platform - Triaging using A2A" in ticket.get('subject', ''):
                                target_ticket = ticket
                                break
                        
                        if not target_ticket:
                            print("⚠ No ticket found with subject 'ExampleCorp - Reporting down for Imaging Platform - Triaging using A2A'")
                            print("  Available tickets:")
                            for ticket in tickets[:3]:  # Show first 3 tickets
                                print(f"    - {ticket.get('id')}: {ticket.get('subject', 'No subject')}")
                            return
                        
                        ticket_id = target_ticket.get('id')
                        print(f"✓ Found ticket to update: {ticket_id} - {target_ticket.get('subject')}")
                        
                        # Create simple correspondence message with path analysis
                        base_message = "connectivity between reporting.examplecorp.com and database.examplecorp.com is restored for Imaging Platform"
                        
                        if path_analysis and path_analysis.get('path_analyses'):
                            # Show all path analysis entries from network insights with proper formatting
                            detailed_message = f"""{base_message}

The following path analysis were used to check and restore the connectivity :

"""
                            
                            for path_info in path_analysis['path_analyses']:
                                path_id = path_info.get('path_id', 'unknown')
                                status = path_info.get('status', 'unknown')
                                detailed_message += f"Path ID : {path_id} : Status : {status}\n\n"
                            
                            # Remove the last extra newline
                            detailed_message = detailed_message.rstrip()
                        else:
                            detailed_message = f"""{base_message}

The following path analysis were used to check and restore the connectivity :

Path ID : connectivity-check : Status : Reachable"""
                        
                        correspondence_data = {
                            "author": "A2A_CollaboratorAgent",
                            "message": detailed_message,
                            "message_type": "system"
                        }
                        
                        data = json.dumps(correspondence_data).encode('utf-8')
                        req = urllib.request.Request(
                            f"{api_gateway_url}/tickets/{ticket_id}/correspondence",
                            data=data,
                            headers={
                                'Content-Type': 'application/json',
                                'User-Agent': 'A2A_CollaboratorAgent/1.0'
                            }
                        )
                        req.get_method = lambda: 'POST'
                        
                        with urllib.request.urlopen(req, timeout=30) as response:
                            if response.status == 201:
                                print("✅ Successfully added correspondence to support ticket")
                                print("   Message: connectivity between reporting.examplecorp.com and database.examplecorp.com is restored for Imaging Platform")
                                print("   Author: A2A_CollaboratorAgent")
                                
                                # Now close the ticket using PUT method with correct payload structure
                                try:
                                    close_data = json.dumps({"status": "closed"}).encode('utf-8')
                                    close_req = urllib.request.Request(
                                        f"{api_gateway_url}/tickets/{ticket_id}",
                                        data=close_data,
                                        headers={
                                            'Content-Type': 'application/json',
                                            'User-Agent': 'A2A_CollaboratorAgent/1.0'
                                        }
                                    )
                                    close_req.get_method = lambda: 'PUT'
                                    
                                    with urllib.request.urlopen(close_req, timeout=30) as close_response:
                                        if close_response.status in [200, 204]:
                                            print("✅ Successfully closed support ticket")
                                        else:
                                            print(f"⚠ Failed to close ticket: HTTP {close_response.status}")
                                            # Read response body for debugging
                                            try:
                                                error_body = close_response.read().decode('utf-8')
                                                print(f"   Response body: {error_body}")
                                            except:
                                                pass
                                except Exception as close_error:
                                    print(f"⚠ Error closing ticket: {close_error}")
                            else:
                                print(f"⚠ API Gateway returned status {response.status}")
                    else:
                        print("⚠ No tickets found to update")
                else:
                    print(f"⚠ Failed to get tickets: HTTP {response.status}")
                    
        except Exception as api_error:
            print(f"⚠ API Gateway method failed: {api_error}")
            print("  Trying direct Lambda invocation...")
            
            # Fallback: Try Lambda function directly
            try:
                # Find the support ticket Lambda function
                functions_response = lambda_client.list_functions()
                support_function_name = None
                
                for func in functions_response.get('Functions', []):
                    func_name = func.get('FunctionName', '')
                    if 'support-ticket' in func_name.lower():
                        support_function_name = func_name
                        break
                
                if support_function_name:
                    print(f"✓ Found support ticket function: {support_function_name}")
                    
                    # Get tickets first
                    lambda_event = {
                        'path': '/tickets',
                        'httpMethod': 'GET',
                        'headers': {'Content-Type': 'application/json'}
                    }
                    
                    response = lambda_client.invoke(
                        FunctionName=support_function_name,
                        InvocationType='RequestResponse',
                        Payload=json.dumps(lambda_event)
                    )
                    
                    result = json.loads(response['Payload'].read().decode('utf-8'))
                    
                    if result.get('statusCode') == 200:
                        body = json.loads(result.get('body', '{}'))
                        tickets = body.get('tickets', [])
                        
                        if tickets:
                            # Find the most recent ticket with "ExampleCorp - Reporting down" in the subject
                            target_ticket = None
                            for ticket in sorted(tickets, key=lambda x: x.get('created_at', ''), reverse=True):
                                if "ExampleCorp - Reporting down for Imaging Platform - Triaging using A2A" in ticket.get('subject', ''):
                                    target_ticket = ticket
                                    break
                            
                            if not target_ticket:
                                print("⚠ No ticket found with subject 'ExampleCorp - Reporting down for Imaging Platform - Triaging using A2A'")
                                print("  Available tickets:")
                                for ticket in tickets[:3]:  # Show first 3 tickets
                                    print(f"    - {ticket.get('id')}: {ticket.get('subject', 'No subject')}")
                                return
                            
                            ticket_id = target_ticket.get('id')
                            print(f"✓ Found ticket to update: {ticket_id} - {target_ticket.get('subject')}")
                            
                            # Add correspondence via Lambda with path analysis
                            base_message = "connectivity between reporting.examplecorp.com and database.examplecorp.com is restored for Imaging Platform"
                            
                            if path_analysis and path_analysis.get('path_analyses'):
                                # Show all path analysis entries from network insights with proper formatting
                                detailed_message = f"""{base_message}

The following path analysis were used to check and restore the connectivity :

"""
                                
                                for path_info in path_analysis['path_analyses']:
                                    path_id = path_info.get('path_id', 'unknown')
                                    status = path_info.get('status', 'unknown')
                                    detailed_message += f"Path ID : {path_id} : Status : {status}\n\n"
                                
                                # Remove the last extra newline
                                detailed_message = detailed_message.rstrip()
                            else:
                                detailed_message = f"""{base_message}

The following path analysis were used to check and restore the connectivity :

Path ID : connectivity-check : Status : Reachable"""
                            
                            correspondence_data = {
                                "author": "A2A_CollaboratorAgent",
                                "message": detailed_message,
                                "message_type": "system"
                            }
                            
                            lambda_event = {
                                'path': f'/tickets/{ticket_id}/correspondence',
                                'httpMethod': 'POST',
                                'body': json.dumps(correspondence_data),
                                'headers': {'Content-Type': 'application/json'}
                            }
                            
                            response = lambda_client.invoke(
                                FunctionName=support_function_name,
                                InvocationType='RequestResponse',
                                Payload=json.dumps(lambda_event)
                            )
                            
                            result = json.loads(response['Payload'].read().decode('utf-8'))
                            
                            if result.get('statusCode') == 201:
                                print("✅ Successfully added correspondence to support ticket via Lambda")
                                print("   Message: connectivity between reporting.examplecorp.com and database.examplecorp.com is restored for Imaging Platform")
                                print("   Author: A2A_CollaboratorAgent")
                                
                                # Now close the ticket via Lambda using PUT method
                                try:
                                    close_event = {
                                        'path': f'/tickets/{ticket_id}',
                                        'httpMethod': 'PUT',
                                        'body': json.dumps({"status": "closed"}),
                                        'headers': {'Content-Type': 'application/json'}
                                    }
                                    
                                    close_response = lambda_client.invoke(
                                        FunctionName=support_function_name,
                                        InvocationType='RequestResponse',
                                        Payload=json.dumps(close_event)
                                    )
                                    
                                    close_result = json.loads(close_response['Payload'].read().decode('utf-8'))
                                    
                                    if close_result.get('statusCode') == 200:
                                        print("✅ Successfully closed support ticket via Lambda")
                                    else:
                                        print(f"⚠ Failed to close ticket via Lambda: {close_result.get('statusCode')}")
                                        print(f"   Error: {close_result.get('body')}")
                                        # Print more debugging info
                                        print(f"   Full response: {close_result}")
                                except Exception as close_error:
                                    print(f"⚠ Error closing ticket via Lambda: {close_error}")
                            else:
                                print(f"⚠ Lambda function returned status {result.get('statusCode')}")
                                print(f"   Error: {result.get('body')}")
                        else:
                            print("⚠ No tickets found to update")
                    else:
                        print(f"⚠ Failed to get tickets via Lambda: {result.get('statusCode')}")
                else:
                    print("⚠ Could not find support ticket Lambda function")
                    
            except Exception as lambda_error:
                print(f"⚠ Lambda invocation also failed: {lambda_error}")
                print("   Correspondence that would have been added:")
                print("   Message: connectivity between reporting.examplecorp.com and database.examplecorp.com is restored for Imaging Platform")
                print("   Author: A2A_CollaboratorAgent")
                
    except Exception as e:
        print(f"⚠ Failed to add ticket correspondence: {e}")
        print("   Correspondence that would have been added:")
        print("   Message: connectivity between reporting.examplecorp.com and database.examplecorp.com is restored for Imaging Platform")
        print("   Author: A2A_CollaboratorAgent")


def get_machine_access_token():
    """Get access token using client_credentials flow (M2M authentication)"""
    try:
        # Get machine client credentials from SSM
        client_id = get_ssm_parameter("/a2a/app/performance/agentcore/machine_client_id")
        client_secret = get_ssm_parameter("/a2a/app/performance/agentcore/machine_client_secret")
        token_url = get_ssm_parameter("/a2a/app/performance/agentcore/cognito_token_url")
        auth_scope = get_ssm_parameter("/a2a/app/performance/agentcore/cognito_auth_scope")
        
        print(f"🔐 Using machine client ID: {client_id}")
        print(f"🔗 Token URL: {token_url}")
        print(f"📋 Scope: {auth_scope}")
        
        # Request token using client_credentials flow
        response = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": auth_scope
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30
        )
        
        if response.status_code == 200:
            token_data = response.json()
            print("✅ Machine-to-machine token acquired successfully")
            return token_data["access_token"]
        else:
            print(f"❌ Failed to get M2M token: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting M2M token: {e}")
        return None


def invoke_endpoint(
    agent_arn: str,
    payload,
    session_id: str,
    bearer_token: str,
    endpoint_name: str = "DEFAULT",
) -> None:
    """Invoke the AgentCore runtime endpoint"""
    escaped_arn = urllib.parse.quote(agent_arn, safe="")
    url = f"https://bedrock-agentcore.{get_aws_region()}.amazonaws.com/runtimes/{escaped_arn}/invocations"

    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }

    try:
        body = json.loads(payload) if isinstance(payload, str) else payload
    except json.JSONDecodeError:
        body = {"payload": payload}

    try:
        print(f"🚀 Invoking agent with M2M authentication...")
        response = requests.post(
            url,
            params={"qualifier": endpoint_name},
            headers=headers,
            json=body,
            timeout=300,
            stream=True,
        )
        
        if response.status_code != 200:
            print(f"❌ Error response: {response.status_code} - {response.text}")
            return
        
        print(f"✅ Agent response (status {response.status_code}):")
        print("-" * 50)
        
        response_received = False
        
        # Process streaming response
        for line in response.iter_lines(chunk_size=8192, decode_unicode=True):
            if line:
                response_received = True
                
                if line.startswith("data: "):
                    content = line[6:].strip('"')
                    content = content.replace('\\n', '\n')
                    content = content.replace('\\"', '"')
                    content = content.replace('\\\\', '\\')
                    print(content, end="", flush=True)
                    
                elif line.strip() in ["data: [DONE]", "[DONE]"]:
                    print("\n", flush=True)
                    break
        
        if not response_received:
            print("⚠️  No response received from agent")

    except requests.exceptions.Timeout:
        print("⏰ Request timed out after 5 minutes")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to invoke agent endpoint: {str(e)}")
    except KeyboardInterrupt:
        print("\n🛑 Request interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")


def interactive_chat_session(agent_arn: str, bearer_token: str, session_id: str):
    """Start an interactive chat session with the agent using M2M authentication."""
    print(f"\n💬 Starting interactive M2M chat session...")
    print(f"🔗 Session ID: {session_id}")
    print("Type 'quit' or 'exit' to end the session")
    print("-" * 50)
    
    while True:
        try:
            user_input = input(f"\n👤 You: ").strip()
            
            if user_input.lower() in ['quit', 'exit']:
                print("\n👋 Ending chat session. Goodbye!")
                # Close multiple support tickets after session ends
                close_multiple_tickets()
                break
            elif not user_input:
                continue
            
            # Send message to agent
            invoke_endpoint(
                agent_arn=agent_arn,
                payload=json.dumps({"prompt": user_input, "actor_id": "DEFAULT"}),
                bearer_token=bearer_token,
                session_id=session_id,
            )
            
        except KeyboardInterrupt:
            print("\n\n👋 Chat session interrupted. Goodbye!")
            # Close multiple support tickets after session ends
            close_multiple_tickets()
            break
        except Exception as e:
            print(f"❌ Chat error: {e}")


@click.command()
@click.argument("agent_name", default="a2a_collaborator_agent_runtime")
@click.option("--prompt", "-p", default="Hello, can you help me coordinate network troubleshooting?", help="Prompt to send to the agent")
@click.option("--interactive", "-i", is_flag=True, help="Start interactive chat session")
def main(agent_name: str, prompt: str, interactive: bool):
    """CLI tool to test A2A Collaborator AgentCore using machine-to-machine authentication."""
    print(f"🤖 Testing agent with M2M authentication: {agent_name}")
    
    # Read runtime configuration
    runtime_config = read_config(".bedrock_agentcore.yaml")
    print(f"📖 Available agents: {list(runtime_config['agents'].keys())}")

    if agent_name not in runtime_config["agents"]:
        print(f"❌ Agent '{agent_name}' not found in config.")
        print(f"💡 Available agents: {', '.join(runtime_config['agents'].keys())}")
        sys.exit(1)
    
    print(f"✅ Found agent: {agent_name}")

    # Get machine-to-machine access token
    access_token = get_machine_access_token()
    if not access_token:
        print("❌ Failed to get M2M access token")
        sys.exit(1)

    # Get agent ARN and create session
    agent_arn = runtime_config["agents"][agent_name]["bedrock_agentcore"]["agent_arn"]
    session_id = str(uuid.uuid4())
    
    print(f"🔗 Agent ARN: {agent_arn}")
    print(f"🆔 Session ID: {session_id}")

    if interactive:
        # Start interactive chat session
        interactive_chat_session(
            agent_arn=agent_arn,
            bearer_token=access_token,
            session_id=session_id,
        )
    else:
        # Single message mode
        invoke_endpoint(
            agent_arn=agent_arn,
            payload=json.dumps({"prompt": prompt, "actor_id": "DEFAULT"}),
            bearer_token=access_token,
            session_id=session_id,
        )


if __name__ == "__main__":
    main()
