"""
AWS AgentCore Runtime Discovery

This module discovers AgentCore runtime ARNs using the AWS CLI bedrock-agentcore-control service.
"""

import json
import logging
import subprocess
import os
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RuntimeInfo:
    """Information about a discovered runtime"""
    runtime_arn: str
    runtime_name: str
    status: str
    created_date: str
    runtime_id: str


class AwsCliRuntimeDiscovery:
    """Discovers AgentCore runtimes using AWS CLI bedrock-agentcore-control"""
    
    def __init__(self, region: str = "us-east-1"):
        self.region = region
        
        # Map runtime names to agent names
        self.runtime_name_mappings = {
            'a2a_performance_agent_runtime': 'PerformanceAgent',
            'a2a_troubleshooting_agent_runtime': 'TroubleshootingAgent', 
            'a2a_collaborator_agent_runtime': 'CollaboratorAgent'
        }
    
    def discover_runtimes(self) -> Dict[str, RuntimeInfo]:
        """
        Discover AgentCore runtimes using AWS CLI
        Returns a dictionary mapping agent names to RuntimeInfo objects
        """
        logger.info("Starting AgentCore runtime discovery using AWS CLI")
        
        discovered_runtimes = {}
        
        try:
            # Use AWS CLI to list agent runtimes
            cmd = [
                'aws', 'bedrock-agentcore-control', 'list-agent-runtimes',
                '--region', self.region,
                '--output', 'json'
            ]
            
            logger.info(f"Running command: {' '.join(cmd)}")
            
            # Execute the CLI command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=os.environ.copy()
            )
            
            if result.returncode != 0:
                logger.error(f"AWS CLI command failed with return code {result.returncode}")
                logger.error(f"stderr: {result.stderr}")
                return self._fallback_discovery()
            
            # Parse the JSON response
            try:
                response = json.loads(result.stdout)
                agent_runtimes = response.get('agentRuntimes', [])
                
                logger.info(f"Found {len(agent_runtimes)} agent runtimes")
                
                for runtime in agent_runtimes:
                    runtime_name = runtime.get('agentRuntimeName', '')
                    runtime_arn = runtime.get('agentRuntimeArn', '')
                    runtime_id = runtime.get('agentRuntimeId', '')
                    status = runtime.get('status', 'UNKNOWN')
                    created_date = runtime.get('lastUpdatedAt', '')
                    
                    # Only process runtimes with a2a_ prefix to avoid picking up other variants
                    if not runtime_name.startswith('a2a_'):
                        logger.debug(f"Skipping runtime without a2a_ prefix: {runtime_name}")
                        continue
                    
                    # Map runtime name to agent name
                    agent_name = self._map_runtime_to_agent_name(runtime_name)
                    
                    if agent_name and runtime_arn:
                        runtime_info = RuntimeInfo(
                            runtime_arn=runtime_arn,
                            runtime_name=runtime_name,
                            runtime_id=runtime_id,
                            status=status,
                            created_date=str(created_date)
                        )
                        
                        discovered_runtimes[agent_name] = runtime_info
                        logger.info(f"Discovered {agent_name}: {runtime_arn}")
                    else:
                        logger.debug(f"Skipping runtime {runtime_name} - no mapping to agent name")
                
                logger.info(f"Successfully discovered {len(discovered_runtimes)} runtimes")
                return discovered_runtimes
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AWS CLI JSON response: {e}")
                logger.error(f"Raw output: {result.stdout}")
                return self._fallback_discovery()
                
        except subprocess.TimeoutExpired:
            logger.error("AWS CLI command timed out")
            return self._fallback_discovery()
        except subprocess.SubprocessError as e:
            logger.error(f"AWS CLI subprocess error: {e}")
            return self._fallback_discovery()
        except Exception as e:
            logger.error(f"Unexpected error during runtime discovery: {e}")
            return self._fallback_discovery()
    
    def _map_runtime_to_agent_name(self, runtime_name: str) -> Optional[str]:
        """Map a runtime name to an agent name"""
        if not runtime_name:
            return None
            
        # Direct mapping
        if runtime_name in self.runtime_name_mappings:
            return self.runtime_name_mappings[runtime_name]
        
        # Fuzzy matching for partial names
        runtime_lower = runtime_name.lower()
        
        if 'performance' in runtime_lower:
            return 'PerformanceAgent'
        elif 'troubleshooting' in runtime_lower or 'connectivity' in runtime_lower:
            return 'TroubleshootingAgent'
        elif 'collaborator' in runtime_lower or 'host' in runtime_lower:
            return 'CollaboratorAgent'
        
        logger.debug(f"No agent mapping found for runtime: {runtime_name}")
        return None
    
    def _fallback_discovery(self) -> Dict[str, RuntimeInfo]:
        """
        Fallback discovery using known ARNs when CLI fails
        This uses the ARNs that were working in the original system
        """
        logger.warning("Using fallback discovery with known runtime ARNs")
        
        # These are the known working ARNs from the CLI output
        known_runtimes = {
            'PerformanceAgent': {
                'runtime_arn': 'arn:aws:bedrock-agentcore:us-east-1:297260274015:runtime/a2a_performance_agent_runtime-GDtAXLFcQj',
                'runtime_name': 'a2a_performance_agent_runtime',
                'runtime_id': 'a2a_performance_agent_runtime-GDtAXLFcQj',
                'status': 'FALLBACK',
                'created_date': ''
            },
            'TroubleshootingAgent': {
                'runtime_arn': 'arn:aws:bedrock-agentcore:us-east-1:297260274015:runtime/a2a_troubleshooting_agent_runtime-GNTw4I8DiI',
                'runtime_name': 'a2a_troubleshooting_agent_runtime',
                'runtime_id': 'a2a_troubleshooting_agent_runtime-GNTw4I8DiI',
                'status': 'FALLBACK',
                'created_date': ''
            }
            # HostAgent is intentionally skipped as per user request
        }
        
        discovered_runtimes = {}
        
        for agent_name, runtime_data in known_runtimes.items():
            runtime_info = RuntimeInfo(
                runtime_arn=runtime_data['runtime_arn'],
                runtime_name=runtime_data['runtime_name'],
                runtime_id=runtime_data['runtime_id'],
                status=runtime_data['status'],
                created_date=runtime_data['created_date']
            )
            
            discovered_runtimes[agent_name] = runtime_info
            logger.info(f"Fallback discovery: {agent_name} -> {runtime_data['runtime_arn']}")
        
        return discovered_runtimes


def discover_agentcore_runtimes(region: str = "us-east-1") -> Dict[str, RuntimeInfo]:
    """
    Main function to discover AgentCore runtimes from AWS account
    
    Args:
        region: AWS region to search in
        
    Returns:
        Dictionary mapping agent names to RuntimeInfo objects
    """
    discovery = AwsCliRuntimeDiscovery(region)
    return discovery.discover_runtimes()
