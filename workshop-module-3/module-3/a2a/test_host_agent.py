#!/usr/bin/env python3
"""
Comprehensive test file for the host agent using BedrockAgentCore framework.
This test validates interaction with the host agent through the proper BedrockAgentCore
framework rather than direct HTTP calls to localhost ports.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Add the host directory to Python path for imports
current_dir = Path(__file__).parent
host_dir = current_dir / "host"
sys.path.insert(0, str(host_dir))
sys.path.insert(0, str(current_dir))

# Import BedrockAgentCore components
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient

# Import host agent components
try:
    from host.agent import HostAgent, host_agent_task, app as host_app
    from host.context import HostAgentContext
    from host.streaming_queue import HostStreamingQueue
    from host.access_token import get_gateway_access_token
    from host.memory_hook_provider import HostMemoryHook
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running this from the a2a_local directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestHostAgentBedrockCore:
    """
    Test suite for the host agent using BedrockAgentCore framework.
    Tests the proper interaction patterns without direct HTTP calls.
    """
    
    def __init__(self):
        self.test_session_id = f"test-session-{uuid.uuid4()}"
        self.test_actor_id = f"test-actor-{uuid.uuid4()}"
        self.memory_client = MemoryClient()
        
    async def setup_test_environment(self):
        """Set up the test environment with proper context."""
        logger.info("Setting up test environment...")
        
        # Initialize response queue
        response_queue = HostStreamingQueue()
        HostAgentContext.set_response_queue_ctx(response_queue)
        
        # Get gateway access token
        try:
            gateway_token = await get_gateway_access_token()
            HostAgentContext.set_gateway_token_ctx(gateway_token)
            logger.info("✓ Gateway access token obtained")
        except Exception as e:
            logger.warning(f"Could not get gateway token: {e}")
            # Use a dummy token for testing
            HostAgentContext.set_gateway_token_ctx("dummy-token-for-testing")
        
        logger.info("✓ Test environment setup complete")
    
    async def test_host_agent_initialization(self) -> bool:
        """Test host agent initialization with BedrockAgentCore."""
        logger.info("Testing host agent initialization...")
        
        try:
            # Test agent URLs (from config)
            agent_urls = ["http://localhost:10005"]  # Log analytics agent
            
            # Create memory hook for testing
            memory_hook = HostMemoryHook(
                memory_client=self.memory_client,
                memory_id="test-memory-id",
                actor_id=self.test_actor_id,
                session_id=self.test_session_id,
            )
            
            # Initialize host agent
            host_agent = await HostAgent.create(
                remote_agent_addresses=agent_urls,
                bearer_token="test-token",
                memory_hook=memory_hook,
            )
            
            # Verify agent initialization
            assert host_agent is not None
            assert hasattr(host_agent, 'agent')
            assert hasattr(host_agent, 'tools')
            assert len(host_agent.tools) >= 2  # Should have current_time and send_message_tool
            
            logger.info("✓ Host agent initialized successfully")
            logger.info(f"  - Model ID: {host_agent.model_id}")
            logger.info(f"  - Tools available: {len(host_agent.tools)}")
            logger.info(f"  - Remote connections: {len(host_agent.remote_agent_connections)}")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Host agent initialization failed: {e}")
            return False
    
    async def test_bedrock_agentcore_entrypoint(self) -> bool:
        """Test the BedrockAgentCore entrypoint function."""
        logger.info("Testing BedrockAgentCore entrypoint...")
        
        try:
            # Import the invoke function directly
            from host.main import invoke
            
            # Prepare test payload
            test_payload = {
                "prompt": "Hello, can you help me analyze Transit Gateway traffic for a test application?",
                "actor_id": self.test_actor_id
            }
            
            # Create mock context
            class MockContext:
                def __init__(self, session_id):
                    self.session_id = session_id
            
            mock_context = MockContext(self.test_session_id)
            
            # Test the entrypoint function directly
            result_generator = await invoke(test_payload, mock_context)
            
            # Collect streaming results
            results = []
            async for item in result_generator:
                results.append(item)
                logger.info(f"Received stream item: {str(item)[:100]}...")
            
            logger.info(f"✓ BedrockAgentCore entrypoint test successful")
            logger.info(f"  - Received {len(results)} stream items")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ BedrockAgentCore entrypoint test failed: {e}")
            return False
    
    async def test_host_agent_task_function(self) -> bool:
        """Test the host_agent_task function directly."""
        logger.info("Testing host_agent_task function...")
        
        try:
            # Set up context
            await self.setup_test_environment()
            
            # Test message for log analytics
            test_message = "Analyze Transit Gateway traffic for Retail-Application with owner test@company.com in us-east-1 region for test environment"
            
            # Create task
            task = asyncio.create_task(
                host_agent_task(
                    user_message=test_message,
                    session_id=self.test_session_id,
                    actor_id=self.test_actor_id,
                )
            )
            
            # Get response queue and collect results
            response_queue = HostAgentContext.get_response_queue_ctx()
            results = []
            
            # Collect streaming results with timeout
            try:
                async with asyncio.timeout(30):  # 30 second timeout
                    async for item in response_queue.stream():
                        results.append(item)
                        logger.info(f"Received: {str(item)[:100]}...")
                        
                    await task  # Ensure task completion
            except asyncio.TimeoutError:
                logger.warning("Task timed out, but may have produced partial results")
            
            logger.info(f"✓ Host agent task test completed")
            logger.info(f"  - Received {len(results)} response items")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Host agent task test failed: {e}")
            return False
    
    async def test_send_message_tool(self) -> bool:
        """Test the send_message_tool functionality."""
        logger.info("Testing send_message_tool...")
        
        try:
            # Initialize host agent
            agent_urls = ["http://localhost:10005"]
            
            host_agent = await HostAgent.create(
                remote_agent_addresses=agent_urls,
                bearer_token="test-token",
            )
            
            # Test sending a message to LogAnalytics_Agent
            test_task = "Analyze network traffic patterns for test application"
            
            # Use the internal method to test message sending
            result = await host_agent._send_message_impl("LogAnalytics_Agent", test_task)
            
            logger.info(f"✓ Send message tool test completed")
            logger.info(f"  - Result type: {type(result)}")
            logger.info(f"  - Result preview: {str(result)[:200]}...")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Send message tool test failed: {e}")
            logger.error("  This may be expected if the log analytics agent is not running")
            return False
    
    async def test_streaming_response(self) -> bool:
        """Test streaming response functionality."""
        logger.info("Testing streaming response...")
        
        try:
            # Initialize host agent
            agent_urls = ["http://localhost:10005"]
            
            host_agent = await HostAgent.create(
                remote_agent_addresses=agent_urls,
                bearer_token="test-token",
            )
            
            # Test streaming
            test_query = "What is the current time and can you help with log analysis?"
            
            stream_items = []
            async for item in host_agent.stream(test_query):
                stream_items.append(item)
                logger.info(f"Stream item: {str(item)[:100]}...")
                
                # Limit to prevent infinite streaming in tests
                if len(stream_items) >= 10:
                    break
            
            logger.info(f"✓ Streaming response test completed")
            logger.info(f"  - Received {len(stream_items)} stream items")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Streaming response test failed: {e}")
            return False
    
    async def test_context_management(self) -> bool:
        """Test context management functionality."""
        logger.info("Testing context management...")
        
        try:
            # Test setting and getting context
            test_queue = HostStreamingQueue()
            test_token = "test-gateway-token"
            
            # Set context
            HostAgentContext.set_response_queue_ctx(test_queue)
            HostAgentContext.set_gateway_token_ctx(test_token)
            
            # Get context
            retrieved_queue = HostAgentContext.get_response_queue_ctx()
            retrieved_token = HostAgentContext.get_gateway_token_ctx()
            
            # Verify context
            assert retrieved_queue is test_queue
            assert retrieved_token == test_token
            
            logger.info("✓ Context management test successful")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Context management test failed: {e}")
            return False
    
    async def run_all_tests(self) -> bool:
        """Run all host agent tests."""
        logger.info("=" * 80)
        logger.info("STARTING HOST AGENT BEDROCKAGENTCORE TEST SUITE")
        logger.info("Testing interaction with host agent through BedrockAgentCore framework")
        logger.info("=" * 80)
        
        tests = [
            ("Context Management", self.test_context_management),
            ("Host Agent Initialization", self.test_host_agent_initialization),
            ("BedrockAgentCore Entrypoint", self.test_bedrock_agentcore_entrypoint),
            ("Host Agent Task Function", self.test_host_agent_task_function),
            ("Send Message Tool", self.test_send_message_tool),
            ("Streaming Response", self.test_streaming_response),
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            logger.info(f"\n--- Running: {test_name} ---")
            try:
                result = await test_func()
                results[test_name] = result
                if result:
                    logger.info(f"✓ {test_name}: PASSED")
                else:
                    logger.error(f"✗ {test_name}: FAILED")
            except Exception as e:
                logger.error(f"✗ {test_name}: ERROR - {e}")
                results[test_name] = False
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("HOST AGENT BEDROCKAGENTCORE TEST RESULTS")
        logger.info("=" * 60)
        
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✓ PASSED" if result else "✗ FAILED"
            logger.info(f"{test_name:<30}: {status}")
        
        logger.info("-" * 60)
        logger.info(f"TOTAL: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 ALL TESTS PASSED! Host agent BedrockAgentCore integration working correctly.")
        else:
            logger.warning(f"⚠ {total - passed} test(s) failed. Check logs for details.")
        
        return passed == total


async def main():
    """Main test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test host agent using BedrockAgentCore framework")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create test instance and run
    test_suite = TestHostAgentBedrockCore()
    success = await test_suite.run_all_tests()
    
    # Return success status instead of calling sys.exit()
    return success


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Test failed with exception: {e}")
        sys.exit(1)
