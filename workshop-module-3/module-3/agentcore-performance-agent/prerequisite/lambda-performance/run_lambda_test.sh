#!/bin/bash

# Test script runner for Lambda function testing
# This script sets up the environment and runs the Lambda test

set -e

echo "🧪 Lambda Function Test Runner"
echo "================================"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS CLI is not configured or credentials are invalid"
    echo "Please run 'aws configure' to set up your credentials"
    exit 1
fi

# Get current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_SCRIPT="$SCRIPT_DIR/test_lambda_analyze_network_flow_monitor.py"

echo "📍 Script directory: $SCRIPT_DIR"
echo "🐍 Test script: $TEST_SCRIPT"

# Check if test script exists
if [ ! -f "$TEST_SCRIPT" ]; then
    echo "❌ Test script not found: $TEST_SCRIPT"
    exit 1
fi

# Install required Python packages if needed
echo "📦 Checking Python dependencies..."
python3 -c "import boto3, json, time, logging, datetime" 2>/dev/null || {
    echo "⚠️ Installing required Python packages..."
    pip3 install boto3 --user
}

# Get AWS account info
echo "🔍 AWS Account Information:"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region || echo "us-east-1")
echo "   Account ID: $AWS_ACCOUNT_ID"
echo "   Region: $AWS_REGION"

# Check for Lambda functions
echo "🔍 Checking for Lambda functions..."
LAMBDA_FUNCTIONS=$(aws lambda list-functions --query 'Functions[?contains(FunctionName, `performance`) || contains(FunctionName, `network`) || contains(FunctionName, `flow`)].FunctionName' --output text)

if [ -n "$LAMBDA_FUNCTIONS" ]; then
    echo "✅ Found potential Lambda functions:"
    for func in $LAMBDA_FUNCTIONS; do
        echo "   - $func"
    done
else
    echo "⚠️ No performance-related Lambda functions found"
    echo "   The test will attempt to auto-detect or use default names"
fi

echo ""
echo "🚀 Starting Lambda function tests..."
echo "================================"

# Run the test script
cd "$SCRIPT_DIR"
python3 "$TEST_SCRIPT"

TEST_EXIT_CODE=$?

echo ""
echo "================================"
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "🎉 All tests completed successfully!"
else
    echo "💥 Some tests failed (exit code: $TEST_EXIT_CODE)"
fi

echo "📄 Check the generated JSON file for detailed results"
echo "🔍 Log files may contain additional debugging information"

exit $TEST_EXIT_CODE
