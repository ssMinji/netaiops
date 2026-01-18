import os
import boto3
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_aws_region() -> str:
    """Get the current AWS region."""
    # Try to get from environment first
    region = os.environ.get('AWS_DEFAULT_REGION')
    if region:
        return region
    
    # Try to get from boto3 session
    try:
        session = boto3.Session()
        return session.region_name or 'us-east-1'
    except Exception:
        return 'us-east-1'


def get_ssm_parameter(parameter_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get parameter from AWS Systems Manager Parameter Store
    
    Args:
        parameter_name: The name of the parameter to retrieve
        default: Default value if parameter not found
        
    Returns:
        Parameter value or default if not found
    """
    try:
        ssm = boto3.client('ssm', region_name=get_aws_region())
        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        return response['Parameter']['Value']
    except Exception as e:
        logger.warning(f"Could not retrieve SSM parameter {parameter_name}: {e}")
        if default is not None:
            logger.info(f"Using default value for {parameter_name}: {default}")
            return default
        return None


def put_ssm_parameter(name: str, value: str, description: str = None, overwrite: bool = True) -> bool:
    """
    Put a parameter in AWS Systems Manager Parameter Store
    
    Args:
        name: The name of the parameter
        value: The value of the parameter
        description: Optional description for the parameter
        overwrite: Whether to overwrite existing parameter
        
    Returns:
        True if parameter was created/updated successfully
    """
    try:
        ssm = boto3.client('ssm', region_name=get_aws_region())
        ssm.put_parameter(
            Name=name,
            Value=value,
            Type='String',
            Overwrite=overwrite,
            Description=description or f'AgentCore parameter: {name}'
        )
        logger.info(f"Successfully put SSM parameter: {name}")
        return True
    except Exception as e:
        logger.error(f"Failed to put SSM parameter {name}: {e}")
        return False


def load_api_spec(file_path: str) -> list:
    """Load API specification from JSON file.
    
    Args:
        file_path: Path to the JSON API specification file
        
    Returns:
        List of API tool definitions
        
    Raises:
        ValueError: If the file doesn't contain a list
    """
    import json
    with open(file_path, 'r') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Expected a list in the JSON file")
    return data


def read_config(config_file: str) -> Dict[str, Any]:
    """
    Read configuration from YAML file
    
    Args:
        config_file: Path to the YAML configuration file
        
    Returns:
        Configuration dictionary
    """
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return yaml.safe_load(f) or {}
        else:
            logger.warning(f"Configuration file {config_file} not found")
            return {}
    except Exception as e:
        logger.error(f"Error reading configuration file {config_file}: {e}")
        return {}


def get_account_id() -> str:
    """Get the current AWS account ID."""
    try:
        sts = boto3.client('sts', region_name=get_aws_region())
        response = sts.get_caller_identity()
        return response['Account']
    except Exception as e:
        logger.error(f"Error getting account ID: {e}")
        raise


def create_ssm_parameters(parameters: Dict[str, str], overwrite: bool = True) -> bool:
    """
    Create multiple SSM parameters at once
    
    Args:
        parameters: Dictionary of parameter names to values
        overwrite: Whether to overwrite existing parameters
        
    Returns:
        True if all parameters were created successfully
    """
    try:
        ssm = boto3.client('ssm', region_name=get_aws_region())
        success = True
        
        for name, value in parameters.items():
            try:
                ssm.put_parameter(
                    Name=name,
                    Value=value,
                    Type='String',
                    Overwrite=overwrite,
                    Description=f'NetOps AgentCore parameter: {name}'
                )
                logger.info(f"Created SSM parameter: {name}")
            except Exception as e:
                logger.error(f"Failed to create SSM parameter {name}: {e}")
                success = False
        
        return success
    except Exception as e:
        logger.error(f"Error creating SSM parameters: {e}")
        return False


def delete_ssm_parameters(parameter_names: list) -> bool:
    """
    Delete multiple SSM parameters
    
    Args:
        parameter_names: List of parameter names to delete
        
    Returns:
        True if all parameters were deleted successfully
    """
    try:
        ssm = boto3.client('ssm', region_name=get_aws_region())
        success = True
        
        for name in parameter_names:
            try:
                ssm.delete_parameter(Name=name)
                logger.info(f"Deleted SSM parameter: {name}")
            except ssm.exceptions.ParameterNotFound:
                logger.warning(f"SSM parameter {name} not found")
            except Exception as e:
                logger.error(f"Failed to delete SSM parameter {name}: {e}")
                success = False
        
        return success
    except Exception as e:
        logger.error(f"Error deleting SSM parameters: {e}")
        return False
