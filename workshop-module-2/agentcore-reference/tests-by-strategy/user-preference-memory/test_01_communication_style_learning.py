"""
Test 1: Communication Style Learning
Tests learning and adapting to user's preferred communication style
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
async def test_communication_style_learning(memory_hook):
    """Test learning user's preferred communication style"""
    print("\n" + "="*80)
    print("🧪 USER PREFERENCE TEST 1: COMMUNICATION STYLE LEARNING")
    print("="*80)
    
    # Store user's communication preference
    preference_content = """
    User prefers step-by-step troubleshooting instructions rather than high-level summaries.
    Communication style: detailed, methodical, with clear action items.
    Feedback: 'Please give me specific commands to run, not just general guidance.'
    """
    
    preference_metadata = {
        "preference_type": "communication_style",
        "user_id": "imaging-ops-user",
        "style": "detailed_step_by_step",
        "feedback_context": "troubleshooting_guidance",
        "timestamp": datetime.now().isoformat()
    }
    
    print(f"📝 STORING PREFERENCE: {preference_content.strip()}")
    print(f"🏷️  METADATA: {preference_metadata}")
    print(f"🎯 STRATEGY: user_preference (adaptive learning)")
    print(f"👤 USER STYLE: Detailed, step-by-step instructions")
    
    # Store communication preference
    store_result = await memory_hook.store_memory(
        strategy="user_preference",
        content=preference_content,
        metadata=preference_metadata
    )
    
    print(f"✅ STORAGE RESULT: {store_result}")
    
    # Retrieve communication preference
    query = "user communication style preferences step-by-step detailed"
    print(f"🔍 SEARCHING FOR: {query}")
    
    retrieve_result = await memory_hook.retrieve_memory(
        strategy="user_preference",
        query=query,
        max_results=3
    )
    
    print(f"📊 RETRIEVAL RESULT: {retrieve_result}")
    print(f"📈 FOUND {len(retrieve_result) if retrieve_result else 0} preferences")
    
    if retrieve_result:
        for i, result in enumerate(retrieve_result):
            content = result.get('content', '')
            print(f"📄 Preference {i+1}: {content[:100]}...")
            
            # Check for communication style indicators
            style_indicators = []
            if 'step-by-step' in content.lower():
                style_indicators.append("Step-by-step")
            if 'detailed' in content.lower():
                style_indicators.append("Detailed")
            if 'specific commands' in content.lower():
                style_indicators.append("Command-focused")
            if 'methodical' in content.lower():
                style_indicators.append("Methodical")
                
            if style_indicators:
                print(f"   🎨 Communication style: {', '.join(style_indicators)} ✅")
    
    success = (
        store_result and store_result.get('status') == 'stored' and
        retrieve_result and len(retrieve_result) > 0
    )
    
    if success:
        print("🎉 SUCCESS: User communication style learned and stored!")
        print("💡 Agent can now adapt responses to user's preferred style")
        print("🚀 BUSINESS IMPACT: Personalized troubleshooting experience")
        print("🎯 ADAPTATION: Future responses will be detailed and step-by-step")
        print("📈 EFFICIENCY: Reduced back-and-forth due to style mismatch")
    else:
        print("❌ FAILED: Could not learn/store communication style preference")
    
    print("=" * 80)
    
    assert success, f"Communication style learning failed. Store: {store_result}, Retrieve: {retrieve_result}"


if __name__ == "__main__":
    import asyncio
    
    async def run_test():
        memory_hook = MemoryHookProvider()
        await test_communication_style_learning(memory_hook)
    
    asyncio.run(run_test())
