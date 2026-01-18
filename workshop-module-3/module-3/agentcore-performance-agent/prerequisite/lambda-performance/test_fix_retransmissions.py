#!/usr/bin/env python3
"""
Integration test for fix_retransmissions Lambda function tool.

This test invokes the Lambda function with the fix_retransmissions tool
to test the functionality in the specified AWS account and region.

Usage:
    python test_fix_retransmissions.py [--instance-id INSTANCE_ID] [--stack-name STACK_NAME]

Requirements:
    - AWS credentials configured (via AWS CLI or environment variables)
    - Lambda function deployed and accessible
    - Appropriate IAM permissions to invoke Lambda
"""

import json
import boto3
import argparse
import sys
from datetime import datetime

# Configuration
DEFAULT_REGION = 'us-east-1'
DEFAULT_ACCOUNT_ID = '104398007905'
DEFAULT_STACK_NAME = 'acme-image-gallery-perf'
LAMBDA_FUNCTION_NAME = 'a2a-performance-tools'  # Update this to match your Lambda function name


def get_lambda_function_name():
    """Get the Lambda function name from CloudFormation stack or use default."""
    try:
        cfn_client = boto3.client('cloudformation', region_name=DEFAULT_REGION)
        
        # Try to get Lambda function name from CloudFormation stack
        response = cfn_client.describe_stacks(StackName='performance-tools-stack')
        
        if response['Stacks']:
            outputs = response['Stacks'][0].get('Outputs', [])
            for output in outputs:
                if output['OutputKey'] == 'LambdaFunctionName':
                    return output['OutputValue']
    except Exception as e:
        print(f"⚠️  Could not get Lambda function name from CloudFormation: {e}")
    
    return LAMBDA_FUNCTION_NAME


def invoke_fix_retransmissions(instance_id=None, stack_name=DEFAULT_STACK_NAME, region=DEFAULT_REGION):
    """
    Invoke the Lambda function with fix_retransmissions tool.
    
    Args:
        instance_id: EC2 instance ID to fix (optional - auto-detects if not provided)
        stack_name: CloudFormation stack name to find bastion server
        region: AWS region
    
    Returns:
        dict: Lambda function response
    """
    print("=" * 80)
    print("🧪 Fix Retransmissions Integration Test")
    print("=" * 80)
    print(f"📅 Test started at: {datetime.now().isoformat()}")
    print(f"🌍 Region: {region}")
    print(f"🔑 Account ID: {DEFAULT_ACCOUNT_ID}")
    print(f"📚 Stack name: {stack_name}")
    if instance_id:
        print(f"🖥️  Instance ID: {instance_id}")
    else:
        print(f"🖥️  Instance ID: Auto-detect from stack")
    print()
    
    # Create Lambda client
    lambda_client = boto3.client('lambda', region_name=region)
    
    # Get Lambda function name
    function_name = get_lambda_function_name()
    print(f"🔧 Lambda function: {function_name}")
    print()
    
    # Prepare the event payload for fix_retransmissions tool
    event = {
        "method": "tools/call",
        "params": {
            "name": "fix_retransmissions",
            "arguments": {
                "region": region
            }
        }
    }
    
    # Add optional parameters
    if instance_id:
        event["params"]["arguments"]["instance_id"] = instance_id
    if stack_name:
        event["params"]["arguments"]["stack_name"] = stack_name
    
    print("📤 Invoking Lambda function with payload:")
    print(json.dumps(event, indent=2))
    print()
    
    try:
        # Invoke Lambda function
        print("🚀 Invoking Lambda function...")
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(event)
        )
        
        # Parse response
        status_code = response['StatusCode']
        print(f"📊 Lambda invocation status code: {status_code}")
        
        # Read and parse the response payload
        response_payload = json.loads(response['Payload'].read())
        
        print()
        print("=" * 80)
        print("📥 Lambda Response:")
        print("=" * 80)
        print(json.dumps(response_payload, indent=2, default=str))
        print()
        
        # Check if the tool execution was successful
        if 'content' in response_payload:
            # MCP protocol response
            content = response_payload['content']
            if isinstance(content, list) and len(content) > 0:
                result_text = content[0].get('text', '')
                try:
                    result = json.loads(result_text)
                    print("=" * 80)
                    print("✅ Tool Execution Result:")
                    print("=" * 80)
                    print(f"Status: {result.get('status', 'unknown')}")
                    print(f"Issue Fixed: {result.get('issue_fixed', 'unknown')}")
                    print(f"Instance ID: {result.get('instance_id', 'unknown')}")
                    print(f"Fix Status: {result.get('fix_status', 'unknown')}")
                    print(f"SSM Command ID: {result.get('ssm_command_id', 'unknown')}")
                    
                    if 'tcp_settings_restored' in result:
                        print()
                        print("🔧 TCP Settings Restored:")
                        for key, value in result['tcp_settings_restored'].items():
                            print(f"  - {key}: {value}")
                    
                    if 'next_steps' in result:
                        print()
                        print("📋 Next Steps:")
                        for step in result['next_steps']:
                            print(f"  - {step}")
                    
                    if result.get('status') == 'success':
                        print()
                        print("✅ TEST PASSED: fix_retransmissions executed successfully!")
                        return 0
                    else:
                        print()
                        print("❌ TEST FAILED: fix_retransmissions execution failed")
                        if 'error' in result:
                            print(f"Error: {result['error']}")
                        return 1
                        
                except json.JSONDecodeError:
                    print(f"⚠️  Could not parse result as JSON: {result_text}")
                    return 1
        elif 'error' in response_payload:
            print("=" * 80)
            print("❌ Lambda Error:")
            print("=" * 80)
            print(f"Error: {response_payload['error']}")
            return 1
        else:
            # Direct response (legacy format)
            if response_payload.get('status') == 'success':
                print("✅ TEST PASSED: fix_retransmissions executed successfully!")
                return 0
            else:
                print("❌ TEST FAILED: fix_retransmissions execution failed")
                if 'error' in response_payload:
                    print(f"Error: {response_payload['error']}")
                return 1
        
    except Exception as e:
        print()
        print("=" * 80)
        print("💥 Test Execution Error:")
        print("=" * 80)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print()
        print("❌ TEST FAILED: Exception during Lambda invocation")
        return 1


def main():
    """Main test execution function."""
    parser = argparse.ArgumentParser(
        description='Integration test for fix_retransmissions Lambda function tool'
    )
    parser.add_argument(
        '--instance-id',
        help='EC2 instance ID to fix (optional - auto-detects bastion server if not provided)'
    )
    parser.add_argument(
        '--stack-name',
        default=DEFAULT_STACK_NAME,
        help=f'CloudFormation stack name (default: {DEFAULT_STACK_NAME})'
    )
    parser.add_argument(
        '--region',
        default=DEFAULT_REGION,
        help=f'AWS region (default: {DEFAULT_REGION})'
    )
    
    args = parser.parse_args()
    
    # Run the test
    exit_code = invoke_fix_retransmissions(
        instance_id=args.instance_id,
        stack_name=args.stack_name,
        region=args.region
    )
    
    print()
    print("=" * 80)
    print(f"📅 Test completed at: {datetime.now().isoformat()}")
    print("=" * 80)
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
