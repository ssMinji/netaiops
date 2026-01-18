# Traffic Mirroring Troubleshooting Guide

## Issue: PCAP files showing as `instance-/` and not appearing in S3

### Root Cause
The instance metadata retrieval is failing, causing the instance ID to be empty. This results in:
1. Directory created as `instance-/` instead of `instance-i-xxxxx/`
2. PCAP files not being uploaded to S3 properly

### Diagnostic Steps

## Step 1: Check if the Traffic Mirroring Target instance is running

```bash
# Get the instance ID from CloudFormation stack outputs
aws cloudformation describe-stacks \
  --stack-name <your-traffic-mirroring-stack-name> \
  --query 'Stacks[0].Outputs[?OutputKey==`TrafficMirroringTargetInstanceId`].OutputValue' \
  --output text

# Check instance status
INSTANCE_ID="<instance-id-from-above>"
aws ec2 describe-instances --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].[InstanceId,State.Name,PrivateIpAddress]' \
  --output table
```

## Step 2: Connect to the instance via SSM

```bash
aws ssm start-session --target $INSTANCE_ID
```

## Step 3: Check the tcpdump service status

```bash
# Check if service is running
sudo systemctl status trafficmirror-tcpdump.service

# Check service logs
sudo journalctl -u trafficmirror-tcpdump.service -n 50 --no-pager

# Check system logs for metadata retrieval errors
