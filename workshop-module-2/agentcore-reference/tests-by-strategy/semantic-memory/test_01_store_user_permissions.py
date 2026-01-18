"""
Test 1: Store User Permissions in Semantic Memory
Tests storing imaging-ops@examplecorp.com permissions for long-term retention
"""
import pytest
import pytest_asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_config.memory_hook_provider import MemoryHookProvider


@pytest.mark.asyncio
async def test_store_imaging_ops_permission(memory_hook):
    """Test storing imaging-ops@examplecorp.com permission in semantic memory (LONG-TERM)"""
    print("\n" + "="*80)
    print("🧪 TEST 1: STORING USER PERMISSIONS IN SEMANTIC MEMORY")
    print("="*80)
    
    # Simulate user stating their permission group for Image Processing Application
    permission_content = "I belong to imaging-ops@examplecorp.com and have access to the Image Processing Application platform with ALB, Lambda functions, S3 bucket, and RDS database for image metadata"
    permission_metadata = {
        "user_permission": "imaging-ops@examplecorp.com",
        "platform": "image_processing_application",
        "access_level": "platform_operations",
        "context": "connectivity_troubleshooting",
        "timestamp": datetime.now().isoformat()
    }
    
    print(f"📝 STORING CONTENT: {permission_content}")
    print(f"🏷️  METADATA: {permission_metadata}")
    print(f"🎯 STRATEGY: semantic (long-term memory)")
    print(f"🔗 MEMORY ID: {memory_hook.memory_id}")
    
    # Store permission in semantic memory (LONG-TERM)
    store_result = await memory_hook.store_memory(
        strategy="semantic",
        content=permission_content,
        metadata=permission_metadata
    )
    
    print(f"✅ STORAGE RESULT: {store_result}")
    print(f"📊 STATUS: {store_result.get('status', 'unknown')}")
    
    if store_result.get('status') == 'stored':
        print("🎉 SUCCESS: Permission data stored in semantic memory!")
        print("💡 This means the agent will remember user permissions across sessions")
        print("🚀 BUSINESS IMPACT: Eliminates need to re-verify permissions every interaction")
    else:
        print(f"❌ FAILED: {store_result.get('error', 'Unknown error')}")
    
    print("=" * 80)
    
    assert store_result and store_result.get('status') == 'stored'


if __name__ == "__main__":
    import asyncio
    
    async def run_test():
        memory_hook = MemoryHookProvider()
        await test_store_imaging_ops_permission(memory_hook)
    
    asyncio.run(run_test())
