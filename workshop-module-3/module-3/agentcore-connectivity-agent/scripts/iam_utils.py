"""
IAM Role Propagation Utilities
Provides retry logic and verification for IAM role propagation delays.
"""

import time
import boto3
from botocore.exceptions import ClientError
from typing import Callable, Any, Optional

# Common IAM-related error indicators
IAM_ERROR_CODES = [
    'AccessDenied',
    'AccessDeniedException',
    'InvalidParameterValue',
    'InvalidParameterValueException',
    'UnauthorizedOperation',
]

IAM_ERROR_MESSAGES = [
    'Role not found',
    'cannot be assumed',
    'The role defined for the function cannot be assumed',
    'is not authorized to perform',
    'User is not authorized',
]


def is_iam_propagation_error(exception: Exception) -> bool:
    """
    Determine if an exception is related to IAM role propagation.
    
    Args:
        exception: The exception to check
        
    Returns:
        bool: True if this appears to be an IAM propagation error
    """
    error_str = str(exception)
    
    # Check if it's a ClientError with IAM error code
    if isinstance(exception, ClientError):
        error_code = exception.response.get('Error', {}).get('Code', '')
        if error_code in IAM_ERROR_CODES:
            return True
    
    # Check for IAM-related error messages
    return any(msg in error_str for msg in IAM_ERROR_MESSAGES)


def wait_for_iam_role_propagation(
    role_arn: str,
    max_wait: int = 300,
    initial_delay: int = 30
) -> bool:
    """
    Smart wait for IAM role to be propagated and usable.
    Polls with incremental backoff instead of blind waiting.
    
    Args:
        role_arn: ARN of the IAM role to verify
        max_wait: Maximum time to wait in seconds (default: 5 minutes)
        initial_delay: Initial retry delay in seconds (default: 30)
    
    Returns:
        bool: True if role is ready, False if timeout
    """
    iam = boto3.client('iam')
    sts = boto3.client('sts')
    
    start_time = time.time()
    delay = initial_delay
    attempt = 1
    
    role_name = role_arn.split('/')[-1] if '/' in role_arn else role_arn
    
    print(f"⏳ Verifying IAM role propagation: {role_name}")
    
    while (time.time() - start_time) < max_wait:
        try:
            # Step 1: Try to get the role
            iam.get_role(RoleName=role_name)
            
            # Step 2: Try to assume the role (best verification)
            try:
                sts.assume_role(
                    RoleArn=role_arn,
                    RoleSessionName='PropagationCheck',
                    DurationSeconds=900
                )
                elapsed = int(time.time() - start_time)
                print(f"✅ IAM role ready after {elapsed} seconds ({attempt} attempts)")
                return True
            except ClientError as e:
                # Role exists but can't be assumed yet
                if 'AccessDenied' in str(e) or 'cannot be assumed' in str(e):
                    pass  # Continue waiting
                else:
                    # Different error, re-raise
                    raise
                    
        except ClientError as e:
            # Role doesn't exist yet
            if e.response['Error']['Code'] != 'NoSuchEntity':
                raise
        
        # Incremental backoff: 30s, 45s, 60s, 60s... (max 60s)
        print(f"  ⏳ Attempt {attempt}: Role not ready, waiting {delay}s...")
        time.sleep(delay)
        delay = min(initial_delay + (attempt * 15), 60)  # 30s, 45s, 60s, 60s...
        attempt += 1
    
    elapsed = int(time.time() - start_time)
    print(f"⚠️  IAM role propagation timeout after {elapsed} seconds")
    return False


def retry_on_iam_error(
    func: Callable,
    max_retries: int = 3,
    initial_delay: int = 30,
    role_arn: Optional[str] = None
) -> Any:
    """
    Execute a function with automatic retry on IAM propagation failures.
    
    Args:
        func: Function to execute
        max_retries: Maximum number of retries (default: 3)
        initial_delay: Initial delay before retry in seconds (default: 30)
        role_arn: Optional IAM role ARN to verify before retry
    
    Returns:
        Result from the function
        
    Raises:
        Exception: If all retries are exhausted or non-IAM error occurs
    """
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🔄 Attempt {attempt}/{max_retries}: Executing operation...")
            result = func()
            print(f"✅ Operation succeeded on attempt {attempt}")
            return result
            
        except Exception as e:
            is_iam_error = is_iam_propagation_error(e)
            
            if is_iam_error and attempt < max_retries:
                # Calculate wait time with incremental backoff: 30s, 45s, 60s
                wait_time = min(initial_delay + ((attempt - 1) * 15), 60)
                
                print(f"⚠️  IAM propagation error detected: {type(e).__name__}")
                print(f"⏳ Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
                
                # Optionally verify role is accessible before retry
                if role_arn:
                    print(f"🔍 Verifying role accessibility...")
                    wait_for_iam_role_propagation(role_arn, max_wait=60)
            else:
                # Not an IAM error or out of retries
                if is_iam_error:
                    print(f"❌ Failed after {max_retries} attempts due to IAM propagation")
                else:
                    print(f"❌ Non-IAM error occurred: {type(e).__name__}")
                raise
    
    raise Exception(f"Failed after {max_retries} attempts")


# Convenience wrapper for common use case
def create_with_iam_retry(
    create_function: Callable,
    resource_name: str,
    role_arn: Optional[str] = None,
    max_retries: int = 3
) -> Any:
    """
    Create AWS resource with automatic retry on IAM propagation failures.
    
    Args:
        create_function: Function that creates the resource
        resource_name: Name of resource being created (for logging)
        role_arn: ARN of IAM role required by the resource
        max_retries: Maximum number of retries (default: 3)
    
    Returns:
        Created resource result
    """
    print(f"🚀 Creating {resource_name} (with IAM retry logic)...")
    return retry_on_iam_error(
        create_function,
        max_retries=max_retries,
        role_arn=role_arn
    )
