"""Utility functions for CloudWatch integration."""

from typing import Any, Dict, List


def remove_null_values(d: Dict[str, Any]) -> Dict[str, Any]:
    """Remove None values from a dictionary.
    
    Args:
        d: Dictionary to clean
        
    Returns:
        Dictionary with None values removed
    """
    return {k: v for k, v in d.items() if v is not None}


def filter_by_prefixes(target_set: set, prefix_list: set) -> bool:
    """Check if any of the strings in target_set starts with any prefix in prefix_list.
    
    Args:
        target_set: Set of strings to check
        prefix_list: Set of prefixes to check against
        
    Returns:
        True if any string in target_set starts with any prefix in prefix_list
    """
    if not prefix_list:
        return False
        
    for target in target_set:
        for prefix in prefix_list:
            if target.startswith(prefix):
                return True
                
    return False


def clean_up_pattern(results: List[Dict[str, Any]]) -> None:
    """Clean up pattern results from CloudWatch Logs Insights queries.
    
    Args:
        results: List of pattern results to clean up
    """
    truncation_suffix = "... [truncated]"
    max_message_length = 500 - len(truncation_suffix)  # Reserve space for the suffix
    
    for result in results:
        if '@ptr' in result:
            # Clean up the pattern pointer which isn't useful for LLMs
            del result['@ptr']

        if '@message' in result:
            # Truncate very long patterns to avoid overwhelming the LLM
            message = result['@message']
            if isinstance(message, str) and len(message) > 500:
                result['@message'] = message[:max_message_length] + truncation_suffix
