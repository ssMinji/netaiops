"""
Configuration Loader for AgentCore Evaluation Framework

This module handles loading and managing configuration from multiple sources:
1. YAML configuration files
2. Environment variables
3. External agent configuration files (module3-config.json)
4. AWS account discovery
"""

import asyncio
import json
import os
import yaml
import boto3
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for a single agent"""
    name: str
    runtime_arn: str
    agent_type: str
    cognito_config: Dict[str, str]
    alb_dns: str
    log_group: str
    description: Optional[str] = None


class ConfigurationLoader:
    """Loads and manages configuration from multiple sources"""
    
    def __init__(self, config_file_path: str = None):
        self.config_file_path = config_file_path or self._find_config_file()
        self.config = {}
        self.agent_configs = {}
        self._aws_account_id = None
        
    def _find_config_file(self) -> str:
        """Find the configuration file in expected locations"""
        possible_paths = [
            "configs/evaluation_config.yaml",
            "../configs/evaluation_config.yaml",
            "evaluation_config.yaml",
            os.path.join(os.path.dirname(__file__), "../../configs/evaluation_config.yaml")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"Found configuration file at: {path}")
                return path
        
        raise FileNotFoundError("Configuration file 'evaluation_config.yaml' not found in expected locations")
    
    def load_configuration(self) -> Dict[str, Any]:
        """Load complete configuration from all sources"""
        try:
            # Load base configuration from YAML
            self.config = self._load_yaml_config()
            
            # Resolve environment variables
            self.config = self._resolve_environment_variables(self.config)
            
            # Load agent configurations
            self.agent_configs = self._load_agent_configurations()
            
            # Add agent configs to main config
            self.config['agent_configs'] = self.agent_configs
            
            logger.info("Configuration loaded successfully")
            return self.config
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def _load_yaml_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_file_path, 'r') as file:
                config = yaml.safe_load(file)
            logger.info(f"Loaded YAML configuration from {self.config_file_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load YAML configuration: {e}")
            raise
    
    def _resolve_environment_variables(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve environment variable placeholders in configuration"""
        def resolve_value(value):
            if isinstance(value, str):
                # Handle ${VAR} and ${VAR:-default} patterns
                if value.startswith('${') and value.endswith('}'):
                    var_expr = value[2:-1]  # Remove ${ and }
                    
                    if ':-' in var_expr:
                        # Handle default values: ${VAR:-default}
                        var_name, default_value = var_expr.split(':-', 1)
                        return os.getenv(var_name.strip(), default_value.strip())
                    else:
                        # Simple variable: ${VAR}
                        env_value = os.getenv(var_expr.strip())
                        if env_value is None:
                            if var_expr.strip() == 'AWS_ACCOUNT_ID':
                                # Try to get AWS account ID dynamically
                                return self._get_aws_account_id()
                            logger.warning(f"Environment variable {var_expr} not set")
                            return value  # Return original if not found
                        return env_value
                return value
            elif isinstance(value, dict):
                return {k: resolve_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [resolve_value(item) for item in value]
            else:
                return value
        
        return resolve_value(config)
    
    def _get_aws_account_id(self) -> str:
        """Get AWS account ID from STS"""
        if self._aws_account_id is None:
            try:
                sts_client = boto3.client('sts')
                response = sts_client.get_caller_identity()
                self._aws_account_id = response['Account']
                logger.info(f"Discovered AWS account ID: {self._aws_account_id}")
            except Exception as e:
                logger.warning(f"Failed to get AWS account ID: {e}")
                self._aws_account_id = "unknown"
        
        return self._aws_account_id
    
    def _load_agent_configurations(self) -> Dict[str, AgentConfig]:
        """Load agent configurations from AWS account discovery only"""
        logger.info("Discovering agent configurations from AWS account")
        
        try:
            # Handle event loop properly - check if there's already a running loop
            try:
                loop = asyncio.get_running_loop()
                # If we're here, there's already a running loop, so we need to run in a new thread
                import concurrent.futures
                import threading
                
                def run_async_in_thread():
                    # Create new event loop for this thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(self._load_agent_configs_from_aws())
                    finally:
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_async_in_thread)
                    agent_configs = future.result()
                    
            except RuntimeError:
                # No running loop, safe to use asyncio.run()
                agent_configs = asyncio.run(self._load_agent_configs_from_aws())
            
            if agent_configs:
                logger.info(f"Successfully discovered {len(agent_configs)} agents from AWS")
                return agent_configs
            else:
                logger.warning("No agents discovered via API discovery, falling back to known ARNs")
                return self._get_fallback_agent_configs()
        except Exception as e:
            logger.error(f"AWS discovery failed: {e}")
            raise ValueError(f"Failed to discover agent configurations from AWS: {e}")
    
    async def _load_agent_configs_from_aws(self) -> Dict[str, AgentConfig]:
        """Load agent configurations from AWS account discovery"""
        from .aws_runtime_discovery import discover_agentcore_runtimes
        
        try:
            # Use the new synchronous discovery method
            runtime_infos = discover_agentcore_runtimes()
            
            if not runtime_infos:
                logger.warning("No runtime ARNs discovered from AWS account")
                return {}
            
            # Map discovered runtimes to agent configs
            agent_configs = {}
            
            # Map runtime names to agent configurations
            runtime_mapping = {
                'a2a_troubleshooting_agent_runtime': {
                    'agent_name': 'TroubleshootingAgent',
                    'agent_type': 'connectivity',
                    'description': 'Connectivity troubleshooting agent'
                },
                'a2a_performance_agent_runtime': {
                    'agent_name': 'PerformanceAgent',
                    'agent_type': 'performance',
                    'description': 'Network performance analysis agent'
                },
                'a2a_collaborator_agent_runtime': {
                    'agent_name': 'CollaboratorAgent',
                    'agent_type': 'collaborator',
                    'description': 'A2A collaborator agent for routing requests'
                }
            }
            
            # Create AgentConfig objects from discovered runtimes
            for agent_name, runtime_info in runtime_infos.items():
                # Map agent names from discovery to our runtime mapping
                runtime_name_mapping = {
                    'TroubleshootingAgent': 'a2a_troubleshooting_agent_runtime',
                    'PerformanceAgent': 'a2a_performance_agent_runtime', 
                    'CollaboratorAgent': 'a2a_collaborator_agent_runtime'
                }
                
                if agent_name in runtime_name_mapping:
                    runtime_key = runtime_name_mapping[agent_name]
                    
                    if runtime_key in runtime_mapping:
                        mapping = runtime_mapping[runtime_key]
                        
                        # Generate correct log group name from runtime ARN
                        runtime_id = runtime_info.runtime_arn.split('/')[-1]
                        log_group = f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT"
                        
                        # Get client IDs from SSM parameters 
                        # Both performance and troubleshooting agents use the same SSM prefix
                        ssm_client = boto3.client('ssm', region_name='us-east-1')
                        ssm_prefix = '/a2a/app/performance/agentcore'
                        
                        try:
                            # Get client IDs from SSM parameters
                            machine_client_id = ssm_client.get_parameter(
                                Name=f"{ssm_prefix}/machine_client_id",
                                WithDecryption=True
                            )['Parameter']['Value']
                            
                            web_client_id = ssm_client.get_parameter(
                                Name=f"{ssm_prefix}/web_client_id", 
                                WithDecryption=True
                            )['Parameter']['Value']
                            
                        except Exception as e:
                            logger.warning(f"Failed to get client IDs from SSM for {mapping['agent_name']}: {e}")
                            # Fallback to environment variables or default values
                            machine_client_id = os.getenv(f"{mapping['agent_type'].upper()}_MACHINE_CLIENT_ID", '')
                            web_client_id = os.getenv(f"{mapping['agent_type'].upper()}_WEB_CLIENT_ID", '')
                        
                        # Create agent configuration with discovered runtime ARN
                        agent_config = AgentConfig(
                            name=mapping['agent_name'],
                            runtime_arn=runtime_info.runtime_arn,
                            agent_type=mapping['agent_type'],
                            cognito_config={
                                'machine_client_id': machine_client_id,
                                'web_client_id': web_client_id,
                                'ssm_prefix': ssm_prefix,  # Pass SSM prefix for authentication
                                'cognito_provider': os.getenv(f"{mapping['agent_type'].upper()}_COGNITO_PROVIDER", ''),
                                'cognito_auth_scope': os.getenv(f"{mapping['agent_type'].upper()}_AUTH_SCOPE", ''),
                                'cognito_discovery_url': os.getenv(f"{mapping['agent_type'].upper()}_DISCOVERY_URL", '')
                            },
                            alb_dns=os.getenv(f"{mapping['agent_type'].upper()}_ALB_DNS", ''),
                            log_group=log_group,
                            description=mapping['description']
                        )
                        
                        agent_configs[mapping['agent_name']] = agent_config
                        logger.info(f"Configured {mapping['agent_name']} with runtime ARN: {runtime_info.runtime_arn}")
                else:
                    logger.debug(f"Discovered agent '{agent_name}' does not match expected agent types")
            
            # Validate that we found all expected agents
            expected_agents = ['TroubleshootingAgent', 'PerformanceAgent', 'CollaboratorAgent']
            missing_agents = [agent for agent in expected_agents if agent not in agent_configs]
            
            if missing_agents:
                logger.warning(f"Could not discover runtime ARNs for agents: {missing_agents}")
            
            logger.info(f"Successfully configured {len(agent_configs)} agents from AWS discovery")
            return agent_configs
            
        except Exception as e:
            logger.error(f"Failed to discover agent configurations from AWS: {e}")
            raise
    
    def get_agent_config(self, agent_name: str) -> Optional[AgentConfig]:
        """Get configuration for a specific agent"""
        return self.agent_configs.get(agent_name)
    
    def get_all_agent_configs(self) -> Dict[str, AgentConfig]:
        """Get all agent configurations"""
        return self.agent_configs
    
    def get_llm_judge_config(self) -> Dict[str, Any]:
        """Get LLM judge configuration"""
        return self.config.get('llm_judge', {})
    
    def get_cloudwatch_config(self) -> Dict[str, Any]:
        """Get CloudWatch configuration"""
        return self.config.get('cloudwatch', {})
    
    def get_performance_thresholds(self) -> Dict[str, Any]:
        """Get performance threshold configuration"""
        return self.config.get('performance_thresholds', {})
    
    def get_testing_config(self) -> Dict[str, Any]:
        """Get testing configuration"""
        return self.config.get('testing', {})
    
    def get_scoring_config(self) -> Dict[str, Any]:
        """Get scoring configuration"""
        return self.config.get('scoring', {})
    
    def get_output_config(self) -> Dict[str, Any]:
        """Get output configuration"""
        return self.config.get('output', {})
    
    def validate_configuration(self) -> bool:
        """Validate that all required configuration is present"""
        validation_errors = []
        
        # Check that we have at least one agent configured
        if not self.agent_configs:
            validation_errors.append("No agent configurations found")
        
        # Validate each agent config
        for agent_name, agent_config in self.agent_configs.items():
            if not agent_config.runtime_arn:
                validation_errors.append(f"Missing runtime ARN for {agent_name}")
            if not agent_config.cognito_config.get('machine_client_id'):
                validation_errors.append(f"Missing Cognito client ID for {agent_name}")
        
        # Check LLM judge config
        llm_config = self.get_llm_judge_config()
        if not llm_config.get('model_id'):
            validation_errors.append("Missing LLM judge model ID")
        
        if validation_errors:
            logger.error("Configuration validation failed:")
            for error in validation_errors:
                logger.error(f"  - {error}")
            return False
        
        logger.info("Configuration validation passed")
        return True


def load_evaluation_config(config_file_path: str = None) -> Dict[str, Any]:
    """Convenience function to load evaluation configuration"""
    loader = ConfigurationLoader(config_file_path)
    config = loader.load_configuration()
    
    if not loader.validate_configuration():
        raise ValueError("Configuration validation failed")
    
    return config


# Global configuration instance (lazy loaded)
_config_loader = None
_config = None


def get_config() -> Dict[str, Any]:
    """Get global configuration instance"""
    global _config_loader, _config
    
    if _config is None:
        _config_loader = ConfigurationLoader()
        _config = _config_loader.load_configuration()
        
        if not _config_loader.validate_configuration():
            raise ValueError("Configuration validation failed")
    
    return _config


def get_config_loader() -> ConfigurationLoader:
    """Get global configuration loader instance"""
    global _config_loader
    
    if _config_loader is None:
        get_config()  # This will initialize both
    
    return _config_loader
