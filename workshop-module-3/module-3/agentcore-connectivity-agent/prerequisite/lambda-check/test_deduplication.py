#!/usr/bin/env python3
"""
Test script to verify Network Insights Path deduplication functionality.
This script simulates multiple Lambda invocations with the same parameters
to ensure paths are reused instead of creating duplicates.
"""

import json
import sys
import os

# Add the lambda function directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python'))

from lambda_function import lambda_handler

class MockContext:
    """Mock Lambda context for testing."""
    def __init__(self):
        self.client_context = MockClientContext()

class MockClientContext:
    """Mock client context."""
    def __init__(self):
        self.custom = {'bedrockAgentCoreToolName': 'connectivity-check'}

def test_deduplication():
    """Test that multiple calls with same parameters reuse existing paths."""
    
