#!/usr/bin/python
"""
Simple setup script for ExampleCorp Image Gallery Platform AgentCore Memory integration
Creates short-term and long-term memory with required strategies
"""
import boto3
import sys
import os
import json
import time
from botocore.exceptions import ClientError
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType

# Force us-east-1 region for all operations
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
REGION = "us-east-1"
ssm = boto3.client("ssm", region_name=REGION)
memory_client = MemoryClient()


def setup_examplecorp_memory():
    """Setup ExampleCorp Image Gallery Platform Memory - Simple approach"""
    print("🧠 Setting up ExampleCorp Image Gallery Platform Memory...")
    print("📋 Creating short-term and long-term memory with required strategies")
    
    name = "ExampleCorpImageGalleryMemory"
    ssm_param = "/examplecorp/agentcore/memory_id"
    event_expiry_days = 365
    
    # Define memory strategies - matching AWS documentation format exactly
    strategies = [
        {
            "semanticMemoryStrategy": {
                "name": "examplecorp_knowledge_extractor",
                "namespaces": ["examplecorp/user/{actorId}/facts"],
            }
        },
        {
            "summaryMemoryStrategy": {
                "name": "incident_session_summary", 
                "namespaces": ["examplecorp/user/{actorId}/{sessionId}"],
            }
        },
        {
            "userPreferenceMemoryStrategy": {
                "name": "user_troubleshooting_preferences",
                "namespaces": ["examplecorp/user/{actorId}/preferences"],
            }
        },
    ]

    try:
        print("🔄 Creating ExampleCorp memory resource...")
        
        # Create memory without execution role (no custom strategies needed)
        memory = memory_client.create_memory_and_wait(
            name=name,
            strategies=strategies,
            description="ExampleCorp Image Gallery Platform Memory - Short-term incident tracking and long-term knowledge storage",
            event_expiry_days=event_expiry_days,
        )
        memory_id = memory["id"]
        print(f"✅ Memory created successfully: {memory_id}")
        
        # Verify the memory exists and get the correct ID
        memories = memory_client.list_memories()
        actual_memory = None
        for mem in memories:
            if mem.get("name") == name or memory_id in mem.get("id", ""):
                actual_memory = mem
                memory_id = mem["id"]  # Use the actual ID from list_memories
                break
        
        if actual_memory:
            print(f"✅ Verified memory ID: {memory_id}")
        else:
            print(f"⚠️  Could not verify memory in list, using returned ID: {memory_id}")
        
        # Store memory ID in SSM
        ssm.put_parameter(Name=ssm_param, Value=memory_id, Type="String", Overwrite=True)
        print(f"🔐 Stored memory_id in SSM: {ssm_param}")
        
        print("🎉 ExampleCorp Memory Setup complete!")
        print(f"   Memory ID: {memory_id}")
        print(f"   SSM Parameter: {ssm_param}")
        print("\n📋 Memory Strategies Configured:")
        print("   📚 Semantic (Long-term): Platform knowledge, procedures, technical facts")
        print("   📝 Summary (Short-term): Incident sessions, workshop progress")
        print("   👤 User Preference: Communication style, troubleshooting patterns")
        print("\n🧪 Ready for test cases to demonstrate all 3 memory strategies!")
        
        return memory_id
        
    except Exception as e:
        if "already exists" in str(e):
            print("📋 Memory already exists, finding existing resource...")
            memories = memory_client.list_memories()
            
            # Look for memory by name pattern (more flexible matching)
            memory_id = None
            for memory in memories:
                memory_name_check = memory.get("name", "")
                if name in memory_name_check or "ExampleCorpImageGalleryMemory" in memory_name_check:
                    memory_id = memory["id"]
                    print(f"   📋 Found matching memory: {memory_name_check} -> {memory_id}")
                    break
            
            if memory_id:
                # Store memory ID in SSM
                ssm.put_parameter(Name=ssm_param, Value=memory_id, Type="String", Overwrite=True)
                print(f"🔐 Stored memory_id in SSM: {ssm_param}")
                print("✅ Using existing memory")
                print(f"   Memory ID: {memory_id}")
                print("🧪 Ready for test cases to demonstrate 3 memory strategies!")
                return memory_id
            else:
                print(f"❌ Could not find existing memory with name pattern: {name}")
                sys.exit(1)
        
        print(f"❌ Failed to setup memory: {e}")
        sys.exit(1)


if __name__ == "__main__":
    setup_examplecorp_memory()
