#!/usr/bin/env python3
"""
Break Script - Remove RDS Security Group Rule and Create Support Ticket

This script:
1. Finds the RDS instance and its associated security group
2. Removes the security group rule that allows Reporting VPC CIDR (10.1.0.0/16)
3. Creates a support ticket for the issue

Usage: python3 break-script.py
"""

import boto3
import json
import sys
import time
from datetime import datetime

def main():
    print("=" * 60)
    print("ExampleCorp Break Script - Simulating Reporting Connectivity Issue")
    print("=" * 60)
    
    # Initialize AWS clients
    try:
        # Set default region to us-east-1
        region = 'us-east-1'
        ec2_client = boto3.client('ec2', region_name=region)
        rds_client = boto3.client('rds', region_name=region)
        print(f"✓ AWS clients initialized successfully (region: {region})")
    except Exception as e:
        print(f"✗ Failed to initialize AWS clients: {e}")
        sys.exit(1)
    
    # Step 1: Find RDS instances and their security groups
    print("\n1. Finding RDS instances...")
    try:
        rds_response = rds_client.describe_db_instances()
        db_instances = rds_response.get('DBInstances', [])
        
        if not db_instances:
            print("✗ No RDS instances found")
            sys.exit(1)
        
        target_db = None
        for db in db_instances:
            db_id = db.get('DBInstanceIdentifier', '')
            if 'sample-app' in db_id or 'image-metadata' in db_id:
                target_db = db
                break
        
        if not target_db:
            # Use the first DB instance if no specific match
            target_db = db_instances[0]
        
        db_identifier = target_db.get('DBInstanceIdentifier')
        vpc_security_groups = target_db.get('VpcSecurityGroups', [])
        
        print(f"✓ Found RDS instance: {db_identifier}")
        print(f"  Security groups: {len(vpc_security_groups)}")
        
    except Exception as e:
        print(f"✗ Failed to describe RDS instances: {e}")
        sys.exit(1)
    
    # Step 2: Find the target security group
    print("\n2. Finding target security group...")
    target_sg_id = None
    
    try:
        # Get all security groups and find the one with "DatabaseSecurityGroup" in the name
        sg_response = ec2_client.describe_security_groups()
        security_groups = sg_response.get('SecurityGroups', [])
        
        for sg in security_groups:
            sg_name = sg.get('GroupName', '')
            sg_id = sg.get('GroupId', '')
            
            if 'sample-application-DatabaseSecurityGroup' in sg_name:
                target_sg_id = sg_id
                print(f"✓ Found target security group: {sg_id} ({sg_name})")
                break
        
        if not target_sg_id:
            # Fallback: use security groups from RDS instance
            for vpc_sg in vpc_security_groups:
                sg_id = vpc_sg.get('VpcSecurityGroupId')
                if sg_id:
                    # Check if this SG has the reporting VPC rule
                    sg_details = ec2_client.describe_security_groups(GroupIds=[sg_id])
                    sg_info = sg_details['SecurityGroups'][0]
                    
                    for rule in sg_info.get('IpPermissions', []):
                        for ip_range in rule.get('IpRanges', []):
                            if ip_range.get('CidrIp') == '10.1.0.0/16':
                                target_sg_id = sg_id
                                print(f"✓ Found security group with Reporting VPC rule: {sg_id}")
                                break
                        if target_sg_id:
                            break
                    if target_sg_id:
                        break
        
        if not target_sg_id:
            print("✗ Could not find target security group with Reporting VPC rule")
            sys.exit(1)
            
    except Exception as e:
        print(f"✗ Failed to find security groups: {e}")
        sys.exit(1)
    
    # Step 3: Get current security group rules
    print("\n3. Analyzing current security group rules...")
    try:
        sg_details = ec2_client.describe_security_groups(GroupIds=[target_sg_id])
        sg_info = sg_details['SecurityGroups'][0]
        
        print(f"  Security Group: {sg_info.get('GroupName')} ({target_sg_id})")
        print(f"  Description: {sg_info.get('Description')}")
        
        # Find any rule that allows IP-based access to MySQL port 3306
        target_rules = []
        for rule in sg_info.get('IpPermissions', []):
            protocol = rule.get('IpProtocol')
            from_port = rule.get('FromPort')
            to_port = rule.get('ToPort')
            
            # Look for MySQL/Aurora port (3306) rules
            if protocol == 'tcp' and from_port == 3306 and to_port == 3306:
                ip_ranges = rule.get('IpRanges', [])
                if ip_ranges:  # Has IP-based rules
                    for ip_range in ip_ranges:
                        cidr = ip_range.get('CidrIp')
                        if cidr:
                            target_rule = {
                                'IpProtocol': protocol,
                                'FromPort': from_port,
                                'ToPort': to_port,
                                'IpRanges': [{'CidrIp': cidr}]
                            }
                            target_rules.append(target_rule)
                            print(f"✓ Found MySQL rule: {protocol} {from_port}-{to_port} from {cidr}")
        
        if not target_rules:
            print("✗ Could not find any IP-based rules allowing MySQL access (port 3306)")
            sys.exit(1)
        
        print(f"  Total rules to remove: {len(target_rules)}")
            
    except Exception as e:
        print(f"✗ Failed to analyze security group rules: {e}")
        sys.exit(1)
    
    # Step 4: Remove the security group rules
    print("\n4. Removing security group rules...")
    removed_rules = []
    try:
        for i, rule in enumerate(target_rules, 1):
            cidr = rule['IpRanges'][0]['CidrIp']
            print(f"  Removing rule {i}/{len(target_rules)}: {rule['IpProtocol']} {rule['FromPort']}-{rule['ToPort']} from {cidr}")
            
            ec2_client.revoke_security_group_ingress(
                GroupId=target_sg_id,
                IpPermissions=[rule]
            )
            removed_rules.append(cidr)
            print(f"    ✓ Rule removed successfully")
        
        print(f"✓ All {len(target_rules)} security group rules removed successfully")
        print("  This will break connectivity to the database from the removed CIDR blocks")
        
    except Exception as e:
        print(f"✗ Failed to remove security group rule: {e}")
        sys.exit(1)
    
    # Step 5: Create support ticket
    print("\n5. Creating support ticket...")
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
        
        # Create ticket data
        ticket_data = {
            "subject": "ExampleCorp - Reporting down for Imaging Platform - Triaging using A2A",
            "priority": "medium",
            "description": "Reporting is broken for Imaging Platform. Need Investigation."
        }
        
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
                    'User-Agent': 'ExampleCorp-Break-Script/1.0'
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
                else:
                    print(f"⚠ Lambda function returned status {result.get('statusCode')}")
                    print(f"  Error: {result.get('body')}")
            else:
                print("⚠ Could not find support ticket Lambda function")
                print("  Ticket details that would have been created:")
                print(f"    Subject: {ticket_data['subject']}")
                print(f"    Priority: {ticket_data['priority']}")
                print(f"    Description: {ticket_data['description']}")
                
        except Exception as lambda_error:
            print(f"⚠ Lambda invocation also failed: {lambda_error}")
            print("  Ticket details that would have been created:")
            print(f"    Subject: {ticket_data['subject']}")
            print(f"    Priority: {ticket_data['priority']}")
            print(f"    Description: {ticket_data['description']}")
    
    # Step 6: Summary
    print("\n" + "=" * 60)
    print("BREAK SCRIPT EXECUTION SUMMARY")
    print("=" * 60)
    print(f"✓ Successfully removed {len(removed_rules)} security group rule(s)")
    print(f"  Security Group: {target_sg_id}")
    for cidr in removed_rules:
        print(f"  Removed Rule: MySQL/Aurora (3306) from {cidr}")
    print("")
    print("✓ Support ticket creation attempted")
    print(f"  Title: ExampleCorp - Reporting down for Imaging Platform")
    print(f"  Priority: Medium")
    print(f"  Description: Reporting is broken for Imaging Platform. Needed Investigation.")
    print("")
    print("IMPACT:")
    print("- Database connectivity broken from the following CIDR blocks:")
    for cidr in removed_rules:
        print(f"  • {cidr}")
    print("- Analytics reports will fail to generate")
    print("- Users will see errors when trying to view reports")
    print("")
    print("TO RESTORE:")
    print("1. Add back the security group rules:")
    for cidr in removed_rules:
        print(f"   aws ec2 authorize-security-group-ingress --group-id {target_sg_id} \\")
        print(f"     --protocol tcp --port 3306 --cidr {cidr}")
    print("2. Or use the AWS Console to add the rules back manually")
    print("")
    print(f"Execution completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

if __name__ == "__main__":
    main()
