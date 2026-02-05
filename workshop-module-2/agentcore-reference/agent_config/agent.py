"""
=============================================================================
Memory-Enhanced TroubleshootingAgent (Module 2)
메모리 강화 TroubleshootingAgent (모듈 2)
=============================================================================

Description (설명):
    This module extends the base troubleshooting agent with a 3-tier memory
    system for context persistence across sessions.
    이 모듈은 세션 간 컨텍스트 유지를 위한 3계층 메모리 시스템으로
    기본 문제 해결 에이전트를 확장합니다.

Memory Tiers (메모리 계층):
    - Semantic Memory (365 days): Platform knowledge, SOPs
      시맨틱 메모리 (365일): 플랫폼 지식, SOP
    - Summary Memory (Session): Analysis results, PathIDs
      요약 메모리 (세션): 분석 결과, PathID
    - User Preference Memory (90 days): Communication style, preferences
      사용자 선호도 메모리 (90일): 커뮤니케이션 스타일, 선호도

Environment Variables (환경변수):
    BEDROCK_MODEL_ID: Override default Claude model
                      기본 Claude 모델 오버라이드

Author: NetAIOps Team
Module: workshop-module-2
=============================================================================
"""

# =============================================================================
# Imports (임포트)
# =============================================================================
from .memory_hook_provider import MemoryHook          # Memory hook for 3-tier persistence (3계층 유지용 메모리 훅)
from .utils import get_ssm_parameter                  # SSM parameter retrieval (SSM 파라미터 조회)
from mcp.client.streamable_http import streamablehttp_client  # MCP HTTP client (MCP HTTP 클라이언트)
from strands import Agent                             # Strands AI Agent framework (Strands AI 에이전트 프레임워크)
from strands_tools import current_time                # Time utility tool (시간 유틸리티 도구)
from strands.models import BedrockModel               # Bedrock model wrapper (Bedrock 모델 래퍼)
from strands.tools.mcp import MCPClient               # MCP client for tool integration (도구 통합용 MCP 클라이언트)
import logging
import os

# Configure module logger (모듈 로거 설정)
logger = logging.getLogger(__name__)

# =============================================================================
# Default Configuration (기본 설정)
# =============================================================================
# Default model ID - Can be overridden via BEDROCK_MODEL_ID environment variable
# 기본 모델 ID - BEDROCK_MODEL_ID 환경변수로 오버라이드 가능
DEFAULT_MODEL_ID = "global.anthropic.claude-opus-4-5-20251101-v1:0"


class TroubleshootingAgent:
    """
    Memory-enhanced AI network troubleshooting agent.
    메모리 강화 AI 네트워크 문제 해결 에이전트.

    Extends basic troubleshooting with 3-tier memory system for
    persistent context and learning across sessions.
    세션 간 지속적인 컨텍스트와 학습을 위해
    3계층 메모리 시스템으로 기본 문제 해결을 확장합니다.
    """

    def __init__(
        self,
        bearer_token: str,
        memory_hook: MemoryHook = None,
        bedrock_model_id: str = None,
        system_prompt: str = None,
    ):
        """
        Initialize the Memory-Enhanced TroubleshootingAgent.
        메모리 강화 TroubleshootingAgent 초기화.

        Args (인자):
            bearer_token (str): Authentication token for MCP gateway
                               MCP 게이트웨이 인증 토큰
            memory_hook (MemoryHook, optional): 3-tier memory hook
                                               3계층 메모리 훅
            bedrock_model_id (str, optional): Override model ID
                                             모델 ID 오버라이드
            system_prompt (str, optional): Custom system prompt
                                          사용자 정의 시스템 프롬프트
        """
        # Determine model ID with priority: env var > parameter > default
        # 우선순위에 따라 모델 ID 결정: 환경변수 > 파라미터 > 기본값
        if bedrock_model_id is None:
            bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', DEFAULT_MODEL_ID)

        self.model_id = bedrock_model_id

        # Initialize Bedrock model (Bedrock 모델 초기화)
        self.model = BedrockModel(
            model_id=self.model_id,
        )

        # Store memory hook for 3-tier memory system (3계층 메모리 시스템용 메모리 훅 저장)
        self.memory_hook = memory_hook
        
        self.system_prompt = (
            system_prompt
            if system_prompt
            else """
You are a Memory-Enhanced Troubleshooting Agent with DNS resolution, connectivity analysis, and CloudWatch monitoring capabilities.

## MEMORY-ENHANCED APPROACH:
**CRITICAL**: When you see "=== MEMORY CONTEXT FOR RESPONSE ===" sections in your system prompt, you MUST use that exact information in your response.

**MEMORY INTEGRATION RULES**:
1. **SEMANTIC MEMORY**: Start with exact permission/architecture information from memory, then offer troubleshooting assistance.
2. **USER PREFERENCE MEMORY**: Use stored communication preferences and SOP procedures. ALWAYS tag with [User Preference Memory].
3. **SUMMARY MEMORY**: Use EXACT session context and PathID information from memory. Do NOT run connectivity analysis again if PathID and results are already stored.
4. **VERBATIM QUOTE RULES**: When memory contains specific information (permissions, PathIDs, procedures), quote it exactly.
5. **CRITICAL**: NEVER use [Custom Memory] tag. Only use [Semantic Memory], [User Preference Memory], or [Summarization Memory].

**CRITICAL SUMMARIZATION MEMORY RULES**:
When you see "STRATEGY: SUMMARIZATION MEMORY" in your system prompt:
- **NEVER** call dns-resolve, connectivity (with action="check"), or cloudwatch-monitoring tools
- **FORBIDDEN ACTIONS**: Do NOT resolve hostnames, do NOT run fresh connectivity analysis
- **DIRECT ACTION ONLY**: When user asks to apply fix, use ONLY connectivity tool with action="fix"
- **SKIP REDUNDANT STEPS**: Do NOT re-analyze what was already completed in previous session
- **MANDATORY FLOW**: Memory retrieval → Summarize findings → Ask to apply fix → Direct fix application

**SUMMARIZATION MEMORY WORKFLOW**:
1. **Session Recovery Questions** ("System crashed, where were we?"):
   - Retrieve stored analysis results from memory
   - Summarize: "Based on our previous session, we identified [issue from memory]"
   - State: "The analysis is complete. Would you like me to apply the fix now?"
   - Tag response with [Summarization Memory]

2. **Fix Application** ("Yes, apply the fix"):
   - Do NOT run dns-resolve or connectivity analysis
   - Go DIRECTLY to connectivity tool with action="fix" 
   - Use stored PathID/instance information from memory
   - Apply security group fix immediately

**CRITICAL RULES FOR MEMORY USAGE**:
- If memory shows "PathID: nip-xxxxx" and "Status: Analysis completed", do NOT run connectivity analysis again
- If memory shows specific support tickets or procedures, reference them exactly as stored
- If memory shows "I belong to imaging-ops@examplecorp.com", start response with "Yes, you belong to imaging-ops@examplecorp.com"
- Always end responses with the memory strategy tag shown in the memory context
- Memory provides specific context and previous work - use it to avoid duplicate analysis while still offering tool-based help for new problems.

**SUMMARIZATION MEMORY OVERRIDE
- When in summarization memory mode, memory context takes absolute precedence over default tool usage patterns

## AVAILABLE TOOLS:

### From lambda-dns:
- **dns-resolve** - Resolves DNS hostnames from Route 53 Private Hosted Zones to EC2 instances or ENIs

### From lambda-connectivity:
- **connectivity** - Analyzes network paths and can fix connectivity issues by applying security group rules (fix action REQUIRES user consent)

### From lambda-cloudwatch:
- **cloudwatch-monitoring** - Comprehensive CloudWatch monitoring for alarms, metrics, and logs analysis

## WORKFLOW:

### For DNS Resolution:
Use **dns-resolve** when working with DNS hostnames instead of instance IDs:
- Required parameter: `hostname` (e.g., "app-frontend.examplecorp.com")
- Optional parameters: `dns_name` (alternative to hostname), `region` (default: us-east-1)
- Always call dns-resolve FIRST before connectivity analysis when using DNS names

### For Connectivity Analysis and Fixes:
Use **connectivity** to analyze network paths and optionally fix issues:
- Required parameters: `source_resource`, `destination_resource`
- Optional parameters: `query`, `protocol` (TCP/UDP/ICMP), `port`, `action`, `session_id`
- `action` parameter: "check" for analysis only, "fix" to analyze and apply fixes (REQUIRES user consent)

**CRITICAL DATABASE CONNECTIVITY RULES:**
- **Source**: should ALWAYS use EC2 instance ID (e.g., i-1234567890abcdef0) or ENI ID (e.g,eni-02158306ab0d81c67 )- NEVER use IPs
- **Database Destination**: If destination contains "database" in hostname, ALWAYS use the resolved IP address - NEVER use ENI IDs or Instance IDs
- **Non-Database Destination**: Use EC2 instance ID if available, otherwise IP address
- **Port**: Database connections default to port 3306 (MySQL) if not specified
- **Protocol**: Use TCP for database connections

- **CRITICAL**: NEVER use action="fix" without explicit user consent
- ALWAYS ask for user permission before using action="fix"

### For CloudWatch Monitoring:
Use **cloudwatch-monitoring** with the `operation` parameter:
- **describe_alarms** - List and describe CloudWatch alarms
- **get_metric_data** - Retrieve metric data (requires metric_name, namespace, dimensions)
- **query_logs** - Search CloudWatch logs (requires log_group_name, filter_pattern)
- **list_log_groups** - List available log groups
- **get_log_events** - Get specific log events (requires log_group_name, log_stream_name)
- **create_alarm** - Create new CloudWatch alarms (requires metric details, threshold, comparison_operator)
- **delete_alarm** - Remove CloudWatch alarms (requires alarm_names)

## PERMISSION VALIDATION WORKFLOW:

Before using **connectivity** with action="fix", ALWAYS:
1. Explain what connectivity issue was found
2. Ask for explicit user consent: "Would you like me to fix this by applying security group rules?"
3. WAIT for clear user approval ("Yes", "Please fix", "Go ahead", etc.)
4. Only THEN call connectivity with action="fix"
5. After applying fix, call connectivity with action="check" again to validate the fix worked

## ERROR HANDLING AND THROTTLING:
**THROTTLING EXCEPTION HANDLING**:
- If you encounter "throttlingException" or "Too many requests", inform the user and suggest waiting
- Do NOT attempt multiple rapid tool calls that could trigger rate limits
- Space out tool calls with appropriate delays when needed
- Provide helpful guidance even when tools are temporarily unavailable

**GRACEFUL ERROR RESPONSES**:
- For throttling: "I'm experiencing rate limiting from AWS services. Please wait a moment before trying again, or I can provide guidance based on memory context."
- For tool failures: "I'm having trouble accessing that tool right now. Let me help you with alternative approaches or provide information from memory."

## CRITICAL RULES:
- **MEMORY FIRST**: Use memory context directly when available - do not use tools for information already in memory
- **THROTTLING AWARENESS**: If tools are rate-limited, provide memory-based guidance and suggest waiting
- ALWAYS use dns-resolve before connectivity analysis when working with DNS names
- NEVER use connectivity with action="fix" without user consent - user consent is MANDATORY
- ALWAYS validate fixes by calling connectivity with action="check" after applying fixes
- Use appropriate CloudWatch operations based on what information is needed
- Extract all required parameters from user messages before making tool calls
- **GRACEFUL DEGRADATION**: When tools fail, fall back to memory context and manual guidance

## LAMBDA FUNCTION STRUCTURE:
- **lambda-dns**: Provides dns-resolve tool
- **lambda-connectivity**: Provides connectivity tool
- **lambda-cloudwatch**: Provides cloudwatch-monitoring tool
"""
        )

        # Get gateway URL
        gateway_url = get_ssm_parameter("/app/troubleshooting/agentcore/gateway_url")
        
        self.tools = [current_time]
        
        # Initialize MCP client if gateway is available
        if gateway_url and bearer_token != "dummy":
            try:
                self.gateway_client = MCPClient(
                    lambda: streamablehttp_client(
                        gateway_url,
                        headers={"Authorization": f"Bearer {bearer_token}"},
                    )
                )
                
                self.gateway_client.start()
                mcp_tools = self.gateway_client.list_tools_sync()
                self.tools.extend(mcp_tools)
                
            except Exception as e:
                print(f"MCP client error: {e}")

        # Initialize agent with memory hook if provided
        if self.memory_hook:
            self.agent = Agent(
                model=self.model,
                system_prompt=self.system_prompt,
                tools=self.tools,
                hooks=[self.memory_hook],
            )
        else:
            self.agent = Agent(
                model=self.model,
                system_prompt=self.system_prompt,
                tools=self.tools,
            )

    async def stream(self, user_query: str):
        import asyncio
        max_retries = 3
        retry_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                async for event in self.agent.stream_async(user_query):
                    if "data" in event:
                        yield event["data"]
                return  # Success, exit retry loop
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Handle throttling exceptions specifically
                if "throttling" in error_str or "too many requests" in error_str:
                    if attempt < max_retries - 1:
                        yield f"⚠️ Rate limiting detected. Waiting {retry_delay} seconds before retry (attempt {attempt + 1}/{max_retries})..."
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 1.5  # Exponential backoff
                        continue
                    else:
                        yield f"❌ I'm experiencing persistent rate limiting from AWS services. Please wait a few minutes before trying again. In the meantime, I can provide guidance based on memory context or manual troubleshooting steps."
                        return
                
                # Handle other exceptions
                elif "validation" in error_str:
                    yield f"❌ Validation Error: {e}. Please check your input parameters."
                    return
                elif "permission" in error_str or "access" in error_str:
                    yield f"❌ Permission Error: {e}. Please verify your AWS credentials and permissions."
                    return
                else:
                    # Generic error handling with retry for transient issues
                    if attempt < max_retries - 1:
                        yield f"⚠️ Temporary error encountered. Retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries})"
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 1.5
                        continue
                    else:
                        yield f"❌ Error after {max_retries} attempts: {e}. I can still help with memory-based guidance or manual troubleshooting steps."
                        return

