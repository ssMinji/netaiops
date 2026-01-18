"""
Shared test configuration for semantic memory tests
Ensures all tests use the same memory hook provider instance
"""
import pytest
import pytest_asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_config.memory_hook_provider import MemoryHookProvider


@pytest_asyncio.fixture(scope="module")
async def memory_hook():
    """Shared memory hook provider for all semantic memory tests"""
    print("\n🔧 INITIALIZING SHARED MEMORY HOOK FOR ALL SEMANTIC MEMORY TESTS")
    hook = MemoryHookProvider()
    print(f"🔗 Shared Memory ID: {hook.memory_id}")
    print(f"🔗 Shared Session ID: {hook.memory_session_id}")
    return hook
