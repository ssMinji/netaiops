"""
Test 3: Store Platform Knowledge in Semantic Memory
Tests storing actual AWS platform architecture and resource information for long-term retention
"""
import pytest
import pytest_asyncio
import sys
import os
import boto3
import requests
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_config.memory_hook_provider import MemoryHookProvider


def get_image_processing_platform_architecture():
    """Discover Image Processing Application platform architecture from CloudFormation exports"""
    try:
        cf_client = boto3.client('cloudformation', region_name='us-east-1')
        
        # Get CloudFormation stack exports
        exports_response = cf_client.list_exports()
        exports = {export['Name']: export['Value'] for export in exports_response.get('Exports', [])}
        
        # Extract EXAMPLECORP platform components from exports
        examplecorp_architecture = {
            'application_url': exports.get('sample-application-ApplicationURL', 'http://sample-app-ALB-497187371.us-east-1.elb.amazonaws.com'),
            'private_app_url': exports.get('sample-application-PrivateApplicationURL', 'http://app.examplecorp.internal'),
            'app_vpc_id': exports.get('sample-application-AppVPCId', 'vpc-04666b31154492ffb'),
            'reporting_vpc_id': exports.get('sample-application-ReportingVPCId', 'vpc-0e37e2bd63a9fa29d'),
            'transit_gateway_id': exports.get('sample-application-TransitGatewayId', 'tgw-0ee317183d30aedbc'),
            'bastion_instance_id': exports.get('sample-application-BastionInstanceId', 'i-0a5bf7a649376dfc3'),
            'reporting_instance_id': exports.get('sample-application-ReportingInstanceId', 'i-0a44e3665fbb8a2ae'),
            'database_endpoint': exports.get('sample-application-DatabaseEndpoint', 'sample-app-image-metadata-db.cq1m6mcym3q2.us-east-1.rds.amazonaws.com'),
            'private_db_url': exports.get('sample-application-PrivateDatabaseURL', 'db.examplecorp.internal'),
            's3_bucket': exports.get('sample-application-S3BucketName', 'sample-app-064190739430-image-sample-application-us-east-1'),
            'lambda_functions': {
                'html_renderer': exports.get('sample-application-HTMLRenderingFunctionArn', 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-html-renderer-sample-application'),
                'image_processor': exports.get('sample-application-ImageProcessingFunctionArn', 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-image-processor'),
                'user_interactions': exports.get('sample-application-UserInteractionFunctionArn', 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-user-interactions'),
                'support_ticket': exports.get('sample-application-SupportTicketFunctionArn', 'arn:aws:lambda:us-east-1:064190739430:function:sample-application-support-ticket-handler')
            },
            'api_gateway_url': exports.get('sample-application-SupportTicketApiGatewayURL', 'https://j2ncvx616k.execute-api.us-east-1.amazonaws.com/prod'),
            'hosted_zone_id': exports.get('sample-application-PrivateHostedZoneId', 'Z06463652R4W29ZXKLU68'),
            'region': 'us-east-1'
        }
        
        return examplecorp_architecture
        
    except Exception as e:
        print(f"   ⚠️  Could not discover EXAMPLECORP platform architecture: {e}")
        # Return fallback values from known EXAMPLECORP platform
        return {
            'application_url': 'http://sample-app-ALB-497187371.us-east-1.elb.amazonaws.com',
            'private_app_url': 'http://app.examplecorp.internal',
            'app_vpc_id': 'vpc-04666b31154492ffb',
            'reporting_vpc_id': 'vpc-0e37e2bd63a9fa29d',
            'transit_gateway_id': 'tgw-0ee317183d30aedbc',
            'bastion_instance_id': 'i-0a5bf7a649376dfc3',
            'reporting_instance_id': 'i-0a44e3665fbb8a2ae',
            'database_endpoint': 'sample-app-image-metadata-db.cq1m6mcym3q2.us-east-1.rds.amazonaws.com',
            'private_db_url': 'db.examplecorp.internal',
            's3_bucket': 'sample-app-064190739430-image-sample-application-us-east-1',
            'lambda_functions': {
                'html_renderer': 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-html-renderer-sample-application',
                'image_processor': 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-image-processor',
                'user_interactions': 'arn:aws:lambda:us-east-1:064190739430:function:sample-app-user-interactions',
                'support_ticket': 'arn:aws:lambda:us-east-1:064190739430:function:sample-application-support-ticket-handler'
            },
            'api_gateway_url': 'https://j2ncvx616k.execute-api.us-east-1.amazonaws.com/prod',
            'hosted_zone_id': 'Z06463652R4W29ZXKLU68',
            'region': 'us-east-1'
        }


@pytest.mark.asyncio
async def test_store_platform_architecture_knowledge(memory_hook):
    """Test storing actual AWS platform architecture knowledge in semantic memory (LONG-TERM)"""
    print("\n" + "="*80)
    print("🧪 TEST 3: STORING PLATFORM ARCHITECTURE KNOWLEDGE")
    print("="*80)
    
    # Discover Image Processing Application platform architecture from CloudFormation exports
    platform = get_image_processing_platform_architecture()
    
    print(f"🔍 DISCOVERED IMAGE PROCESSING PLATFORM:")
    print(f"   📍 Region: {platform['region']}")
    print(f"   🌐 Application URL: {platform['application_url']}")
    print(f"   🏢 App VPC: {platform['app_vpc_id']}")
    print(f"   📊 Reporting VPC: {platform['reporting_vpc_id']}")
    print(f"   🔗 Transit Gateway: {platform['transit_gateway_id']}")
    print(f"   🖥️  Bastion Instance: {platform['bastion_instance_id']}")
    print(f"   📈 Reporting Instance: {platform['reporting_instance_id']}")
    print(f"   🗄️  Database: {platform['database_endpoint']}")
    print(f"   📦 S3 Bucket: {platform['s3_bucket']}")
    print(f"   ⚡ Lambda Functions: {len(platform['lambda_functions'])} functions")
    
    # Create meaningful platform knowledge content
    platform_knowledge = f"""
    Image Processing Application Platform Architecture (CloudFormation Exports):
    
    Application Infrastructure:
    - Public URL: {platform['application_url']}
    - Private URL: {platform['private_app_url']}
    - Application VPC: {platform['app_vpc_id']}
    - Reporting VPC: {platform['reporting_vpc_id']}
    - Transit Gateway: {platform['transit_gateway_id']}
    
    Compute Resources:
    - Bastion Instance: {platform['bastion_instance_id']} (App VPC)
    - Reporting Instance: {platform['reporting_instance_id']} (Reporting VPC)
    
    Data Layer:
    - Database Endpoint: {platform['database_endpoint']}
    - Private DB URL: {platform['private_db_url']}
    - S3 Image Storage: {platform['s3_bucket']}
    
    Lambda Functions:
    - HTML Renderer: {platform['lambda_functions']['html_renderer']}
    - Image Processor: {platform['lambda_functions']['image_processor']}
    - User Interactions: {platform['lambda_functions']['user_interactions']}
    - Support Tickets: {platform['lambda_functions']['support_ticket']}
    
    API & DNS:
    - Support API: {platform['api_gateway_url']}
    - Private Hosted Zone: {platform['hosted_zone_id']}
    
    Troubleshooting Context:
    - Cross-VPC connectivity via Transit Gateway
    - Database connectivity from Reporting VPC to App VPC
    - Lambda function connectivity to RDS and S3
    - DNS resolution via Route 53 private hosted zone
    """
    
    knowledge_metadata = {
        "knowledge_type": "platform_architecture",
        "platform": "image_processing_application",
        "region": platform['region'],
        "app_vpc_id": platform['app_vpc_id'],
        "reporting_vpc_id": platform['reporting_vpc_id'],
        "transit_gateway_id": platform['transit_gateway_id'],
        "bastion_instance_id": platform['bastion_instance_id'],
        "reporting_instance_id": platform['reporting_instance_id'],
        "database_endpoint": platform['database_endpoint'],
        "s3_bucket": platform['s3_bucket'],
        "lambda_functions_count": len(platform['lambda_functions']),
        "discovery_method": "cloudformation_exports",
        "discovery_timestamp": datetime.now().isoformat()
    }
    
    print(f"📝 STORING CONTENT: Image Processing Application platform with {len(platform['lambda_functions'])} Lambda functions")
    print(f"🏷️  METADATA: {knowledge_metadata}")
    print(f"🎯 STRATEGY: semantic (long-term memory)")
    print(f"🔗 MEMORY ID: {memory_hook.memory_id}")
    
    # Store platform knowledge
    store_result = await memory_hook.store_memory(
        strategy="semantic",
        content=platform_knowledge,
        metadata=knowledge_metadata
    )
    
    print(f"✅ STORAGE RESULT: {store_result}")
    print(f"📊 STATUS: {store_result.get('status', 'unknown')}")
    
    if store_result.get('status') == 'stored':
        print("🎉 SUCCESS: Platform architecture knowledge stored in semantic memory!")
        print("💡 This enables instant access to current environment details during troubleshooting")
        print("🚀 BUSINESS IMPACT: Eliminates need to rediscover infrastructure during incidents")
    else:
        print(f"❌ FAILED: {store_result.get('error', 'Unknown error')}")
    
    print("=" * 80)
    
    assert store_result and store_result.get('status') == 'stored'


@pytest.mark.asyncio
async def test_retrieve_platform_knowledge(memory_hook):
    """Test retrieving stored platform knowledge for troubleshooting context"""
    print("\n" + "="*80)
    print("🧪 TEST 3B: RETRIEVING PLATFORM ARCHITECTURE KNOWLEDGE")
    print("="*80)
    
    query = "platform architecture security groups instances VPC troubleshooting"
    print(f"🔍 SEARCHING FOR: {query}")
    print(f"🎯 STRATEGY: semantic (long-term memory)")
    print(f"🔗 MEMORY ID: {memory_hook.memory_id}")
    
    # Retrieve platform knowledge
    retrieve_result = await memory_hook.retrieve_memory(
        strategy="semantic",
        query=query,
        max_results=3
    )
    
    print(f"📊 RETRIEVAL RESULT: {retrieve_result}")
    print(f"📈 FOUND {len(retrieve_result) if retrieve_result else 0} memories")
    
    if retrieve_result:
        for i, result in enumerate(retrieve_result):
            content = result.get('content', '')
            print(f"📄 Memory {i+1}: {content[:150]}...")
            metadata = result.get('metadata', {})
            if metadata:
                print(f"   🏷️  Region: {metadata.get('region', 'unknown')}")
                print(f"   🏷️  VPC: {metadata.get('vpc_id', 'unknown')}")
                print(f"   🏷️  Security Groups: {metadata.get('security_groups_count', 0)}")
                print(f"   🏷️  Instances: {metadata.get('instances_count', 0)}")
    
    success = (
        retrieve_result and 
        len(retrieve_result) > 0 and
        any("architecture" in str(result).lower() for result in retrieve_result)
    )
    
    if success:
        print("🎉 SUCCESS: Platform architecture knowledge retrieved successfully!")
        print("💡 This proves the agent can instantly access environment details")
        print("🚀 BUSINESS IMPACT: Faster incident resolution through retained infrastructure knowledge")
    else:
        print("❌ FAILED: Could not retrieve platform architecture knowledge")
    
    print("=" * 80)
    
    assert success, f"Platform knowledge retrieval failed. Retrieved: {retrieve_result}"


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        memory_hook = MemoryHookProvider()
        await test_store_platform_architecture_knowledge(memory_hook)
        await test_retrieve_platform_knowledge(memory_hook)
    
    asyncio.run(run_tests())
