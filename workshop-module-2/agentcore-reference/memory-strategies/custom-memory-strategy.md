# Custom Memory Strategy - EXAMPLECORP Image Gallery Platform

## Overview

The Custom Memory Strategy supports **specific information storage based on customized prompts** tailored to the EXAMPLECORP Image Gallery Platform. This strategy uses custom extraction prompts to capture platform-specific configurations, procedures, and domain knowledge that don't fit into the standard memory categories.

## Strategy Configuration

### **Primary Purpose**
Store EXAMPLECORP platform-specific information using custom extraction logic:
- Platform configuration details and resource mappings
- Standard operating procedures and runbooks
- Domain-specific troubleshooting workflows
- Custom business logic and rules
- Integration patterns and dependencies

### **Memory Namespaces**
```
troubleshooting/platform/examplecorp/config
troubleshooting/platform/examplecorp/procedures
troubleshooting/platform/examplecorp/workflows
troubleshooting/platform/examplecorp/integrations
```

### **Strategy Definition**
```json
{
  "type": "CUSTOM",
  "name": "examplecorp_platform_config",
  "description": "Stores EXAMPLECORP platform configurations and custom procedures using specialized extraction prompts",
  "namespaces": [
    "troubleshooting/platform/examplecorp/config",
    "troubleshooting/platform/examplecorp/procedures",
    "troubleshooting/platform/examplecorp/workflows",
    "troubleshooting/platform/examplecorp/integrations"
  ],
  "custom_prompt": "Extract EXAMPLECORP Image Gallery Platform-specific information including: 1) AWS resource configurations (ALB, RDS, S3, Transit Gateway), 2) Network connectivity patterns between VPCs, 3) Standard troubleshooting procedures for platform outages, 4) Workshop module integration workflows, 5) Performance monitoring thresholds and alerts. Focus on actionable technical details and operational procedures."
}
```

## EXAMPLECORP Platform Use Cases

### **Use Case 1: Platform Configuration Storage**

**Scenario**: Agent learns comprehensive EXAMPLECORP platform configuration during troubleshooting sessions.

**Input Conversation**:
```
User: "The EXAMPLECORP platform has ALB sample-app-image-sharing-alb-123456789.us-east-1.elb.amazonaws.com"
User: "Database is sample-app-image-metadata-db.cluster-xyz.us-east-1.rds.amazonaws.com"
User: "S3 bucket is sample-app-123456789-image-stack-name"
User: "Transit Gateway tgw-0123456789abcdef0 connects App VPC 10.2.0.0/16 to Reporting VPC 10.1.0.0/16"
```

**Custom Memory Storage**:
```json
{
  "namespace": "troubleshooting/platform/examplecorp/config",
  "content": {
    "platform_name": "EXAMPLECORP Image Gallery Platform",
    "app_id": "EXAMPLECORP-IMG-GALLERY-001",
    "infrastructure": {
      "alb": {
        "dns_name": "sample-app-image-sharing-alb-123456789.us-east-1.elb.amazonaws.com",
        "target_groups": ["html-renderer", "image-processor", "user-interactions"]
      },
      "database": {
        "endpoint": "sample-app-image-metadata-db.cluster-xyz.us-east-1.rds.amazonaws.com",
        "port": 3306,
        "vpc": "10.2.0.0/16",
        "private_subnets": ["10.2.3.0/24", "10.2.4.0/24"]
      },
      "storage": {
        "s3_bucket": "sample-app-123456789-image-stack-name",
        "image_path": "/images/",
        "frontend_path": "/frontend/"
      },
      "networking": {
        "transit_gateway": "tgw-0123456789abcdef0",
        "app_vpc": "10.2.0.0/16",
        "reporting_vpc": "10.1.0.0/16",
        "connectivity_pattern": "reporting_to_database_via_tgw"
      }
    },
    "extracted_at": "2024-01-15T10:30:00Z"
  }
}
```

### **Use Case 2: Standard Operating Procedures**

**Scenario**: Agent learns EXAMPLECORP-specific troubleshooting procedures and runbooks.

**Input Conversation**:
```
User: "For EXAMPLECORP platform outages, we always check ALB health first, then Lambda functions, then database connectivity"
User: "The standard procedure is: 1) Verify ALB target groups, 2) Check Lambda logs, 3) Test database from reporting server, 4) Verify Transit Gateway routes"
User: "If reporting server can't reach database, add 10.1.0.0/16 to database security group on port 3306"
```

**Custom Memory Storage**:
```json
{
  "namespace": "troubleshooting/platform/examplecorp/procedures",
  "content": {
    "procedure_name": "EXAMPLECORP Platform Outage Response",
    "trigger": "platform_unavailable_or_connectivity_issues",
    "steps": [
      {
        "step": 1,
        "action": "verify_alb_target_groups",
        "description": "Check ALB target group health and registration",
        "expected_result": "all_targets_healthy",
        "troubleshooting": "restart_unhealthy_lambda_functions"
      },
      {
        "step": 2,
        "action": "check_lambda_logs",
        "description": "Review CloudWatch logs for Lambda function errors",
        "log_groups": ["/aws/lambda/sample-app-html-renderer", "/aws/lambda/sample-app-image-processor", "/aws/lambda/sample-app-user-interactions"],
        "common_errors": ["database_connection_timeout", "s3_access_denied"]
      },
      {
        "step": 3,
        "action": "test_database_connectivity",
        "description": "Test database connection from reporting server",
        "test_command": "mysql -h database.examplecorp.com -u admin -p",
        "expected_result": "successful_connection"
      },
      {
        "step": 4,
        "action": "verify_transit_gateway_routes",
        "description": "Check TGW route tables for cross-VPC connectivity",
        "routes_to_verify": ["10.1.0.0/16 -> App VPC", "10.2.0.0/16 -> Reporting VPC"]
      }
    ],
    "common_fixes": {
      "reporting_database_connectivity": {
        "issue": "reporting_server_cannot_connect_to_database",
        "solution": "add_reporting_vpc_cidr_to_database_security_group",
        "command": "aws ec2 authorize-security-group-ingress --group-id sg-database --protocol tcp --port 3306 --cidr 10.1.0.0/16",
        "success_rate": "95%"
      }
    }
  }
}
```

### **Use Case 3: Workshop Integration Workflows**

**Scenario**: Agent learns how workshop progress integrates with platform troubleshooting.

**Input Conversation**:
```
User: "When users post correspondence in TKT-SEV1-001, their workshop progress advances by 25%"
User: "The workshop has 4 modules: AgentCore Memory, AgentCore Runtime, A2A, CloudWatch Investigations"
User: "Progress is stored in RDS and persists across browser sessions"
```

**Custom Memory Storage**:
```json
{
  "namespace": "troubleshooting/platform/examplecorp/workflows",
  "content": {
    "workflow_name": "workshop_progress_integration",
    "trigger": "support_ticket_correspondence",
    "integration_points": {
      "ticket_system": {
        "primary_ticket": "TKT-SEV1-001",
        "title": "EXAMPLECORP Image Platform is down",
        "progress_trigger": "user_correspondence_posted"
      },
      "workshop_modules": [
        {
          "name": "AgentCore Memory",
          "order": 2,
          "progress_increment": 25,
          "completion_criteria": "4_correspondences_posted"
        },
        {
          "name": "AgentCore Runtime", 
          "order": 1,
          "progress_increment": 25,
          "completion_criteria": "connectivity_troubleshooting_completed"
        },
        {
          "name": "A2A",
          "order": 3,
          "progress_increment": 25,
          "completion_criteria": "agent_collaboration_demonstrated"
        },
        {
          "name": "CloudWatch Investigations",
          "order": 4,
          "progress_increment": 25,
          "completion_criteria": "performance_monitoring_completed"
        }
      ],
      "persistence_mechanism": {
        "storage": "RDS_database",
        "table": "workshop_modules",
        "session_independence": true,
        "progress_calculation": "correspondence_count * 25"
      }
    }
  }
}
```

## Implementation Details

### **Custom Extraction Prompt**

The custom memory strategy uses a specialized prompt for extracting EXAMPLECORP-specific information:

```
Extract EXAMPLECORP Image Gallery Platform-specific information including:

1) AWS Resource Configurations:
   - ALB DNS names and target group mappings
   - RDS database endpoints and connection details
   - S3 bucket names and access patterns
   - Transit Gateway IDs and routing configurations
   - Lambda function names and purposes

2) Network Connectivity Patterns:
   - VPC CIDR blocks and subnet configurations
   - Cross-VPC connectivity via Transit Gateway
   - Security group rules and NACL configurations
   - DNS resolution patterns (examplecorp.com private zone)

3) Standard Troubleshooting Procedures:
   - Step-by-step outage response procedures
   - Common connectivity issues and solutions
   - Performance monitoring thresholds
   - Escalation procedures and contact information

4) Workshop Module Integration:
   - Progress tracking mechanisms
   - Module completion criteria
   - Cross-session persistence patterns
   - User interaction workflows

5) Business Logic and Rules:
   - Permission group requirements (imaging-ops@examplecorp.com)
   - SLA requirements and recovery objectives
   - Compliance and security controls
   - Operational procedures and runbooks

Focus on actionable technical details, specific resource identifiers, and operational procedures that enable efficient troubleshooting and platform management.
```

### **Memory Hook Integration**

```python
def extract_custom_examplecorp_information(self, conversation_text):
    """Extract EXAMPLECORP-specific information using custom prompt"""
    
    # Check if conversation contains EXAMPLECORP platform information
    examplecorp_indicators = [
        "sample-app-", "examplecorp.com", "TKT-SEV1-001", 
        "imaging-ops@examplecorp.com", "10.1.0.0/16", "10.2.0.0/16",
        "transit gateway", "reporting server", "database connectivity"
    ]
    
    if any(indicator in conversation_text.lower() for indicator in examplecorp_indicators):
        # Apply custom extraction prompt
        extracted_info = self.apply_custom_extraction_prompt(conversation_text)
        
        # Store in appropriate namespace based on content type
        if "resource" in extracted_info or "configuration" in extracted_info:
            namespace = "troubleshooting/platform/examplecorp/config"
        elif "procedure" in extracted_info or "steps" in extracted_info:
            namespace = "troubleshooting/platform/examplecorp/procedures"
        elif "workshop" in extracted_info or "progress" in extracted_info:
            namespace = "troubleshooting/platform/examplecorp/workflows"
        else:
            namespace = "troubleshooting/platform/examplecorp/integrations"
            
        return namespace, extracted_info
    
    return None, None
```

## Testing Custom Memory

### **Test Script**: `test/test_memory_validation.py`

```python
def test_custom_memory_examplecorp_config():
    """Test EXAMPLECORP platform configuration extraction and storage"""
    memory_client = MemoryClient()
    
    # Test configuration extraction
    config_conversation = [
        ("The ALB DNS is sample-app-image-sharing-alb-123456789.us-east-1.elb.amazonaws.com", "user"),
        ("Database endpoint is sample-app-image-metadata-db.cluster-xyz.us-east-1.rds.amazonaws.com", "user"),
        ("Transit Gateway tgw-0123456789abcdef0 connects the VPCs", "user")
    ]
    
    for msg, role in config_conversation:
        memory_client.save_conversation(
            memory_id=MEMORY_ID,
            actor_id="test_user",
            session_id="config_session",
            messages=[(msg, role)]
        )
    
    # Test configuration retrieval
    config_memories = memory_client.retrieve_memories(
        memory_id=MEMORY_ID,
        namespace="troubleshooting/platform/examplecorp/config",
        query="EXAMPLECORP platform ALB database configuration",
        top_k=3
    )
    
    # Verify: Should extract and store EXAMPLECORP platform configuration
    assert len(config_memories) > 0
    config_text = str(config_memories)
    assert "sample-app-image-sharing-alb" in config_text
    assert "sample-app-image-metadata-db" in config_text
    assert "tgw-0123456789abcdef0" in config_text

def test_custom_memory_procedures():
    """Test EXAMPLECORP troubleshooting procedure extraction"""
    memory_client = MemoryClient()
    
    # Test procedure extraction
    procedure_conversation = [
        ("For EXAMPLECORP outages, first check ALB health, then Lambda logs, then database connectivity", "user"),
        ("If reporting server can't reach database, add 10.1.0.0/16 to database security group", "user")
    ]
    
    for msg, role in procedure_conversation:
        memory_client.save_conversation(
            memory_id=MEMORY_ID,
            actor_id="test_user",
            session_id="procedure_session",
            messages=[(msg, role)]
        )
    
    # Test procedure retrieval
    procedure_memories = memory_client.retrieve_memories(
        memory_id=MEMORY_ID,
        namespace="troubleshooting/platform/examplecorp/procedures",
        query="EXAMPLECORP platform outage troubleshooting procedure",
        top_k=3
    )
    
    # Verify: Should extract troubleshooting procedures
    assert len(procedure_memories) > 0
    procedure_text = str(procedure_memories)
    assert "ALB health" in procedure_text or "database connectivity" in procedure_text
```

### **Manual Testing Procedure**

1. **Test Configuration Extraction**:
   ```bash
   # Provide EXAMPLECORP platform details in conversation
   # Expected: Custom memory extracts and categorizes configuration information
   ```

2. **Test Procedure Learning**:
   ```bash
   # Describe EXAMPLECORP-specific troubleshooting procedures
   # Expected: Custom memory stores procedures in structured format
   ```

3. **Test Workflow Integration**:
   ```bash
   # Explain workshop progress integration
   # Expected: Custom memory captures workflow patterns
   ```

## Performance Characteristics

### **Extraction Efficiency**
- **Custom Prompt Processing**: 200-500ms for complex extractions
- **Information Categorization**: Automatic namespace assignment
- **Structured Storage**: JSON-formatted for easy retrieval

### **Retrieval Performance**
- **Query Speed**: < 100ms for configuration lookups
- **Context Relevance**: High precision for EXAMPLECORP-specific queries
- **Cross-Reference Capability**: Links related configurations and procedures

### **Memory Footprint**
- **Configuration Records**: ~2KB per platform configuration set
- **Procedure Documentation**: ~1-3KB per procedure
- **Workflow Definitions**: ~1KB per workflow pattern

## Troubleshooting

### **Common Issues**

#### **Issue 1: Custom Extraction Not Working**
```bash
# Symptoms: EXAMPLECORP-specific information not being extracted
# Debug: Check custom prompt application
python3 test/test_memory_validation.py --strategy custom --debug

# Expected output:
# ✅ Custom memory namespace accessible
# ✅ EXAMPLECORP configuration extracted: ALB, Database, TGW
# ✅ Procedure extraction: outage_response_steps
```

#### **Issue 2: Information Miscategorized**
```bash
# Symptoms: Information stored in wrong namespace
# Debug: Check namespace assignment logic
memory_client.retrieve_memories(
    memory_id=MEMORY_ID,
    namespace="troubleshooting/platform/examplecorp/config",
    query="all EXAMPLECORP configurations",
    top_k=10
)
```

#### **Issue 3: Custom Prompt Not Applied**
```bash
# Symptoms: Generic extraction instead of EXAMPLECORP-specific
# Check: Custom prompt configuration
# Verify: EXAMPLECORP indicator detection
# Debug: Enable custom extraction logs
```

## Best Practices

### **Information to Store in Custom Memory**
✅ **Good for Custom Memory**:
- Platform-specific configurations and mappings
- Domain-specific procedures and workflows
- Business logic and operational rules
- Integration patterns and dependencies
- Custom troubleshooting methodologies

❌ **Not Suitable for Custom Memory**:
- Generic troubleshooting steps
- User-specific preferences or permissions
- Temporary session data
- Standard AWS service documentation

### **Namespace Organization**
```
troubleshooting/platform/examplecorp/config        # Platform configurations
troubleshooting/platform/examplecorp/procedures    # Standard operating procedures
troubleshooting/platform/examplecorp/workflows     # Business process workflows
troubleshooting/platform/examplecorp/integrations  # System integration patterns
```

### **Custom Prompt Guidelines**
- **Be Specific**: Target exact information types needed
- **Use Structure**: Request JSON or structured format
- **Include Context**: Specify domain and use case
- **Define Scope**: Clearly outline what to extract vs. ignore

## Integration with Other Strategies

### **Custom + Semantic Memory**
```
Custom: Stores "EXAMPLECORP platform ALB DNS: sample-app-image-sharing-alb-123..."
Semantic: Stores "User has imaging-ops@examplecorp.com permissions"
Combined: Agent knows platform resources AND user access rights
```

### **Custom + Summary Memory**
```
Custom: Stores "EXAMPLECORP outage procedure: check ALB → Lambda → Database"
Summary: Stores "User completed ALB verification step"
Combined: Agent follows EXAMPLECORP procedure and tracks progress
```

### **Custom + User Preference Memory**
```
Custom: Stores "EXAMPLECORP procedure: systematic step-by-step approach"
User Preference: Learns "User prefers systematic troubleshooting"
Combined: Agent applies EXAMPLECORP procedures in user's preferred style
```

## Advanced Custom Extraction

### **Multi-Domain Information Extraction**
```python
def extract_multi_domain_info(self, conversation_text):
    """Extract information across multiple EXAMPLECORP domains"""
    
    domains = {
        'infrastructure': ['alb', 'rds', 's3', 'lambda', 'vpc'],
        'networking': ['transit gateway', 'security group', 'nacl', 'route'],
        'procedures': ['troubleshoot', 'procedure', 'steps', 'runbook'],
        'monitoring': ['cloudwatch', 'metrics', 'alerts', 'performance']
    }
    
    extracted_domains = {}
    for domain, keywords in domains.items():
        if any(keyword in conversation_text.lower() for keyword in keywords):
            extracted_domains[domain] = self.extract_domain_specific_info(conversation_text, domain)
    
    return extracted_domains
```

### **Contextual Information Linking**
```python
def link_related_information(self, new_info, existing_memories):
    """Link new information with existing related memories"""
    
    # Find related configurations
    if 'database' in new_info and 'connectivity' in new_info:
        related_configs = self.find_related_configs(['database', 'security_group', 'vpc'])
        new_info['related_resources'] = related_configs
    
    # Link procedures to configurations
    if 'procedure' in new_info:
        applicable_configs = self.find_applicable_configs(new_info['procedure'])
        new_info['applicable_to'] = applicable_configs
    
    return new_info
```

## Monitoring and Metrics

### **Key Metrics**
- **Extraction Accuracy**: % of EXAMPLECORP-specific information correctly extracted
- **Categorization Precision**: % of information stored in correct namespaces
- **Retrieval Relevance**: % of queries returning relevant EXAMPLECORP information
- **Cross-Reference Success**: % of related information successfully linked

### **CloudWatch Metrics**
```
Namespace: AgentCore/Memory/EXAMPLECORP/Custom
Metrics:
- CustomExtractionAccuracy
- CategorizationPrecision
- EXAMPLECORPInformationCoverage
- CrossReferenceSuccess
```

## Business Value

### **Operational Efficiency**
- **Reduced Learning Curve**: New team members access institutional knowledge
- **Consistent Procedures**: Standardized troubleshooting approaches
- **Faster Resolution**: Quick access to platform-specific solutions
- **Knowledge Retention**: Preserves expertise across team changes

### **Platform Reliability**
- **Proactive Monitoring**: Stored thresholds and alert configurations
- **Predictive Troubleshooting**: Historical patterns inform future issues
- **Automated Procedures**: Codified responses to common problems
- **Continuous Improvement**: Learning from each troubleshooting session

---

**Success Criteria**: Custom memory successfully extracts, stores, and retrieves EXAMPLECORP Image Gallery Platform-specific configurations, procedures, and workflows, enabling efficient and consistent troubleshooting operations for the platform outage scenario.
