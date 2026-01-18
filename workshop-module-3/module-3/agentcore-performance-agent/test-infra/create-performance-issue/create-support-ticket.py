#!/usr/bin/env python3
"""
Support Ticket Creation Script

This script creates a support ticket using the ExampleCorp support system.
The ticket data can be customized by modifying the ticket_data dictionary.

Usage: python3 create-support-ticket.py
"""

import boto3
import json
import sys
from datetime import datetime

def create_support_ticket(ticket_data):
    """
    Create a support ticket using API Gateway or Lambda fallback
    
    Args:
        ticket_data (dict): Dictionary containing ticket information
                           Required keys: subject, priority, description
    
    Returns:
        dict: Result of ticket creation with success status and ticket info
    """
    region = 'us-east-1'
    
    try:
        # Try to find the support ticket API Gateway URL from SSM
        ssm_client = boto3.client('ssm', region_name=region)
        
        try:
            response = ssm_client.get_parameter(Name='/examplecorp/support/api-gateway-url')
            api_gateway_url = response['Parameter']['Value']
            print(f"✓ Found support API Gateway URL: {api_gateway_url}")
        except:
            print("⚠ Could not find support API Gateway URL in SSM, will use Lambda function directly")
            api_gateway_url = None
        
        if api_gateway_url:
            # Use API Gateway
            import urllib.request
            import urllib.parse
            
            data = json.dumps(ticket_data).encode('utf-8')
            req = urllib.request.Request(
                f"{api_gateway_url}/tickets",
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'ExampleCorp-Support-Ticket-Script/1.0'
                }
            )
            
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 201:
                        result = json.loads(response.read().decode('utf-8'))
                        ticket = result.get('ticket', {})
                        ticket_id = ticket.get('id', 'Unknown')
                        print(f"✓ Support ticket created successfully via API Gateway")
                        print(f"  Ticket ID: {ticket_id}")
                        print(f"  Subject: {ticket.get('subject')}")
                        print(f"  Priority: {ticket.get('priority')}")
                        return {
                            'success': True,
                            'method': 'API Gateway',
                            'ticket_id': ticket_id,
                            'ticket': ticket
                        }
                    else:
                        print(f"⚠ API Gateway returned status {response.status}")
                        raise Exception("API Gateway error")
            except Exception as api_error:
                print(f"⚠ API Gateway failed: {api_error}")
                print("  Falling back to direct Lambda invocation...")
                raise Exception("API fallback needed")
        else:
            raise Exception("No API Gateway URL")
            
    except Exception as e:
        # Fallback: Try to invoke Lambda function directly
        try:
            lambda_client = boto3.client('lambda', region_name=region)
            
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
                
                # Invoke the Lambda function
                lambda_event = {
                    'path': '/tickets',
                    'httpMethod': 'POST',
                    'body': json.dumps(ticket_data),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = lambda_client.invoke(
                    FunctionName=support_function_name,
                    InvocationType='RequestResponse',
                    Payload=json.dumps(lambda_event)
                )
                
                result = json.loads(response['Payload'].read().decode('utf-8'))
                
                if result.get('statusCode') == 201:
                    body = json.loads(result.get('body', '{}'))
                    ticket = body.get('ticket', {})
                    ticket_id = ticket.get('id', 'Unknown')
                    print(f"✓ Support ticket created successfully via Lambda")
                    print(f"  Ticket ID: {ticket_id}")
                    print(f"  Subject: {ticket.get('subject')}")
                    print(f"  Priority: {ticket.get('priority')}")
                    return {
                        'success': True,
                        'method': 'Lambda',
                        'ticket_id': ticket_id,
                        'ticket': ticket
                    }
                else:
                    print(f"⚠ Lambda function returned status {result.get('statusCode')}")
                    print(f"  Error: {result.get('body')}")
                    return {
                        'success': False,
                        'method': 'Lambda',
                        'error': result.get('body')
                    }
            else:
                print("⚠ Could not find support ticket Lambda function")
                print("  Ticket details that would have been created:")
                print(f"    Subject: {ticket_data['subject']}")
                print(f"    Priority: {ticket_data['priority']}")
                print(f"    Description: {ticket_data['description']}")
                return {
                    'success': False,
                    'method': 'None',
                    'error': 'No Lambda function found',
                    'ticket_data': ticket_data
                }
                
        except Exception as lambda_error:
            print(f"⚠ Lambda invocation also failed: {lambda_error}")
            print("  Ticket details that would have been created:")
            print(f"    Subject: {ticket_data['subject']}")
            print(f"    Priority: {ticket_data['priority']}")
            print(f"    Description: {ticket_data['description']}")
            return {
                'success': False,
                'method': 'Lambda',
                'error': str(lambda_error),
                'ticket_data': ticket_data
            }

def main():
    print("=" * 60)
    print("ExampleCorp Support Ticket Creation Script")
    print("=" * 60)
    
    # Initialize AWS clients
    try:
        region = 'us-east-1'
        print(f"✓ Using AWS region: {region}")
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        sys.exit(1)
    
    # Create ticket data
    ticket_data = {
        "subject": "ExampleCorp - Retransmission issues found for Imaging Platform - Triaging using A2A",
        "priority": "medium",
        "description": "Reporting Application is experiencing performance degradation. Need Investigation."
    }
    
    print("\nTicket Information:")
    print(f"  Subject: {ticket_data['subject']}")
    print(f"  Priority: {ticket_data['priority']}")
    print(f"  Description: {ticket_data['description']}")
    
    # Create the support ticket
    print("\nCreating support ticket...")
    result = create_support_ticket(ticket_data)
    
    # Display results
    print("\n" + "=" * 60)
    print("SUPPORT TICKET CREATION SUMMARY")
    print("=" * 60)
    
    if result['success']:
        print(f"✓ Support ticket created successfully via {result['method']}")
        print(f"  Ticket ID: {result['ticket_id']}")
        if 'ticket' in result:
            ticket = result['ticket']
            print(f"  Subject: {ticket.get('subject', 'N/A')}")
            print(f"  Priority: {ticket.get('priority', 'N/A')}")
            print(f"  Status: {ticket.get('status', 'N/A')}")
            print(f"  Created: {ticket.get('created_at', 'N/A')}")
    else:
        print(f"⚠ Support ticket creation failed")
        print(f"  Method attempted: {result['method']}")
        print(f"  Error: {result.get('error', 'Unknown error')}")
        if 'ticket_data' in result:
            print("\n  Ticket data that was attempted:")
            for key, value in result['ticket_data'].items():
                print(f"    {key}: {value}")
    
    print(f"\nExecution completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

if __name__ == "__main__":
    main()
