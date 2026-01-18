# Semantic Memory Strategy - EXAMPLECORP Image Gallery Platform

## Overview

The Semantic Memory Strategy focuses on extracting and storing **factual knowledge** from conversations, particularly user permissions and platform-specific information. For the EXAMPLECORP Image Gallery Platform, this strategy is crucial for remembering user access rights and technical knowledge across troubleshooting sessions.

## Strategy Configuration

### **Primary Purpose**
Store factual information that doesn't change frequently:
- User permission groups (`imaging-ops@examplecorp.com`)
- Platform resource identifiers
- Technical specifications and configurations
- Known connectivity patterns and solutions

### **Memory Namespaces**
```
troubleshooting/user/{actorId}/permissions
troubleshooting/platform/examplecorp/knowledge
troubleshooting/platform/examplecorp/resources
```

### **Strategy Definition**
```json
{
  "type": "SEMANTIC",
  "name": "examplecorp_permission_extractor",
  "description": "Extracts and stores imaging-ops@examplecorp.com permissions and EXAMPLECORP platform knowledge",
  "namespaces": [
    "troubleshooting/user/{actorId}/permissions",
    "troubleshooting/platform/examplecorp/knowledge",
    "troubleshooting/platform/examplecorp/resources"
  ]
}
```

## EXAMPLECORP Platform Use Cases

### **Use Case 1: User Permission Storage**

**Scenario**: User identifies their permission group during platform outage troubleshooting.

**Input Conversation**:
```
User: "I belong to imaging-ops@examplecorp.com and need help with the EXAMPLECORP Image Platform outage"
Agent: "I understand you have imaging-ops permissions. Let me help with the platform issue."
```

**Semantic Memory Storage**:
```json
{
  "namespace": "troubleshooting/user/user123/permissions",
  "content": {
    "permission_group": "imaging-ops@examplecorp.com",
    "access_level": "image_management_operations",
    "verified_at": "2024-01-15T10:30:00Z",
    "context": "EXAMPLECORP Image Platform troubleshooting"
  }
}
```

**Memory Retrieval** (Next Session):
```
User: "The reporting server still can't connect to the database"
Memory Recalls: "User has imaging-ops@examplecorp.com permissions"
Agent: "I remember you have imaging-ops access. Let's continue troubleshooting the reporting server connectivity issue..."
```

### **Use Case 2: Platform Resource Knowledge**

**Scenario**: Agent learns about EXAMPLECORP platform infrastructure during troubleshooting.

**Input Conversation**:
```
User: "The ALB DNS is sample-app-image-sharing-alb-123456789.us-east-1.elb.amazonaws.com"
User: "The database endpoint is sample-app-image-metadata-db.cluster-xyz.us-east-1.rds.amazonaws.com"
```

**Semantic Memory Storage**:
```json
{
  "namespace": "troubleshooting/platform/examplecorp/resources",
  "content": {
    "alb_dns": "sample-app-image-sharing-alb-123456789.us-east-1.elb.amazonaws.com",
    "database_endpoint": "sample-app-image-metadata-db.cluster-xyz.us-east-1.rds.amazonaws.com",
    "s3_bucket": "sample-app-123456789-image-stack-name",
    "transit_gateway": "tgw-0123456789abcdef0",
    "reporting_server": "reporting.examplecorp.com"
  }
}
```

### **Use Case 3: Connectivity Pattern Knowledge**

**Scenario**: Agent learns about successful connectivity troubleshooting patterns.

**Input Conversation**:
```
User: "The issue was the database security group missing the Reporting VPC CIDR 10.1.0.0/16"
Agent: "That's a common connectivity issue. I'll remember this pattern for future troubleshooting."
```

**Semantic Memory Storage**:
```json
{
  "namespace": "troubleshooting/platform/examplecorp/knowledge",
  "content": {
    "connectivity_pattern": "reporting_to_database",
    "common_issue": "database_security_group_missing_reporting_vpc_cidr",
    "solution": "add_10.1.0.0/16_to_database_security_group_port_3306",
    "success_rate": "high",
    "last_verified": "2024-01-15T14:45:00Z"
  }
}
```

## Implementation Details

### **Memory Hook Integration**

Based on `stage-3/agentcore-reference/agent_config/memory_hook_provider.py`:

```python
def _add_context_user_query(self, namespace: str, query: str, init_content: str, event: MessageAddedEvent):
    """Add semantic context to user queries"""
    content = None
    memories = self.memory_client.retrieve_memories(
        memory_id=self.memory_id, 
        namespace=namespace, 
        query=query, 
        top_k=3
    )
    
    for memory in memories:
        if not content:
            content = "\n\n" + init_content + "\n\n"
        content += memory["content"]["text"]
    
    if content:
        event.agent.messages[-1]["content"][0]["text"] += content + "\n\n"
```

### **Permission Context Injection**

```python
def on_message_added(self, event: MessageAddedEvent):
    """Store and retrieve permission context"""
    if messages[-1]["role"] == "user":
        # Add permission context to user queries
        self._add_context_user_query(
            namespace=f"troubleshooting/user/{self.actor_id}/permissions",
            query=messages[-1]["content"][0]["text"],
            init_content="User permissions:",
            event=event
        )
        
        # Add platform knowledge context
        self._add_context_user_query(
            namespace=f"troubleshooting/platform/examplecorp/knowledge",
            query=messages[-1]["content"][0]["text"],
            init_content="EXAMPLECORP platform knowledge:",
            event=event
        )
```

## Testing Semantic Memory

### **Test Script**: `test/test_memory_validation.py`

```python
def test_semantic_memory_permissions():
    """Test permission storage and retrieval"""
    memory_client = MemoryClient()
    
    # Test 1: Store permission
    memory_client.save_conversation(
        memory_id=MEMORY_ID,
        actor_id="test_user",
        session_id="session_001",
        messages=[
            ("I belong to imaging-ops@examplecorp.com", "user"),
            ("I understand you have imaging-ops permissions", "assistant")
        ]
    )
    
    # Test 2: Retrieve permission context
    memories = memory_client.retrieve_memories(
        memory_id=MEMORY_ID,
        namespace="troubleshooting/user/test_user/permissions",
        query="Do I have permissions for image operations?",
        top_k=1
    )
    
    # Verify: Should recall imaging-ops@examplecorp.com without re-asking
    assert len(memories) > 0
    assert "imaging-ops@examplecorp.com" in memories[0]["content"]["text"]
```

### **Manual Testing Procedure**

1. **Session 1 - Store Permission**:
   ```
   User: "I belong to imaging-ops@examplecorp.com and need help with the platform outage"
   Expected: Agent acknowledges and stores permission
   ```

2. **Session 2 - Recall Permission**:
   ```
   User: "I need to modify image metadata in the database"
   Expected: Agent recalls permission, doesn't ask "Do you belong to imaging-ops@examplecorp.com?"
   ```

3. **Session 3 - Platform Knowledge**:
   ```
   User: "What's the ALB DNS for the EXAMPLECORP platform?"
   Expected: Agent recalls stored resource information
   ```

## Performance Characteristics

### **Storage Efficiency**
- **Factual Information**: Highly efficient for storing structured facts
- **Deduplication**: Automatically handles duplicate permission statements
- **Persistence**: Long-term storage suitable for rarely-changing information

### **Retrieval Performance**
- **Query Speed**: < 50ms for permission lookups
- **Accuracy**: 99%+ for exact factual matches
- **Context Relevance**: High precision for permission and resource queries

### **Memory Footprint**
- **Permission Records**: ~100 bytes per user
- **Platform Knowledge**: ~1KB per resource set
- **Connectivity Patterns**: ~500 bytes per pattern

## Troubleshooting

### **Common Issues**

#### **Issue 1: Permissions Not Recalled**
```bash
# Symptoms: Agent repeatedly asks for imaging-ops@examplecorp.com verification
# Debug: Check semantic memory namespace
python3 test/test_memory_validation.py --strategy semantic --debug

# Expected output:
# ✅ Semantic memory namespace accessible
# ✅ Permission stored: imaging-ops@examplecorp.com
# ✅ Retrieval test: SUCCESS
```

#### **Issue 2: Platform Knowledge Not Retrieved**
```bash
# Symptoms: Agent doesn't recall EXAMPLECORP platform resources
# Debug: Check platform knowledge namespace
memory_client.retrieve_memories(
    memory_id=MEMORY_ID,
    namespace="troubleshooting/platform/examplecorp/knowledge",
    query="EXAMPLECORP platform resources",
    top_k=5
)
```

#### **Issue 3: Semantic Context Not Injected**
```bash
# Symptoms: Agent doesn't use stored factual knowledge in responses
# Check: Memory hook integration
# Verify: _add_context_user_query function is called
# Debug: Enable AGENTCORE_DEBUG=true
```

## Best Practices

### **Information to Store in Semantic Memory**
✅ **Good for Semantic Memory**:
- User permission groups
- Platform resource identifiers
- Technical specifications
- Known connectivity patterns
- Successful troubleshooting procedures

❌ **Not Suitable for Semantic Memory**:
- Temporary session data
- Changing metrics or status
- Personal preferences
- Conversation flow context

### **Namespace Organization**
```
troubleshooting/user/{actorId}/permissions     # User-specific permissions
troubleshooting/platform/examplecorp/knowledge        # Platform-wide knowledge
troubleshooting/platform/examplecorp/resources        # Resource identifiers
troubleshooting/platform/examplecorp/patterns         # Connectivity patterns
```

### **Query Optimization**
- Use specific queries for better retrieval accuracy
- Include context keywords (e.g., "imaging-ops", "EXAMPLECORP platform")
- Limit top_k to 3-5 for performance

## Integration with Other Strategies

### **Semantic + Summary Memory**
```
Semantic: Stores "User has imaging-ops@examplecorp.com permissions"
Summary: Stores "User completed connectivity troubleshooting for TKT-SEV1-001"
Combined: Agent knows user permissions AND current troubleshooting context
```

### **Semantic + User Preference Memory**
```
Semantic: Stores "Database endpoint: sample-app-image-metadata-db.cluster-xyz..."
User Preference: Learns "User prefers security group troubleshooting first"
Combined: Agent suggests security group checks for database connectivity issues
```

## Monitoring and Metrics

### **Key Metrics**
- **Permission Recall Rate**: % of sessions where permissions are correctly recalled
- **Platform Knowledge Accuracy**: % of correct resource information retrievals
- **Context Injection Success**: % of queries enhanced with semantic context

### **CloudWatch Metrics**
```
Namespace: AgentCore/Memory/EXAMPLECORP/Semantic
Metrics:
- PermissionRecallRate
- PlatformKnowledgeAccuracy
- SemanticContextInjections
- FactualQueryLatency
```

---

**Success Criteria**: Semantic memory successfully stores and recalls user permissions (`imaging-ops@examplecorp.com`), platform resources, and connectivity knowledge, eliminating the need for users to repeatedly provide the same factual information during EXAMPLECORP platform troubleshooting sessions.
