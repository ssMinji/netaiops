#!/bin/bash

# IAM Utilities for Bash - Exponential Backoff and Retry Logic
# Mirrors the functionality of iam_utils.py for bash scripts

# Configuration
INITIAL_DELAY=30
MAX_RETRIES=3
BACKOFF_MULTIPLIER=1.5

# Check if an error is IAM-related
is_iam_propagation_error() {
    local error_message="$1"
    
    # Common IAM propagation error patterns
    if echo "$error_message" | grep -qiE "(InvalidParameterValueException|role.*cannot be assumed|role.*does not exist|access denied|not authorized|entity already exists|role.*not found|assume.*role)"; then
        return 0  # true - is IAM error
    fi
    
    return 1  # false - not IAM error
}

# Wait for IAM role propagation with exponential backoff
# Usage: wait_for_iam_role_propagation <role_arn> [initial_delay]
wait_for_iam_role_propagation() {
    local role_arn="$1"
    local initial_delay="${2:-$INITIAL_DELAY}"
    
    echo "⏳ Waiting ${initial_delay} seconds for IAM role propagation..."
    echo "   Role ARN: $role_arn"
    sleep "$initial_delay"
    
    # Optionally verify role exists
    local role_name=$(echo "$role_arn" | awk -F'/' '{print $NF}')
    if [ -n "$role_name" ]; then
        echo "✅ IAM role propagation wait completed"
    fi
}

# Retry a command with exponential backoff on IAM errors
# Usage: retry_with_backoff <max_retries> <command> [args...]
retry_with_backoff() {
    local max_retries="$1"
    shift
    local command=("$@")
    
    local attempt=1
    local delay=$INITIAL_DELAY
    
    while [ $attempt -le $max_retries ]; do
        echo "🔄 Attempt $attempt of $max_retries: ${command[*]}"
        
        # Execute command and capture output and exit code
        local output
        local exit_code
        output=$("${command[@]}" 2>&1)
        exit_code=$?
        
        # Success
        if [ $exit_code -eq 0 ]; then
            echo "✅ Command succeeded on attempt $attempt"
            echo "$output"
            return 0
        fi
        
        # Check if it's an IAM propagation error
        if is_iam_propagation_error "$output"; then
            echo "⚠️  IAM propagation error detected"
            echo "   Error: $output"
            
            if [ $attempt -lt $max_retries ]; then
                echo "⏳ Waiting ${delay} seconds before retry..."
                sleep "$delay"
                
                # Calculate next delay (exponential backoff) - using bash arithmetic
                delay=$(awk "BEGIN {printf \"%.0f\", $delay * $BACKOFF_MULTIPLIER}")
                attempt=$((attempt + 1))
            else
                echo "❌ Max retries ($max_retries) reached"
                echo "   Last error: $output"
                return $exit_code
            fi
        else
            # Not an IAM error, fail immediately
            echo "❌ Command failed with non-IAM error"
            echo "   Error: $output"
            return $exit_code
        fi
    done
    
    return 1
}

# Create resource with automatic IAM retry
# Usage: create_with_iam_retry <resource_name> <role_arn> <command> [args...]
create_with_iam_retry() {
    local resource_name="$1"
    local role_arn="$2"
    shift 2
    local command=("$@")
    
    echo "🚀 Creating $resource_name with IAM retry logic..."
    echo "   Role ARN: $role_arn"
    
    # Initial wait for IAM propagation
    wait_for_iam_role_propagation "$role_arn" "$INITIAL_DELAY"
    
    # Try to create resource with retries
    retry_with_backoff "$MAX_RETRIES" "${command[@]}"
    local result=$?
    
    if [ $result -eq 0 ]; then
        echo "✅ Successfully created $resource_name"
    else
        echo "❌ Failed to create $resource_name after retries"
    fi
    
    return $result
}

# Export functions for use in other scripts
export -f is_iam_propagation_error
export -f wait_for_iam_role_propagation
export -f retry_with_backoff
export -f create_with_iam_retry
