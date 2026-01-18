# EXAMPLECORP Memory Tests by Strategy

This directory contains organized memory tests separated by memory strategy type. Each test demonstrates individual memory capabilities and their business impact, using actual AWS resources discovered from your environment.

## Directory Structure

```
tests-by-strategy/
├── semantic-memory/          # Long-term knowledge storage (3 tests)
├── user-preference-memory/   # User behavior learning (1 test)
├── summary-memory/           # Session context tracking (1 test)
├── custom-memory/           # EXAMPLECORP-specific procedures (1 test)
└── integration/             # Module-1 runtime enhancement (1 test)
```

## Memory Strategy Overview

### 🧠 Semantic Memory (Long-term)
**Purpose**: Stores facts, permissions, and platform knowledge that persist across sessions
**Namespace**: `examplecorp/user/{actorId}/facts`
**Retention**: Long-term (365 days)

### 👤 User Preference Memory
**Purpose**: Learns user communication style and troubleshooting preferences
**Namespace**: `examplecorp/user/{actorId}/preferences`
**Retention**: User-specific

### 📝 Summary Memory (Session-based)
**Purpose**: Tracks current session context and progress
**Namespace**: `examplecorp/user/{actorId}/{sessionId}`
**Retention**: Session-based

### 🔧 Custom Memory (EXAMPLECORP-specific)
**Purpose**: Stores EXAMPLECORP platform procedures and workflows
**Namespace**: `examplecorp/user/{actorId}/facts` (shared with semantic)
**Retention**: Long-term

## Test Output Format

Each test displays clear input/output information:

```
🧪 TEST: [Test Name]
📋 MEMORY STRATEGY: [semantic/user-preference/summary/custom]
📥 INPUT: [What data is being stored/queried]
📤 OUTPUT: [What the agent retrieves/remembers]
🎯 BUSINESS IMPACT: [Qualitative benefit]
✅ RESULT: [Success/Failure with details]
```

## Running Tests

### Prerequisites
- Tests run from EC2 instance with appropriate IAM role
- Module-1 runtime, identity, and gateway already deployed
- Module-2 memory resource created via `setup_examplecorp_memory.py`
- EC2 has permissions for resource discovery and memory operations

### Individual Memory Strategy Tests

#### 1. Semantic Memory Tests (Foundation)
```bash
# Test 1: Store user permissions
python3 -m pytest tests-by-strategy/semantic-memory/test_01_store_user_permissions.py -v -s

# Test 2: Recall permissions without asking
python3 -m pytest tests-by-strategy/semantic-memory/test_02_recall_permissions_without_asking.py -v -s

# Test 3: Store platform architecture knowledge
python3 -m pytest tests-by-strategy/semantic-memory/test_03_platform_knowledge_storage.py -v -s

# All semantic memory tests
python3 -m pytest tests-by-strategy/semantic-memory/ -v -s
```

**What these tests demonstrate:**
- **Test 1**: Basic storage - shows memory can store imaging-ops@examplecorp.com permissions
- **Test 2**: Retrieval - proves agent can recall without asking again
- **Test 3**: Platform knowledge - stores actual AWS resource IDs and architecture details

#### 2. User Preference Tests (Personalization)
```bash
# Test communication style learning
python3 -m pytest tests-by-strategy/user-preference-memory/test_01_communication_style_learning.py -v -s
```

**What this test demonstrates:**
- Learns user prefers "systematic" vs "quick-fix" troubleshooting approach
- Adapts communication style based on user preferences

#### 3. Summary Memory Tests (Session Context)
```bash
# Test session context tracking
python3 -m pytest tests-by-strategy/summary-memory/test_01_session_context_tracking.py -v -s
```

**What this test demonstrates:**
- Tracks current troubleshooting session progress and next steps
- Maintains context across session interruptions

#### 4. Custom Memory Tests (EXAMPLECORP Procedures)
```bash
# Test EXAMPLECORP-specific procedures
python3 -m pytest tests-by-strategy/custom-memory/test_01_examplecorp_platform_procedures.py -v -s
```

**What this test demonstrates:**
- Stores EXAMPLECORP-specific troubleshooting procedures with success rates
- Applies institutional knowledge for consistent problem resolution

#### 5. Integration Test (Module-1 Enhancement)
```bash
# Test complete module-1 workflow enhanced with memory
python3 -m pytest tests-by-strategy/integration/test_01_runtime_connectivity_with_memory.py -v -s
```

**What this test demonstrates:**
- Complete module-1 troubleshooting workflow (same as `test_agent.py`)
- Shows before/after comparison with memory enhancement
- Proves seamless integration - no runtime changes needed

### Run All Tests
```bash
# Run all memory strategy tests
python3 -m pytest tests-by-strategy/ -v -s
```

## Expected Test Output Example

```
🧪 TEST 1: STORING USER PERMISSIONS IN SEMANTIC MEMORY
================================================================================
🔍 DISCOVERED ENVIRONMENT:
   📍 Region: us-east-1
   🖥️  Current Instance: i-0abc123def456789
   🔒 Security Groups: 3 found
   ⚡ Running Instances: 2 found

📝 STORING CONTENT: I belong to imaging-ops@examplecorp.com and have access to...
🏷️  METADATA: {'user_permission': 'imaging-ops@examplecorp.com', 'platform': 'examplecorp_image_gallery'}
🎯 STRATEGY: semantic (long-term memory)
🔗 MEMORY ID: EXAMPLECORPImageGalleryMemory-5XprTc9gO1
✅ STORAGE RESULT: {'memory_id': 'mem_semantic_abc123', 'status': 'stored'}
🎉 SUCCESS: Permission data stored in semantic memory!
💡 This enables the agent to remember user permissions across sessions
🚀 BUSINESS IMPACT: Eliminates need to re-verify permissions every interaction
================================================================================
```

## Dynamic Resource Discovery

All tests automatically discover and use actual AWS resources from your environment:

- **Current EC2 instance ID** (from instance metadata)
- **Security groups** (first 3 found in account)
- **Running instances** (for connectivity troubleshooting scenarios)
- **VPC information** (from discovered resources)
- **Region** (from boto3 session)

This ensures tests are realistic and relevant to your specific AWS setup.

## Business Impact Summary

### Without Memory (Module-1 Only):
- ❌ User must verify permissions every session
- ❌ Agent starts troubleshooting from scratch
- ❌ No retained platform knowledge
- ❌ Generic troubleshooting approach
- ❌ No institutional knowledge retention

### With Memory (Module-1 + Module-2):
- ✅ Agent remembers imaging-ops@examplecorp.com permissions
- ✅ Agent continues from previous troubleshooting context
- ✅ Agent recalls platform architecture & resource IDs
- ✅ Agent adapts to user's systematic troubleshooting preference
- ✅ Agent applies proven EXAMPLECORP-specific procedures

### Key Benefits:
- **Eliminates repeated permission verification**
- **Maintains troubleshooting context across sessions**
- **Applies learned troubleshooting patterns**
- **Retains institutional knowledge and procedures**
- **Provides consistent, expert-level troubleshooting**

## Test Sequence (Recommended Order)

1. **Semantic Memory** (Foundation) - Establishes basic memory functionality
2. **User Preference** (Personalization) - Learns user communication style
3. **Summary Memory** (Session Context) - Tracks troubleshooting progress
4. **Custom Memory** (EXAMPLECORP Procedures) - Stores platform-specific knowledge
5. **Integration** (Complete Workflow) - Demonstrates all strategies working together

## Troubleshooting

If tests fail:
1. **Check memory resource exists**: `aws ssm get-parameter --name "/examplecorp/agentcore/memory_id"`
2. **Verify EC2 permissions**: Ensure IAM role allows EC2 describe operations
3. **Run tests in sequence**: Some tests may depend on data from previous tests
4. **Use `-s` flag**: Shows detailed debug output for troubleshooting
5. **Check AWS region**: Tests assume resources exist in the current region

## Integration with Module-1

The integration test demonstrates that:
- **No module-1 changes needed** - same runtime, enhanced with memory
- **Same troubleshooting workflow** - identical to `module-1/test/test_agent.py`
- **Seamless enhancement** - memory capabilities added automatically
- **Backward compatibility** - existing functionality preserved
