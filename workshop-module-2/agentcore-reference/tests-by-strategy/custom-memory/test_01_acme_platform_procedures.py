"""
Test 1: EXAMPLECORP Platform Procedures
Tests storing and retrieving EXAMPLECORP-specific troubleshooting procedures and workflows
"""
import pytest
import pytest_asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_config.memory_hook_provider import MemoryHookProvider


@pytest_asyncio.fixture
async def memory_hook():
    """Fixture to provide memory hook provider"""
    return MemoryHookProvider()


@pytest.mark.asyncio
async def test_examplecorp_platform_procedures(memory_hook):
    """Test storing EXAMPLECORP-specific troubleshooting procedures"""
    print("\n" + "="*80)
    print("🧪 CUSTOM MEMORY TEST 1: EXAMPLECORP PLATFORM PROCEDURES")
    print("="*80)
    
    # Store Image Processing Application-specific procedure
    procedure_content = """
    Image Processing Application - Connectivity Troubleshooting Procedure:
    
    Issue: Reporting Server cannot connect to Database
    Standard Resolution Steps:
    1. Check Transit Gateway route tables for cross-VPC connectivity
    2. Verify security group rules allow traffic from Reporting VPC to App VPC
    3. Test DNS resolution: nslookup db.examplecorp.internal from reporting server
    4. Check NACL rules on both VPCs
    5. Verify RDS security group allows port 3306 from Reporting VPC
    
    Common Fix: Add Reporting VPC CIDR to RDS security group inbound rules
    Historical Context: Last time this occurred, CPU utilization was at 78% on the database
    Escalation: If issue persists after security group fix, escalate to Network Team
    """
    
    procedure_metadata = {
        "procedure_type": "connectivity_troubleshooting",
        "platform": "image_processing_application",
        "issue_category": "database_connectivity",
        "historical_cpu_utilization": "78%",
        "last_incident_date": "2024-09-15",
        "last_updated": datetime.now().isoformat()
    }
    
    print(f"📝 STORING PROCEDURE: {procedure_content.strip()}")
    print(f"🏷️  METADATA: {procedure_metadata}")
    print(f"🎯 STRATEGY: custom (Image Processing Application procedures)")
    print(f"🏢 PLATFORM: Image Processing Application")
    print(f"📊 HISTORICAL DATA: Last incident CPU was at 78%")
    
    # Store EXAMPLECORP procedure
    store_result = await memory_hook.store_memory(
        strategy="custom",
        content=procedure_content,
        metadata=procedure_metadata
    )
    
    print(f"✅ STORAGE RESULT: {store_result}")
    
    # Retrieve EXAMPLECORP procedure
    query = "EXAMPLECORP connectivity troubleshooting database reporting server procedure"
    print(f"🔍 SEARCHING FOR: {query}")
    
    retrieve_result = await memory_hook.retrieve_memory(
        strategy="custom",
        query=query,
        max_results=3
    )
    
    print(f"📊 RETRIEVAL RESULT: {retrieve_result}")
    print(f"📈 FOUND {len(retrieve_result) if retrieve_result else 0} procedures")
    
    if retrieve_result:
        for i, result in enumerate(retrieve_result):
            content = result.get('content', '')
            print(f"📄 Procedure {i+1}: {content[:100]}...")
            
            # Check for procedure elements
            procedure_elements = []
            if 'resolution steps' in content.lower():
                procedure_elements.append("Step-by-step guide")
            if 'security group' in content.lower():
                procedure_elements.append("Security group fix")
            if 'escalation' in content.lower():
                procedure_elements.append("Escalation path")
            if 'transit gateway' in content.lower():
                procedure_elements.append("Network troubleshooting")
            if '10.1.0.0/16' in content:
                procedure_elements.append("VPC-specific details")
                
            if procedure_elements:
                print(f"   🔧 Procedure elements: {', '.join(procedure_elements)} ✅")
    
    success = (
        store_result and store_result.get('status') == 'stored' and
        retrieve_result and len(retrieve_result) > 0
    )
    
    if success:
        print("🎉 SUCCESS: Image Processing Application procedure stored and retrieved!")
        print("💡 Agent now has access to proven troubleshooting workflows")
        print("🚀 BUSINESS IMPACT: Standardized resolution approach across team")
        print("📋 CONSISTENCY: Same proven steps used every time")
        print("📊 HISTORICAL CONTEXT: Includes CPU utilization data from previous incidents")
        print("🎯 PLATFORM-SPECIFIC: Tailored to exact platform architecture")
    else:
        print("❌ FAILED: Could not store/retrieve EXAMPLECORP procedure")
    
    print("=" * 80)
    
    assert success, f"EXAMPLECORP procedure storage failed. Store: {store_result}, Retrieve: {retrieve_result}"


if __name__ == "__main__":
    import asyncio
    
    async def run_test():
        memory_hook = MemoryHookProvider()
        await test_examplecorp_platform_procedures(memory_hook)
    
    asyncio.run(run_test())
