"""
=============================================================================
TroubleshootingAgent - Network Troubleshooting AI Agent (Module 1)
TroubleshootingAgent - 네트워크 문제 해결 AI 에이전트 (모듈 1)
=============================================================================

Description (설명):
    This module implements the core troubleshooting agent using Strands framework
    and Amazon Bedrock for AI-powered network diagnostics.
    이 모듈은 Strands 프레임워크와 Amazon Bedrock을 사용하여
    AI 기반 네트워크 진단을 수행하는 핵심 문제 해결 에이전트를 구현합니다.

Features (기능):
    - DNS resolution via Route 53 (Route 53을 통한 DNS 해석)
    - Network connectivity analysis (네트워크 연결성 분석)
    - CloudWatch monitoring integration (CloudWatch 모니터링 통합)
    - MCP (Model Context Protocol) tool integration (MCP 도구 통합)

Environment Variables (환경변수):
    BEDROCK_MODEL_ID: Override default Claude model
                      기본 Claude 모델 오버라이드

Author: NetAIOps Team
Module: workshop-module-1
=============================================================================
"""

# =============================================================================
# Imports (임포트)
# =============================================================================
from .memory_hook_provider import MemoryHook          # Memory hook for context persistence (컨텍스트 유지용 메모리 훅)
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
    AI-powered network troubleshooting agent.
    AI 기반 네트워크 문제 해결 에이전트.

    This agent provides DNS resolution, connectivity analysis,
    and CloudWatch monitoring capabilities through MCP tools.
    이 에이전트는 MCP 도구를 통해 DNS 해석, 연결성 분석,
    CloudWatch 모니터링 기능을 제공합니다.
    """

    def __init__(
        self,
        bearer_token: str,
        memory_hook: MemoryHook = None,
        bedrock_model_id: str = None,
        system_prompt: str = None,
    ):
        """
        Initialize the TroubleshootingAgent.
        TroubleshootingAgent 초기화.

        Args (인자):
            bearer_token (str): Authentication token for MCP gateway
                               MCP 게이트웨이 인증 토큰
            memory_hook (MemoryHook, optional): Hook for memory persistence
                                               메모리 유지를 위한 훅
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

        # Store memory hook reference (메모리 훅 참조 저장)
        self.memory_hook = memory_hook
        
        self.system_prompt = (
            system_prompt
            if system_prompt
            else """
You are a Troubleshooting Agent with DNS resolution, connectivity analysis, and CloudWatch monitoring capabilities. You have access to tools from 3 consolidated Lambda functions:

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

## EXAMPLES:

**DNS + Connectivity Analysis:**
User: "Check connectivity between app-frontend.examplecorp.com and app-backend.examplecorp.com on port 80"

1. Call dns-resolve(hostname="app-frontend.examplecorp.com")
2. Call dns-resolve(hostname="app-backend.examplecorp.com") 
3. Call connectivity(source_resource="i-xxx", destination_resource="i-yyy", protocol="TCP", port="80", action="check")
4. IF issues found, ask user permission, then call connectivity(source_resource="i-xxx", destination_resource="i-yyy", protocol="TCP", port="80", action="fix")
5. Call connectivity with action="check" again to validate fix

**Database Connectivity Analysis:**
User: "Check connectivity between reporting.examplecorp.com and database.examplecorp.com"

1. Call dns-resolve(hostname="reporting.examplecorp.com") → Get instance ID (e.g., i-008cea92371b362fa)
2. Call dns-resolve(hostname="database.examplecorp.com") → Get IP address (e.g., 10.2.3.194) - IGNORE any ENI IDs
3. Call connectivity(source_resource="i-008cea92371b362fa", destination_resource="10.2.3.194", protocol="TCP", port="3306", action="check")
4. IF issues found, ask user permission, then call connectivity with same parameters but action="fix"

**Direct Instance Analysis:**
User: "Check connectivity between i-123 and i-456 on port 443"

1. Call connectivity(source_resource="i-123", destination_resource="i-456", protocol="TCP", port="443", action="check")
2. IF issues found, ask user permission, then call connectivity with action="fix" if approved

**CloudWatch Monitoring:**
User: "Show me CPU alarms"
1. Call cloudwatch-monitoring(operation="describe_alarms", query="CPU alarms")

User: "Get CPU metrics for i-123 for the last hour"
1. Call cloudwatch-monitoring(operation="get_metric_data", metric_name="CPUUtilization", namespace="AWS/EC2", dimensions={"InstanceId": "i-123"}, start_time="1h", end_time="now")

## CRITICAL RULES:
- ALWAYS use dns-resolve before connectivity analysis when working with DNS names
- NEVER use connectivity with action="fix" without user consent - user coansent is MANDATORY
- ALWAYS validate fixes by calling connectivity with action="check" after applying fixes
- Use appropriate CloudWatch operations based on what information is needed
- Extract all required parameters from user messages before making tool calls

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
        try:
            async for event in self.agent.stream_async(user_query):
                if "data" in event:
                    yield event["data"]
        except Exception as e:
            yield f"Error: {e}"
