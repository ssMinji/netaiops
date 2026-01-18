#!/usr/bin/env python3
"""
Test script to demonstrate the beautiful AgentCore runtime logging

This script shows how the enhanced logging will appear when users run evaluations.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add current directory to Python path
sys.path.append(str(Path(__file__).parent))

# Import our enhanced client
from src.evaluation.agentcore_client import AgentRuntimeLogger, AgentCoreClient


async def demo_beautiful_logging():
    """Demonstrate the beautiful logging output"""
    
    print("🎯 AgentCore Beautiful Logging Demo")
    print("=" * 50)
    print()
    
    # Sample runtime ARN and test data
    sample_runtime_arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/a2a_troubleshooting_agent_runtime-ABC123"
    sample_message = "Help me troubleshoot connectivity issues with my EC2 instance i-1234567890abcdef0"
    sample_session_id = "12345678-1234-1234-1234-123456789012"
    
    # Demo 1: Show logging for a fast response
    print("📍 Demo 1: Fast Response (< 5 seconds)")
    AgentRuntimeLogger.log_runtime_call_start(sample_runtime_arn, sample_message, sample_session_id)
    AgentRuntimeLogger.log_auth_progress("Getting access token...")
    await asyncio.sleep(0.5)
    AgentRuntimeLogger.log_auth_progress("Access token obtained successfully")
    AgentRuntimeLogger.log_runtime_call_progress(1.2, "Request prepared, sending to AgentCore...")
    await asyncio.sleep(0.3)
    AgentRuntimeLogger.log_runtime_call_progress(1.8, "Connected! Processing streaming response...")
    await asyncio.sleep(0.7)
    AgentRuntimeLogger.log_runtime_call_success(
        3.2, 
        445, 
        "I'll help you troubleshoot the connectivity issues with your EC2 instance. Let me start by checking the basic network configuration and security groups..."
    )
    
    print("\n" + "=" * 50 + "\n")
    
    # Demo 2: Show logging for a medium response  
    print("📍 Demo 2: Medium Response (5-15 seconds)")
    sample_message_2 = "Analyze network performance and identify TCP retransmission patterns in my VPC"
    sample_session_id_2 = "87654321-4321-4321-4321-210987654321"
    
    AgentRuntimeLogger.log_runtime_call_start(sample_runtime_arn, sample_message_2, sample_session_id_2)
    AgentRuntimeLogger.log_auth_progress("Getting access token...")
    await asyncio.sleep(0.2)
    AgentRuntimeLogger.log_auth_progress("Access token obtained successfully")
    AgentRuntimeLogger.log_runtime_call_progress(0.8, "Request prepared, sending to AgentCore...")
    await asyncio.sleep(0.4)
    AgentRuntimeLogger.log_runtime_call_progress(1.3, "Connected! Processing streaming response...")
    await asyncio.sleep(1.0)
    AgentRuntimeLogger.log_runtime_call_progress(6.1, "Streaming response... (1247 chars received)")
    await asyncio.sleep(0.8)
    AgentRuntimeLogger.log_runtime_call_success(
        8.7, 
        1847, 
        "I've analyzed your VPC network performance and found several TCP retransmission patterns. Let me break down the findings: 1) High retransmission rates on subnet-abc123..."
    )
    
    print("\n" + "=" * 50 + "\n")
    
    # Demo 3: Show logging for a slow response
    print("📍 Demo 3: Slow Response (> 15 seconds)")
    sample_message_3 = "Perform comprehensive network analysis across multiple availability zones with detailed flow monitoring"
    sample_session_id_3 = "11111111-2222-3333-4444-555555555555"
    
    AgentRuntimeLogger.log_runtime_call_start(sample_runtime_arn, sample_message_3, sample_session_id_3)
    AgentRuntimeLogger.log_auth_progress("Getting access token...")
    await asyncio.sleep(0.3)
    AgentRuntimeLogger.log_auth_progress("Access token obtained successfully")
    AgentRuntimeLogger.log_runtime_call_progress(1.1, "Request prepared, sending to AgentCore...")
    await asyncio.sleep(0.5)
    AgentRuntimeLogger.log_runtime_call_progress(1.7, "Connected! Processing streaming response...")
    await asyncio.sleep(1.2)
    AgentRuntimeLogger.log_runtime_call_progress(8.3, "Streaming response... (2451 chars received)")
    await asyncio.sleep(1.1)
    AgentRuntimeLogger.log_runtime_call_progress(13.8, "Streaming response... (4203 chars received)")
    await asyncio.sleep(0.9)
    AgentRuntimeLogger.log_runtime_call_success(
        18.4, 
        5672, 
        "I've completed a comprehensive network analysis across your multiple availability zones. Here's the detailed flow monitoring report: The analysis covers 3 AZs with flow data from the past 24 hours..."
    )
    
    print("\n" + "=" * 50 + "\n")
    
    # Demo 4: Show logging for an error
    print("📍 Demo 4: Error Response")
    sample_message_4 = "Invalid request that will cause an error"
    sample_session_id_4 = "99999999-8888-7777-6666-555555555555"
    
    AgentRuntimeLogger.log_runtime_call_start(sample_runtime_arn, sample_message_4, sample_session_id_4)
    AgentRuntimeLogger.log_auth_progress("Getting access token...")
    await asyncio.sleep(0.2)
    AgentRuntimeLogger.log_auth_progress("Access token obtained successfully")
    AgentRuntimeLogger.log_runtime_call_progress(0.9, "Request prepared, sending to AgentCore...")
    await asyncio.sleep(0.3)
    AgentRuntimeLogger.log_runtime_call_error("HTTP 403: Forbidden - Invalid session or expired token", 2.1)
    
    print("\n" + "=" * 60)
    print("🎉 Beautiful Logging Demo Complete!")
    print("=" * 60)
    print()
    print("Key Features:")
    print("✅ Real-time progress indicators with timestamps")
    print("✅ Color-coded response times (🟢 < 5s, 🟡 5-15s, 🟠 > 15s)")
    print("✅ Authentication progress tracking")
    print("✅ Streaming response progress updates")
    print("✅ Clear error reporting with timing")
    print("✅ Response size and preview information")
    print("✅ Beautiful visual separators")
    print()


async def demo_actual_client():
    """Demo what would happen with a real client (without making actual calls)"""
    
    print("🔧 AgentCore Client Integration Demo")
    print("=" * 50)
    print()
    
    # Sample configuration
    sample_config = {
        'machine_client_id': 'sample-client-id-12345',
        'cognito_auth_scope': 'agentcore/invoke'
    }
    
    print("This shows how the beautiful logging integrates with the actual AgentCoreClient:")
    print()
    print("🔹 When you run: python scripts/run_evaluation.py --agent TroubleshootingAgent")
    print("🔹 You'll see the beautiful progress logs for each AgentCore runtime call")
    print("🔹 Response times are tracked and color-coded automatically")
    print("🔹 Authentication steps are shown with clear progress")
    print("🔹 Streaming responses show real-time progress updates")
    print()
    
    # Show a simulated client initialization
    print("💡 Example client usage:")
    print("   client = AgentCoreClient(cognito_config)")
    print("   response = await client.invoke_agent(runtime_arn, message, session_id)")
    print("   # Beautiful logging happens automatically! ✨")
    print()


if __name__ == "__main__":
    print("🚀 Starting AgentCore Beautiful Logging Test")
    print("=" * 60)
    print()
    
    # Run the demos
    asyncio.run(demo_beautiful_logging())
    print()
    asyncio.run(demo_actual_client())
