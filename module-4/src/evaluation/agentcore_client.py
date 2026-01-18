"""
AgentCore Client for invoking deployed AgentCore runtime instances

This module provides a client to interact with deployed AgentCore agents via direct HTTP requests
following the same pattern as the working test files.
"""

import boto3
import json
import logging
import requests
import urllib.parse
import uuid
import time
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AgentRuntimeLogger:
    """Enhanced logger for AgentCore runtime calls with beautiful formatting"""
    
    # ANSI color codes for beautiful output
    COLORS = {
        'BLUE': '\033[94m',
        'GREEN': '\033[92m', 
        'YELLOW': '\033[93m',
        'RED': '\033[91m',
        'MAGENTA': '\033[95m',
        'CYAN': '\033[96m',
        'WHITE': '\033[97m',
        'BOLD': '\033[1m',
        'DIM': '\033[2m',
        'RESET': '\033[0m'
    }
    
    @classmethod
    def colorize(cls, text, color):
        """Apply color to text"""
        return f"{cls.COLORS.get(color, '')}{text}{cls.COLORS['RESET']}"
    
    @classmethod
    def log_runtime_call_start(cls, runtime_arn: str, message: str, session_id: str):
        """Log the start of a runtime call with beautiful formatting"""
        runtime_name = runtime_arn.split('/')[-1] if '/' in runtime_arn else runtime_arn
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n{cls.colorize('[' + timestamp + ']', 'DIM')} {cls.colorize('AgentCore Runtime Call', 'BOLD')}")
        print(f"   {cls.colorize('Runtime:', 'CYAN')} {cls.colorize(runtime_name, 'WHITE')}")
        print(f"   {cls.colorize('Session:', 'CYAN')} {cls.colorize(session_id[:8] + '...', 'DIM')}")
        
        # Show message preview (first 80 characters)
        message_preview = message[:80] + "..." if len(message) > 80 else message
        formatted_message = f'"{message_preview}"'
        print(f"   {cls.colorize('Message:', 'CYAN')} {cls.colorize(formatted_message, 'YELLOW')}")
        
        print(f"   {cls.colorize('Status:', 'CYAN')} {cls.colorize('Sending request...', 'YELLOW')}")
    
    @classmethod
    def log_runtime_call_progress(cls, elapsed_time: float, status: str):
        """Log progress updates during runtime call"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"   {cls.colorize('Progress:', 'CYAN')} {cls.colorize(f'{elapsed_time:.1f}s', 'WHITE')} - {cls.colorize(status, 'BLUE')}")
    
    @classmethod
    def log_runtime_call_success(cls, response_time: float, response_length: int, response_preview: str = ""):
        """Log successful runtime call completion"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Color code response time based on speed
        if response_time < 5.0:
            time_color = 'GREEN'
            speed_indicator = '[FAST]'
        elif response_time < 15.0:
            time_color = 'YELLOW'
            speed_indicator = '[NORMAL]'
        else:
            time_color = 'RED'
            speed_indicator = '[SLOW]'
        
        print(f"   {cls.colorize('Status:', 'CYAN')} {cls.colorize('Response received!', 'GREEN')}")
        print(f"   {cls.colorize(f'{speed_indicator} Response Time:', 'CYAN')} {cls.colorize(f'{response_time:.2f}s', time_color)}")
        print(f"   {cls.colorize('Response Size:', 'CYAN')} {cls.colorize(f'{response_length} characters', 'WHITE')}")
        
        if response_preview:
            preview = response_preview[:100] + "..." if len(response_preview) > 100 else response_preview
            formatted_preview = f'"{preview}"'
            print(f"   {cls.colorize('Preview:', 'CYAN')} {cls.colorize(formatted_preview, 'DIM')}")
        
        print(f"{cls.colorize('─' * 80, 'DIM')}")
    
    @classmethod
    def log_runtime_call_error(cls, error: str, elapsed_time: float):
        """Log runtime call failure"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        print(f"   {cls.colorize('Status:', 'CYAN')} {cls.colorize('Request failed!', 'RED')}")
        print(f"   {cls.colorize('Elapsed Time:', 'CYAN')} {cls.colorize(f'{elapsed_time:.2f}s', 'WHITE')}")
        print(f"   {cls.colorize('Error:', 'CYAN')} {cls.colorize(error, 'RED')}")
        print(f"{cls.colorize('─' * 80, 'DIM')}")
    
    @classmethod
    def log_auth_progress(cls, step: str):
        """Log authentication progress"""
        print(f"   {cls.colorize('Auth:', 'CYAN')} {cls.colorize(step, 'BLUE')}")


class AgentCoreClient:
    """Client for invoking AgentCore runtime instances using HTTP requests"""
    
    def __init__(self, cognito_config: Dict[str, str], region_name: str = 'us-east-1'):
        self.region_name = region_name
        self.cognito_config = cognito_config
        self.access_token = None
        
    async def invoke_agent(self, runtime_arn: str, message: str, session_id: Optional[str] = None) -> str:
        """
        Invoke an AgentCore agent with the given message using HTTP requests
        
        Args:
            runtime_arn: The ARN of the AgentCore runtime to invoke
            message: The message/query to send to the agent
            session_id: Optional session ID for conversation tracking
            
        Returns:
            String response from the agent
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        start_time = time.time()
        
        # Beautiful logging - Start of runtime call
        AgentRuntimeLogger.log_runtime_call_start(runtime_arn, message, session_id)
            
        try:
            logger.info(f"Invoking AgentCore runtime: {runtime_arn}")
            logger.debug(f"Session ID: {session_id}")
            
            # Get access token for authentication
            AgentRuntimeLogger.log_auth_progress("Getting access token...")
            access_token = await self._get_access_token()
            if not access_token:
                raise Exception("Failed to obtain access token")
            
            AgentRuntimeLogger.log_auth_progress("Access token obtained successfully")
            
            # Prepare request following the working test pattern
            escaped_arn = urllib.parse.quote(runtime_arn, safe="")
            url = f"https://bedrock-agentcore.{self.region_name}.amazonaws.com/runtimes/{escaped_arn}/invocations"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json", 
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
            }
            
            # Use the exact payload format from working tests
            payload = {
                "prompt": message,
                "actor_id": "DEFAULT"
            }
            
            request_start_time = time.time()
            elapsed_prep = request_start_time - start_time
            AgentRuntimeLogger.log_runtime_call_progress(elapsed_prep, "Request prepared, sending to AgentCore...")
            
            # Make the HTTP request with streaming response
            response = requests.post(
                url,
                params={"qualifier": "DEFAULT"},
                headers=headers,
                json=payload,
                timeout=300,
                stream=True,
            )
            
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"Agent invocation failed: {error_msg}")
                elapsed_error = time.time() - start_time
                AgentRuntimeLogger.log_runtime_call_error(error_msg, elapsed_error)
                raise Exception(error_msg)
            
            # Log successful connection
            elapsed_connect = time.time() - start_time
            AgentRuntimeLogger.log_runtime_call_progress(elapsed_connect, "Connected! Processing streaming response...")
            
            # Process streaming response (similar to test files)
            response_text = ""
            chunk_count = 0
            last_progress_time = time.time()
            
            for line in response.iter_lines(chunk_size=8192, decode_unicode=True):
                if line:
                    if line.startswith("data: "):
                        content = line[6:].strip('"')
                        content = content.replace('\\n', '\n')
                        content = content.replace('\\"', '"')
                        content = content.replace('\\\\', '\\')
                        response_text += content
                        chunk_count += 1
                        
                        # Show progress every 5 seconds during streaming
                        current_time = time.time()
                        if current_time - last_progress_time >= 5.0:
                            elapsed_stream = current_time - start_time
                            AgentRuntimeLogger.log_runtime_call_progress(
                                elapsed_stream, 
                                f"Streaming response... ({len(response_text)} chars received)"
                            )
                            last_progress_time = current_time
                            
                    elif line.strip() in ["data: [DONE]", "[DONE]"]:
                        break
            
            end_time = time.time()
            response_time = end_time - start_time
            
            # Beautiful logging - Success
            AgentRuntimeLogger.log_runtime_call_success(
                response_time, 
                len(response_text), 
                response_text.strip()
            )
            
            logger.info(f"Agent response received in {response_time:.2f}s")
            if response_text:
                logger.info(f"Response preview: {response_text[:150]}{'...' if len(response_text) > 150 else ''}")
            
            return response_text
            
        except Exception as e:
            elapsed_error = time.time() - start_time
            AgentRuntimeLogger.log_runtime_call_error(str(e), elapsed_error)
            logger.error(f"Failed to invoke AgentCore runtime {runtime_arn}: {e}")
            raise Exception(f"Agent invocation failed: {str(e)}")
    
    async def _get_access_token(self) -> Optional[str]:
        """Get machine-to-machine access token using client credentials flow"""
        try:
            if self.access_token:
                return self.access_token
            
            # Get credentials from cognito config (which now includes client_id)
            client_id = self.cognito_config.get('machine_client_id')
            if not client_id:
                logger.error("Missing machine_client_id in cognito config")
                return None
            
            # Get SSM prefix from cognito config (defaults to performance if not specified)
            ssm_prefix = self.cognito_config.get('ssm_prefix', '/a2a/app/performance/agentcore')
            
            # Try to get client_secret from SSM (following the test file pattern)
            try:
                ssm_client = boto3.client('ssm', region_name=self.region_name)
                client_secret = ssm_client.get_parameter(
                    Name=f"{ssm_prefix}/machine_client_secret",
                    WithDecryption=True
                )['Parameter']['Value']
                
                token_url = ssm_client.get_parameter(
                    Name=f"{ssm_prefix}/cognito_token_url",
                    WithDecryption=True
                )['Parameter']['Value']
                
                auth_scope = ssm_client.get_parameter(
                    Name=f"{ssm_prefix}/cognito_auth_scope",
                    WithDecryption=True
                )['Parameter']['Value']
                
            except Exception as e:
                logger.error(f"Failed to get additional parameters from SSM using prefix {ssm_prefix}: {e}")
                return None
            
            logger.debug(f"Using client ID: {client_id}")
            logger.debug(f"Token URL: {token_url}")
            logger.debug(f"Scope: {auth_scope}")
            
            # Request token using client_credentials flow
            response = requests.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": auth_scope
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                logger.debug("Successfully obtained M2M access token")
                return self.access_token
            else:
                logger.error(f"Failed to get M2M token: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting M2M token: {e}")
            return None
    
    async def get_agent_info(self, runtime_arn: str) -> Dict[str, Any]:
        """
        Get information about an AgentCore runtime
        
        Args:
            runtime_arn: The ARN of the AgentCore runtime
            
        Returns:
            Dictionary containing runtime information
        """
        try:
            # Extract runtime ID from ARN
            runtime_id = runtime_arn.split('/')[-1]
            
            response = self.bedrock_agentcore_client.get_runtime(
                runtimeId=runtime_id
            )
            
            return {
                'runtime_arn': runtime_arn,
                'runtime_id': runtime_id,
                'status': response.get('status', 'unknown'),
                'creation_time': response.get('creationTime', ''),
                'last_modified_time': response.get('lastModifiedTime', ''),
                'description': response.get('description', ''),
                'success': True
            }
            
        except Exception as e:
            logger.warning(f"Could not get runtime info for {runtime_arn}: {e}")
            return {
                'runtime_arn': runtime_arn,
                'error': str(e),
                'success': False
            }
    
    async def test_connectivity(self, runtime_arn: str) -> Dict[str, Any]:
        """
        Test connectivity to an AgentCore runtime with a simple query
        
        Args:
            runtime_arn: The ARN of the AgentCore runtime to test
            
        Returns:
            Dictionary containing connectivity test results
        """
        test_message = "Hello, this is a connectivity test. Please respond to confirm you are working."
        
        try:
            result = await self.invoke_agent(runtime_arn, test_message, f"test-{uuid.uuid4().hex[:8]}")
            
            # Check if response indicates the agent is working
            response_text = result.get('response_text', '').lower()
            is_responsive = (
                result.get('success', False) and 
                len(response_text) > 0 and
                'error' not in response_text
            )
            
            return {
                'runtime_arn': runtime_arn,
                'connectivity_test_passed': is_responsive,
                'response_time': result.get('response_time', 0),
                'test_message': test_message,
                'agent_response': result.get('response_text', ''),
                'success': result.get('success', False)
            }
            
        except Exception as e:
            logger.error(f"Connectivity test failed for {runtime_arn}: {e}")
            return {
                'runtime_arn': runtime_arn,
                'connectivity_test_passed': False,
                'error': str(e),
                'success': False
            }


class CognitoAuthenticator:
    """Handle Cognito authentication for AgentCore agents"""
    
    def __init__(self, region_name: str = 'us-east-1'):
        self.region_name = region_name
        self.cognito_client = boto3.client('cognito-idp', region_name=region_name)
        
    async def get_machine_to_machine_token(self, cognito_config: Dict[str, str]) -> Optional[str]:
        """
        Get a machine-to-machine token for AgentCore authentication
        
        Args:
            cognito_config: Dictionary containing Cognito configuration
            
        Returns:
            Access token string if successful, None otherwise
        """
        try:
            client_id = cognito_config.get('machine_client_id')
            auth_scope = cognito_config.get('cognito_auth_scope')
            
            if not client_id or not auth_scope:
                logger.warning("Missing Cognito client ID or auth scope")
                return None
            
            # Use client credentials flow for machine-to-machine authentication
            response = self.cognito_client.initiate_auth(
                ClientId=client_id,
                AuthFlow='CLIENT_CREDENTIALS',
                AuthParameters={
                    'SCOPE': auth_scope
                }
            )
            
            access_token = response['AuthenticationResult']['AccessToken']
            logger.info("Successfully obtained Cognito access token")
            return access_token
            
        except Exception as e:
            logger.error(f"Failed to get Cognito token: {e}")
            return None


# Utility functions for working with AgentCore runtimes
def extract_runtime_id_from_arn(runtime_arn: str) -> str:
    """Extract the runtime ID from a runtime ARN"""
    return runtime_arn.split('/')[-1]


def extract_account_id_from_arn(runtime_arn: str) -> str:
    """Extract the account ID from a runtime ARN"""
    return runtime_arn.split(':')[4]


def extract_region_from_arn(runtime_arn: str) -> str:
    """Extract the region from a runtime ARN"""
    return runtime_arn.split(':')[3]


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_client():
        """Test the AgentCore client with example runtime ARNs"""
        
        client = AgentCoreClient()
        
        # Test runtime ARNs from the configuration
        test_runtimes = [
            "arn:aws:bedrock-agentcore:us-east-1:237616366264:runtime/a2a_troubleshooting_agent_runtime-31xtNG6I7x",
            "arn:aws:bedrock-agentcore:us-east-1:104398007905:runtime/a2a_performance_agent_runtime-lIbJHD3rD6"
        ]
        
        for runtime_arn in test_runtimes:
            print(f"\nTesting runtime: {runtime_arn}")
            
            # Test connectivity
            connectivity_result = await client.test_connectivity(runtime_arn)
            print(f"Connectivity test: {'PASS' if connectivity_result.get('connectivity_test_passed') else 'FAIL'}")
            
            if connectivity_result.get('success'):
                # Test a real query
                query_result = await client.invoke_agent(
                    runtime_arn, 
                    "Can you check connectivity between reporting.acme.com and database.acme.com?"
                )
                print(f"Query response time: {query_result.get('response_time', 0):.2f}s")
                print(f"Response preview: {query_result.get('response_text', '')[:100]}...")
    
    # Run the test
    asyncio.run(test_client())
