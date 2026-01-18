# Sample App Memory Configuration - EXAMPLECORP Image Gallery Platform

## Overview

This document provides the complete memory configuration for integrating AgentCore Memory with the EXAMPLECORP Image Gallery Platform. It includes specific configurations, code examples, and integration patterns based on the actual sample application architecture.

## Memory Configuration for EXAMPLECORP Platform

### **Memory Resource Setup**

Based on `stage-3/agentcore-reference/scripts/setup_memory.py`:

```python
def setup_examplecorp_memory():
    """Setup memory specifically for EXAMPLECORP Image Gallery Platform"""
    
    memory_name = "EXAMPLECORPImageGalleryMemory"
    ssm_param = "/app/troubleshooting/agentcore/memory_id"
    event_expiry_days = 30
    
    strategies = [
        {
            StrategyType.SEMANTIC.value: {
                "name": "examplecorp_permission_extractor",
                "description": "Extracts and stores imaging-ops@examplecorp.com permissions and EXAMPLECORP platform knowledge",
                "namespaces": [
                    "troubleshooting/user/{actorId}/permissions",
                    "troubleshooting/platform/examplecorp/knowledge",
                    "troubleshooting/platform/examplecorp/resources"
                ],
            },
        },
        {
            StrategyType.SUMMARY.value: {
                "name": "examplecorp_workshop_tracker", 
                "description": "Tracks workshop progress and troubleshooting decisions for EXAMPLECORP platform",
                "namespaces": [
                    "troubleshooting/user/{actorId}/workshop",
                    "troubleshooting/user/{actorId}/{sessionId}",
                    "troubleshooting/tickets/{ticketId}/summary"
                ],
            },
        },
        {
            StrategyType.USER_PREFERENCE.value: {
                "name": "examplecorp_troubleshooting_patterns",
                "description": "Learns troubleshooting patterns and preferred solutions for EXAMPLECORP platform users",
                "namespaces": [
                    "troubleshooting/user/{actorId}/patterns",
                    "troubleshooting/user/{actorId}/preferences",
                    "troubleshooting/platform/examplecorp/solutions"
                ],
            },
        },
        {
            StrategyType.CUSTOM.value: {
                "name": "examplecorp_platform_config",
                "description": "Stores EXAMPLECORP platform configurations and custom procedures using specialized extraction prompts",
                "namespaces": [
                    "troubleshooting/platform/examplecorp/config",
                    "troubleshooting/platform/examplecorp/procedures", 
                    "troubleshooting/platform/examplecorp/workflows",
                    "troubleshooting/platform/examplecorp/integrations"
                ],
                "custom_prompt": "Extract EXAMPLECORP Image Gallery Platform-specific information including: 1) AWS resource configurations (ALB, RDS, S3, Transit Gateway), 2) Network connectivity patterns between VPCs, 3) Standard troubleshooting procedures for platform outages, 4) Workshop module integration workflows, 5) Performance monitoring thresholds and alerts. Focus on actionable technical details and operational procedures."
            },
        },
    ]
    
    try:
        memory = memory_client.create_memory_and_wait(
            name=memory_name,
            strategies=strategies,
            description="Memory for EXAMPLECORP Image Gallery Platform - stores user permissions, workshop progress, troubleshooting patterns, and platform-specific configurations",
            event_expiry_days=event_expiry_days,
        )
        
        memory_id = memory["id"]
        store_memory_id_in_ssm(ssm_param, memory_id)
        
        print("✅ EXAMPLECORP Image Gallery Memory setup complete!")
        print(f"   Memory ID: {memory_id}")
        print(f"   SSM Parameter: {ssm_param}")
        return memory_id
        
    except Exception as e:
        if "already exists" in str(e):
            # Handle existing memory
            memories = memory_client.list_memories()
            memory_id = next(
                (m["id"] for m in memories if memory_name in m.get("name", "")), None
            )
            if memory_id:
                store_memory_id_in_ssm(ssm_param, memory_id)
                print("✅ Using existing EXAMPLECORP memory")
                return memory_id
        
        print(f"❌ Failed to setup EXAMPLECORP memory: {e}")
        raise
```

## Integration with Sample Application

### **Memory Hook Configuration**

Based on `stage-3/agentcore-reference/agent_config/memory_hook_provider.py`, here's the EXAMPLECORP-specific memory hook:

```python
class EXAMPLECORPMemoryHook(MemoryHook):
    def __init__(self, memory_client: MemoryClient, memory_id: str, actor_id: str, session_id: str):
        super().__init__(memory_client, memory_id, actor_id, session_id)
        self.examplecorp_config = self._load_examplecorp_config()
    
    def _load_examplecorp_config(self):
        """Load EXAMPLECORP platform-specific configuration"""
        return {
            "platform_name": "EXAMPLECORP Image Gallery Platform",
            "app_id": "EXAMPLECORP-IMG-GALLERY-001",
            "permission_group": "imaging-ops@examplecorp.com",
            "primary_ticket": "TKT-SEV1-001",
            "workshop_modules": [
                "AgentCore Runtime",
                "AgentCore Memory", 
                "A2A",
                "CloudWatch Investigations"
            ]
        }
    
    def on_agent_initialized(self, event: AgentInitializedEvent):
        """Load EXAMPLECORP platform context when agent starts"""
        try:
            # Load recent conversation history (last 5 turns)
            recent_turns = self.memory_client.get_last_k_turns(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
                k=5,
            )

            if recent_turns:
                # Format conversation history for EXAMPLECORP context
                context_messages = []
                for turn in recent_turns:
                    for message in turn:
                        role = "assistant" if message["role"] == "ASSISTANT" else "user"
                        content = message["content"]["text"]
                        context_messages.append(
                            {"role": role, "content": [{"text": content}]}
                        )

                # Add EXAMPLECORP-specific system prompt context
                event.agent.system_prompt += f"""

EXAMPLECORP PLATFORM CONTEXT:
- Platform: {self.examplecorp_config['platform_name']}
- App ID: {self.examplecorp_config['app_id']}
- Current Issue: Platform outage (TKT-SEV1-001)
- User Permission Group: {self.examplecorp_config['permission_group']}
- Workshop Modules: {', '.join(self.examplecorp_config['workshop_modules'])}

Do not ask for user permissions if already stored in memory.
Use stored EXAMPLECORP platform knowledge for troubleshooting guidance.
Track workshop progress through support ticket interactions.
"""
                event.agent.messages = context_messages

        except Exception as e:
            print(f"EXAMPLECORP Memory load error: {e}")

    def on_message_added(self, event: MessageAddedEvent):
        """Store EXAMPLECORP-specific context and update workshop progress"""
        messages = copy.deepcopy(event.agent.messages)
        
        try:
            if messages[-1]["role"] == "user" or messages[-1]["role"] == "assistant":
                if "text" not in messages[-1]["content"][0]:
                    return

                message_text = messages[-1]["content"][0]["text"]

                if messages[-1]["role"] == "user":
                    # Add EXAMPLECORP permission context
                    self._add_context_user_query(
                        namespace=f"troubleshooting/user/{self.actor_id}/permissions",
                        query=message_text,
                        init_content="User permissions (do not ask again if already known):",
                        event=event,
                    )

                    # Add EXAMPLECORP platform knowledge context
                    self._add_context_user_query(
                        namespace=f"troubleshooting/platform/examplecorp/knowledge",
                        query=message_text,
                        init_content="EXAMPLECORP platform knowledge:",
                        event=event,
                    )
                    
                    # Add EXAMPLECORP troubleshooting procedures context
                    self._add_context_user_query(
                        namespace=f"troubleshooting/platform/examplecorp/procedures",
                        query=message_text,
                        init_content="EXAMPLECORP troubleshooting procedures:",
                        event=event,
                    )

                # Store conversation for all memory strategies
                self.memory_client.save_conversation(
                    memory_id=self.memory_id,
                    actor_id=self.actor_id,
                    session_id=self.session_id,
                    messages=[
                        (message_text, messages[-1]["role"])
                    ],
                )
                
                # Update workshop progress if this is correspondence activity
                if self._is_correspondence_activity(message_text):
                    self._update_workshop_progress(message_text)

        except Exception as e:
            raise RuntimeError(f"EXAMPLECORP Memory save error: {e}")
    
    def _is_correspondence_activity(self, message_text):
        """Check if message represents correspondence activity"""
        correspondence_indicators = [
            "TKT-SEV1-001", "support ticket", "correspondence", 
            "platform outage", "connectivity issue", "troubleshooting",
            "reporting server", "database connectivity"
        ]
        return any(indicator in message_text.lower() for indicator in correspondence_indicators)
    
    def _update_workshop_progress(self, message_text):
        """Update workshop progress based on correspondence activity"""
        try:
            # This would integrate with the sample app's progress tracking
            # Based on sample-app.yaml correspondence system
            progress_update = {
                "activity": "correspondence_posted",
                "ticket_id": "TKT-SEV1-001",
                "message": message_text,
                "timestamp": datetime.now().isoformat(),
                "progress_increment": 25
            }
            
            # Store progress update in summary memory
            self.memory_client.save_conversation(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
                messages=[
                    (f"Workshop progress update: {progress_update}", "system")
                ],
            )
            
        except Exception as e:
            print(f"Workshop progress update error: {e}")
```

## Agent Configuration

### **EXAMPLECORP Troubleshooting Agent Setup**

Based on `stage-3/agentcore-reference/agent_config/agent.py`:

```python
class EXAMPLECORPTroubleshootingAgent(TroubleshootingAgent):
    def __init__(self, bearer_token: str, memory_hook: EXAMPLECORPMemoryHook = None):
        # EXAMPLECORP-specific system prompt
        examplecorp_system_prompt = """
You are an EXAMPLECORP Image Gallery Platform Troubleshooting Agent with specialized knowledge of the platform architecture and current outage scenario.

PLATFORM CONTEXT:
- Application: EXAMPLECORP Image Gallery Platform (EXAMPLECORP-IMG-GALLERY-001)
- Current Issue: TKT-SEV1-001 - "EXAMPLECORP Image Platform is down"
- Architecture: Multi-VPC (App VPC 10.2.0.0/16, Reporting VPC 10.1.0.0/16) connected via Transit Gateway
- Key Resources: ALB, Lambda functions, RDS database, S3 bucket, Reporting server

CONNECTIVITY ISSUE:
- Problem: Reporting server (10.1.2.x) cannot connect to RDS database (10.2.x.x)
- Connection Path: Reporting VPC → Transit Gateway → App VPC → Database
- Common Solution: Add 10.1.0.0/16 CIDR to database security group on port 3306

MEMORY INTEGRATION:
- Remember user permissions (imaging-ops@examplecorp.com) - do not ask repeatedly
- Track workshop progress through correspondence interactions
- Use stored EXAMPLECORP platform knowledge for efficient troubleshooting
- Learn user troubleshooting preferences and adapt responses

WORKSHOP PROGRESS:
- Each correspondence in TKT-SEV1-001 advances AgentCore Memory module by 25%
- Progress persists across browser sessions
- Modules: AgentCore Runtime → AgentCore Memory → A2A → CloudWatch Investigations

Your goal is to help resolve the platform outage while providing an educational experience that advances the user's workshop progress.
"""
        
        super().__init__(
            bearer_token=bearer_token,
            memory_hook=memory_hook,
            system_prompt=examplecorp_system_prompt
        )
```

## Database Integration

### **Workshop Progress Persistence**

Integration with the sample app's RDS database for workshop progress tracking:

```python
def integrate_with_sample_app_database():
    """Integrate memory system with sample app's workshop progress tracking"""
    
    # Based on sample-app.yaml Lambda function code
    def store_correspondence_and_update_progress(ticket_id, message, author, session_id=None):
        """Store correspondence and update workshop module progress"""
        try:
            conn = get_db_connection()
            
            with conn.cursor() as cursor:
                cursor.execute(f"USE {os.environ['DB_NAME']}")
                
                # Get the next correspondence ID for this ticket
                cursor.execute("""
                    SELECT COALESCE(MAX(correspondence_id), 0) + 1 as next_id
                    FROM sev1_correspondence_history 
                    WHERE ticket_id = %s
                """, (ticket_id,))
                
                next_correspondence_id = cursor.fetchone()['next_id']
                
                # Get current workshop module progress
                cursor.execute("""
                    SELECT module_name, display_name, current_progress, is_completed
                    FROM workshop_modules 
                    ORDER BY id
                """)
                
                modules = cursor.fetchall()
                current_module = None
                
                # Find the first incomplete module
                for module in modules:
                    if not module['is_completed']:
                        current_module = module
                        break
                
                module_updated = False
                module_completed = False
                
                if current_module:
                    # Update progress: each correspondence = 25% progress
                    old_progress = current_module['current_progress']
                    new_progress = min(old_progress + 25, 100)
                    module_completed = (new_progress >= 100)
                    
                    # Update module progress in database
                    cursor.execute("""
                        UPDATE workshop_modules 
                        SET current_progress = %s, 
                            is_completed = %s,
                            completion_date = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE module_name = %s
                    """, (new_progress, module_completed, 
                          datetime.now() if module_completed else None,
                          current_module['module_name']))
                    
                    # Store correspondence with module tracking
                    cursor.execute("""
                        INSERT INTO sev1_correspondence_history 
                        (ticket_id, correspondence_id, author, message, message_type, 
                         module_name, module_progress_before, module_progress_after, 
                         module_completed, session_id, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """, (ticket_id, next_correspondence_id, author, message, 'user',
                          current_module['module_name'], old_progress, new_progress,
                          module_completed, session_id))
                    
                    module_updated = True
                    
                    # Also store in AgentCore memory for cross-session persistence
                    memory_client = MemoryClient()
                    memory_id = get_memory_id_from_ssm("/app/troubleshooting/agentcore/memory_id")
                    
                    memory_client.save_conversation(
                        memory_id=memory_id,
                        actor_id=session_id or "default_user",
                        session_id=session_id or "default_session",
                        messages=[
                            (f"Workshop progress: {current_module['module_name']} {old_progress}% → {new_progress}%", "system")
                        ]
                    )
                
                return {
                    'success': True,
                    'correspondence_id': next_correspondence_id,
                    'moduleUpdated': module_updated,
                    'moduleCompleted': module_completed,
                    'moduleProgress': cursor.fetchall()
                }
                
        except Exception as e:
            print(f"Error storing correspondence and updating progress: {e}")
            raise Exception(f"Failed to store correspondence: {e}")
```

## Frontend Integration

### **Memory-Enhanced Progress Tracking**

Integration with the sample app's frontend for memory-persistent progress tracking:

```javascript
// Based on sample-app.yaml frontend code
async function postCorrespondenceWithMemory(ticketId) {
    const textarea = document.getElementById(`correspondence-input-${ticketId}`);
    const message = textarea.value.trim();
    
    if (!message) {
        alert('Please enter a message before posting.');
        return;
    }
    
    try {
        // Send correspondence to backend (integrates with memory system)
        const response = await fetch(`${API_BASE_URL}/api/correspondence`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ticketId: ticketId,
                message: message,
                author: 'Workshop Participant',
                sessionId: 'user-session-' + Date.now()
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            
            // Update UI with new correspondence
            addCorrespondenceToUI(ticketId, message, 'Workshop Participant');
            
            // Update workshop progress (now memory-persistent)
            if (result.moduleUpdated) {
                updateWorkshopProgressFromMemory(result.moduleProgress);
            }
            
            // Clear the textarea
            textarea.value = '';
            
        } else {
            throw new Error('Failed to post correspondence');
        }
    } catch (error) {
        console.error('Error posting correspondence:', error);
        alert('Failed to post correspondence. Please try again.');
    }
}

function updateWorkshopProgressFromMemory(moduleProgressData) {
    """Update progress bars with memory-persistent data"""
    if (moduleProgressData && Array.isArray(moduleProgressData)) {
        moduleProgressData.forEach((module, index) => {
            if (index < moduleProgress.length) {
                // Update progress from memory/database
                moduleProgress[index] = module.current_progress;
                if (module.current_progress >= 100) {
                    currentModuleIndex = Math.max(currentModuleIndex, index + 1);
                }
            }
        });
        updateProgressBars();
        
        // Store in browser for immediate UI updates
        localStorage.setItem('workshopProgress', JSON.stringify(moduleProgress));
    }
}

// Load progress from memory on page load
async function loadWorkshopProgressFromMemory() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/workshop-progress`);
        if (response.ok) {
            const progressData = await response.json();
            updateWorkshopProgressFromMemory(progressData);
        } else {
            // Fallback to localStorage if memory unavailable
            const savedProgress = localStorage.getItem('workshopProgress');
            if (savedProgress) {
                moduleProgress = JSON.parse(savedProgress);
                updateProgressBars();
            }
        }
    } catch (error) {
        console.error('Error loading workshop progress from memory:', error);
    }
}

// Initialize memory-enhanced progress tracking
document.addEventListener('DOMContentLoaded', () => {
    loadWorkshopProgressFromMemory();
});
```

## Configuration Files

### **Environment Configuration**

```bash
# Environment variables for EXAMPLECORP memory integration
export EXAMPLECORP_MEMORY_ID="mem-examplecorp-img-gallery-001"
export EXAMPLECORP_SSM_PARAM="/app/troubleshooting/agentcore/memory_id"
export EXAMPLECORP_PLATFORM_NAME="EXAMPLECORP Image Gallery Platform"
export EXAMPLECORP_APP_ID="EXAMPLECORP-IMG-GALLERY-001"
export EXAMPLECORP_PERMISSION_GROUP="imaging-ops@examplecorp.com"
export EXAMPLECORP_PRIMARY_TICKET="TKT-SEV1-001"
```

### **Memory Namespace Mapping**

```yaml
# EXAMPLECORP Memory Namespace Configuration
examplecorp_memory_namespaces:
  semantic:
    - "troubleshooting/user/{actorId}/permissions"
    - "troubleshooting/platform/examplecorp/knowledge"
    - "troubleshooting/platform/examplecorp/resources"
  
  summary:
    - "troubleshooting/user/{actorId}/workshop"
    - "troubleshooting/user/{actorId}/{sessionId}"
    - "troubleshooting/tickets/{ticketId}/summary"
  
  user_preference:
    - "troubleshooting/user/{actorId}/patterns"
    - "troubleshooting/user/{actorId}/preferences"
    - "troubleshooting/platform/examplecorp/solutions"
  
  custom:
    - "troubleshooting/platform/examplecorp/config"
    - "troubleshooting/platform/examplecorp/procedures"
    - "troubleshooting/platform/examplecorp/workflows"
    - "troubleshooting/platform/examplecorp/integrations"
```

## Testing Integration

### **End-to-End Integration Test**

```python
def test_examplecorp_memory_integration():
    """Test complete EXAMPLECORP platform memory integration"""
    
    # Test 1: Memory setup
    memory_id = setup_examplecorp_memory()
    assert memory_id is not None
    
    # Test 2: Agent initialization with memory
    memory_hook = EXAMPLECORPMemoryHook(
        memory_client=MemoryClient(),
        memory_id=memory_id,
        actor_id="test_user",
        session_id="test_session"
    )
    
    agent = EXAMPLECORPTroubleshootingAgent(
        bearer_token="test_token",
        memory_hook=memory_hook
    )
    
    # Test 3: Permission storage and recall
    test_permission_persistence(memory_hook)
    
    # Test 4: Workshop progress integration
    test_workshop_progress_integration(memory_hook)
    
    # Test 5: Platform knowledge storage
    test_platform_knowledge_storage(memory_hook)
    
    print("✅ EXAMPLECORP memory integration tests passed")

def test_permission_persistence(memory_hook):
    """Test permission storage and recall across sessions"""
    # Session 1: Store permission
    memory_hook.memory_client.save_conversation(
        memory_id=memory_hook.memory_id,
        actor_id=memory_hook.actor_id,
        session_id="session_1",
        messages=[("I belong to imaging-ops@examplecorp.com", "user")]
    )
    
    # Session 2: Should recall permission
    memories = memory_hook.memory_client.retrieve_memories(
        memory_id=memory_hook.memory_id,
        namespace=f"troubleshooting/user/{memory_hook.actor_id}/permissions",
        query="user permissions imaging-ops",
        top_k=1
    )
    
    assert len(memories) > 0
    assert "imaging-ops@examplecorp.com" in str(memories)

def test_workshop_progress_integration(memory_hook):
    """Test workshop progress tracking through memory"""
    # Simulate correspondence posting
    memory_hook._update_workshop_progress("Working on TKT-SEV1-001 connectivity issue")
    
    # Verify progress stored in memory
    memories = memory_hook.memory_client.retrieve_memories(
        memory_id=memory_hook.memory_id,
        namespace=f"troubleshooting/user/{memory_hook.actor_id}/workshop",
        query="workshop progress AgentCore Memory",
        top_k=1
    )
    
    assert len(memories) > 0
    assert "progress" in str(memories).lower()
```

## Troubleshooting Integration Issues

### **Common Integration Problems**

1. **Memory Not Persisting Across Sessions**
   ```bash
   # Check SSM parameter
   aws ssm get-parameter --name "/app/troubleshooting/agentcore/memory_id"
   
   # Verify memory client connectivity
   python3 -c "
   from bedrock_agentcore.memory import MemoryClient
   client = MemoryClient()
   print('Memory client connected:', client is not None)
   "
   ```

2. **Workshop Progress Not Updating**
   ```bash
   # Check database connectivity
   mysql -h database.examplecorp.com -u admin -p
   
   # Verify workshop_modules table
   SELECT * FROM workshop_modules;
   ```

3. **Permission Context Not Recalled**
   ```bash
   # Test semantic memory namespace
   python3 test/test_memory_validation.py --strategy semantic --debug
   ```

## Performance Optimization

### **Memory Query Optimization**
- Use specific namespace queries for faster retrieval
- Limit top_k to 3-5 for optimal performance
- Cache frequently accessed EXAMPLECORP configuration data
- Implement memory query result caching for repeated lookups

### **Database Integration Optimization**
- Use connection pooling for RDS connections
- Implement batch updates for workshop progress
- Cache workshop module configuration
- Optimize correspondence storage queries

---

**Success Criteria**: AgentCore Memory successfully integrates with the EXAMPLECORP Image Gallery Platform, providing persistent user permissions, workshop progress tracking, and platform-specific knowledge storage that enhances troubleshooting efficiency and learning outcomes.
