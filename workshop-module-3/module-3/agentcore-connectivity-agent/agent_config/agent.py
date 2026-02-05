"""
=============================================================================
Connectivity Agent - Network Connectivity Analysis (Module 3 - A2A)
Connectivity Agent - 네트워크 연결성 분석 (모듈 3 - A2A)
=============================================================================

Description (설명):
    Specialized agent for DNS resolution and network connectivity analysis
    within the A2A (Agent-to-Agent) collaboration framework.
    A2A (에이전트 간) 협업 프레임워크 내에서 DNS 해석 및
    네트워크 연결성 분석을 위한 전문 에이전트입니다.

Capabilities (기능):
    - DNS resolution via Route 53 (Route 53을 통한 DNS 해석)
    - Network path analysis (네트워크 경로 분석)
    - Security group rule analysis and fixes (보안 그룹 규칙 분석 및 수정)
    - Connectivity check and fix actions (연결성 확인 및 수정 작업)

A2A Integration (A2A 통합):
    This agent can be invoked by the Host/Collaborator agent for
    connectivity-specific tasks in multi-agent workflows.
    이 에이전트는 다중 에이전트 워크플로우에서 연결성 관련 작업을 위해
    Host/Collaborator 에이전트에 의해 호출될 수 있습니다.

Environment Variables (환경변수):
    BEDROCK_MODEL_ID: Override default Claude model
                      기본 Claude 모델 오버라이드

Author: NetAIOps Team
Module: workshop-module-3 (agentcore-connectivity-agent)
=============================================================================
"""

# =============================================================================
# Imports (임포트)
# =============================================================================
from .memory_hook_provider import MemoryHook          # Memory hook (메모리 훅)
from .utils import get_ssm_parameter                  # SSM parameter retrieval (SSM 파라미터 조회)
from mcp.client.streamable_http import streamablehttp_client  # MCP HTTP client
from strands import Agent                             # Strands AI Agent framework
from strands_tools import current_time                # Time utility tool (시간 유틸리티)
from strands.models import BedrockModel               # Bedrock model wrapper
from strands.tools.mcp import MCPClient               # MCP client for tools
import logging
import os

# Configure module logger (모듈 로거 설정)
logger = logging.getLogger(__name__)

# =============================================================================
# Default Configuration (기본 설정)
# =============================================================================
# Default model ID - Supports env var override for flexibility
# 기본 모델 ID - 유연성을 위해 환경변수 오버라이드 지원
DEFAULT_MODEL_ID = "global.anthropic.claude-opus-4-5-20251101-v1:0"


class TroubleshootingAgent:
    """
    Connectivity-focused troubleshooting agent for A2A collaboration.
    A2A 협업을 위한 연결성 중심 문제 해결 에이전트.

    Handles DNS resolution and network connectivity analysis tasks
    as part of multi-agent troubleshooting workflows.
    다중 에이전트 문제 해결 워크플로우의 일부로
    DNS 해석 및 네트워크 연결성 분석 작업을 처리합니다.
    """

    def __init__(
        self,
        bearer_token: str,
        memory_hook: MemoryHook = None,
        bedrock_model_id: str = None,
        system_prompt: str = None,
    ):
        """
        Initialize the Connectivity Agent.
        Connectivity Agent 초기화.

        Args (인자):
            bearer_token (str): Auth token for MCP gateway (MCP 게이트웨이 인증 토큰)
            memory_hook (MemoryHook): Optional memory persistence (선택적 메모리 유지)
            bedrock_model_id (str): Override model ID (모델 ID 오버라이드)
            system_prompt (str): Custom system prompt (사용자 정의 시스템 프롬프트)
        """
        # Model ID priority: env var > parameter > default
        # 모델 ID 우선순위: 환경변수 > 파라미터 > 기본값
        if bedrock_model_id is None:
            bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', DEFAULT_MODEL_ID)

        self.model_id = bedrock_model_id
        self.model = BedrockModel(model_id=self.model_id)
        self.memory_hook = memory_hook
        
        self.system_prompt = (
            system_prompt
            if system_prompt
            else """
You are a Troubleshooting Agent with DNS resolution and connectivity analysis capabilities. You have access to tools from 2 consolidated Lambda functions:

CORE TOOLS ALWAYS AVAILABLE:
- current_time: Gets the current time in ISO 8601 format for a specified timezone

## ADVANCED CONNECTIVITY TOOLS (via AgentCore Gateway):

- **dns-resolve** - Resolves DNS hostnames from Route 53 Private Hosted Zones to EC2 instances or ENIs

- **connectivity** - Analyzes network paths and can fix connectivity issues by applying security group rules (fix action REQUIRES user consent)

## SPECIFIC WORKFLOW FOR CONNECTIVITY REQUESTS:

### Scenario 1: User asks "Can you check connectivity between reporting.examplecorp.com and database.examplecorp.com?"
**IMMEDIATE ACTION**: Call the connectivity tool to check connectivity by creating VPC reachability analyzer path
1. Call dns-resolve(hostname="reporting.examplecorp.com") → Get instance ID
2. Call dns-resolve(hostname="database.examplecorp.com") → Get IP address (IGNORE ENI IDs for database)
3. Call connectivity(source_resource="instance_id", destination_resource="ip_address", protocol="TCP", port="3306", action="check")
4. Report the connectivity analysis results to the user

### Scenario 2: User asks "Can you fix connectivity between reporting.examplecorp.com and database.examplecorp.com?"
**MANDATORY CONSENT REQUIREMENT**: NEVER call any tools immediately. ALWAYS ask for explicit user consent first.
- **CRITICAL**: Do NOT call dns-resolve or connectivity tools yet
- **CRITICAL**: Do NOT attempt to fix anything without explicit user consent
- **REQUIRED RESPONSE**: "I can help fix the connectivity issue between reporting.examplecorp.com and database.examplecorp.com by applying the necessary security group rules to allow the required traffic. However, this will modify your AWS security groups. 

Please confirm if you want to proceed with these security group changes."
- **MANDATORY**: WAIT for explicit user confirmation before proceeding with any tool calls

### Scenario 3: User confirms the fix (with any affirmative response)
**IMMEDIATE ACTION**: Call the connectivity tool to fix the issue
1. Call dns-resolve(hostname="reporting.examplecorp.com") → Get instance ID
2. Call dns-resolve(hostname="database.examplecorp.com") → Get IP address (IGNORE ENI IDs for database)
3. Call connectivity(source_resource="instance_id", destination_resource="ip_address", protocol="TCP", port="3306", action="fix")
4. After applying fix, call connectivity with action="check" again to validate the fix worked
5. Report the fix results to the user

## GENERAL WORKFLOW:

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

## PERMISSION VALIDATION WORKFLOW:

Before using **connectivity** with action="fix", ALWAYS:
1. Explain what connectivity issue was found (if checking first) OR ask for permission to fix (if user directly requests fix)
2. Ask for explicit user consent: "Would you like me to fix this by applying security group rules?" OR "Do you want me to proceed with the fix?"
3. WAIT for clear user approval
4. Only THEN call connectivity with action="fix"
5. After applying fix, call connectivity with action="check" again to validate the fix worked

## EXAMPLES:

**Specific Example - Check Request:**
User: "Can you check connectivity between reporting.examplecorp.com and database.examplecorp.com?"
→ IMMEDIATELY call dns-resolve and connectivity tools with action="check"

**Specific Example - Fix Request:**
User: "Can you fix connectivity between reporting.examplecorp.com and database.examplecorp.com?"
→ IMMEDIATELY ask for consent: "I can fix the connectivity issue... Do you want me to proceed?"

**Specific Example - User Confirmation:**
User provides affirmative response
→ IMMEDIATELY call dns-resolve and connectivity tools with action="fix"

**General DNS + Connectivity Analysis:**
User: "Check connectivity between app-frontend.examplecorp.com and app-backend.examplecorp.com on port 80"

1. Call dns-resolve(hostname="app-frontend.examplecorp.com")
2. Call dns-resolve(hostname="app-backend.examplecorp.com") 
3. Call connectivity(source_resource="i-xxx", destination_resource="i-yyy", protocol="TCP", port="80", action="check")
4. IF issues found, ask user permission, then call connectivity(source_resource="i-xxx", destination_resource="i-yyy", protocol="TCP", port="80", action="fix")
5. Call connectivity with action="check" again to validate fix

## CRITICAL RULES - CONSENT IS MANDATORY:
- ALWAYS use dns-resolve before connectivity analysis when working with DNS names
- **ABSOLUTE RULE**: NEVER EVER use connectivity with action="fix" without explicit user consent - user consent is MANDATORY
- **ABSOLUTE RULE**: When user asks to "fix" anything, NEVER call any tools immediately - ALWAYS ask for consent first
- **ABSOLUTE RULE**: Only proceed with fixes after receiving explicit confirmation from the user
- ALWAYS validate fixes by calling connectivity with action="check" after applying fixes
- Extract all required parameters from user messages before making tool calls
- For "check connectivity" requests: IMMEDIATELY perform the check
- For "fix connectivity" requests: IMMEDIATELY ask for consent - DO NOT CALL ANY TOOLS
- For user confirmations: IMMEDIATELY execute the fix

## CONSENT VALIDATION CHECKLIST:
Before ANY action="fix" operation, verify:
1. ✓ User has explicitly requested a fix (not just a check)
2. ✓ You have asked for explicit consent with the exact phrase about security group modifications
3. ✓ User has responded with clear confirmation
4. ✓ Only THEN proceed with dns-resolve and connectivity tools with action="fix"

**VIOLATION OF CONSENT RULES IS STRICTLY FORBIDDEN**

## LAMBDA FUNCTION STRUCTURE:
- **lambda-dns**: Provides dns-resolve tool
- **lambda-fix**: Provides connectivity tool
"""
        )

        # Get gateway URL
        gateway_url = get_ssm_parameter("/a2a/app/troubleshooting/agentcore/gateway_url")
        
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
        try:
            async for event in self.agent.stream_async(user_query):
                if "data" in event:
                    yield event["data"]
        except Exception as e:
            yield f"Error: {e}"
