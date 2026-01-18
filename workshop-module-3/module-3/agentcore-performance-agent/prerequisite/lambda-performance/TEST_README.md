# Fix Retransmissions Integration Test

This directory contains an integration test for the `fix_retransmissions` Lambda function tool.

## Overview

The `fix_retransmissions` tool fixes TCP retransmission issues by:
- Restoring optimal TCP buffer sizes
- Re-enabling TCP window scaling
- Restoring proper TCP retransmission settings
- Removing network impairment (packet loss and delay via tc qdisc)

## Test Script

**File:** `test_fix_retransmissions.py`

This Python script invokes the Lambda function with the `fix_retransmissions` tool to test its functionality in the AWS environment.

## Prerequisites

1. **AWS Credentials**: Ensure AWS credentials are configured via AWS CLI or environment variables
2. **Lambda Function**: The performance-tools Lambda function must be deployed
3. **IAM Permissions**: Your AWS credentials must have permission to:
   - Invoke Lambda functions
   - Describe CloudFormation stacks
   - Access EC2 instances (for auto-detection)

## Configuration

The test is pre-configured for:
- **AWS Account**: `104398007905`
- **Region**: `us-east-1`
- **Default Stack**: `acme-image-gallery-perf`

You can override these defaults using command-line arguments.

## Usage

### Basic Usage (Auto-detect bastion server)

```bash
cd module-3/agentcore-performance-agent/prerequisite/lambda-performance
python test_fix_retransmissions.py
```

or

```bash
./test_fix_retransmissions.py
```

### Specify Instance ID

```bash
python test_fix_retransmissions.py --instance-id i-0123456789abcdef0
```

### Specify Stack Name

```bash
python test_fix_retransmissions.py --stack-name my-custom-stack
```

### Specify Region

```bash
python test_fix_retransmissions.py --region us-west-2
```

### Combined Options

```bash
