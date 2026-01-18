"""
Test 2: Recall User Permissions Without Asking
Tests retrieving imaging-ops@examplecorp.com permissions from semantic memory
"""
import pytest
import pytest_asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_config.memory_hook_provider import MemoryHookProvider


@pytest.mark.asyncio
async def test_recall_permission_without_asking(memory_hook):
    """Test that agent can recall permission without asking user again (LONG-TERM PERSISTENCE)"""
    print("\n" + "="*80)
    print("🧪 TEST 2: RECALLING USER PERMISSIONS WITHOUT ASKING")
    print("="*80)
    
    query = "imaging-ops@examplecorp.com permission access EXAMPLECORP platform"
    print(f"🔍 SEARCHING FOR: {query}")
    print(f"🎯 STRATEGY: semantic (long-term memory)")
    print(f"🔗 MEMORY ID: {memory_hook.memory_id}")
    
    # Query for permission information
    retrieve_result = await memory_hook.retrieve_memory(
        strategy="semantic",
        query=query,
        max_results=5
    )
    
    print(f"📊 RETRIEVAL RESULT: {retrieve_result}")
    print(f"📈 FOUND {len(retrieve_result) if retrieve_result else 0} memories")
    
    if retrieve_result:
        for i, result in enumerate(retrieve_result):
            print(f"📄 Memory {i+1}: {result.get('content', '')[:100]}...")
            print(f"   🏷️  Metadata: {result.get('metadata', {})}")
            print(f"   📅 Timestamp: {result.get('timestamp', 'unknown')}")
    
    # Validate that permission was recalled
    success = (
        retrieve_result and 
        len(retrieve_result) > 0 and
        any("imaging-ops@examplecorp.com" in str(result).lower() for result in retrieve_result)
    )
    
    if success:
        print("🎉 SUCCESS: Agent can recall user permissions without asking!")
        print("💡 This eliminates the need to re-verify permissions in each session")
        print("🚀 BUSINESS IMPACT: Eliminates need to re-verify permissions every interaction")
    else:
        print("❌ FAILED: Could not recall previously stored permissions")
        print("🔍 DEBUG: Check if test_01_store_user_permissions.py was run first")
    
    print("=" * 80)
    
    assert success, f"Failed to recall permissions. Retrieved: {retrieve_result}"


if __name__ == "__main__":
    import asyncio
    
    async def run_test():
        memory_hook = MemoryHookProvider()
        await test_recall_permission_without_asking(memory_hook)
    
    asyncio.run(run_test())
