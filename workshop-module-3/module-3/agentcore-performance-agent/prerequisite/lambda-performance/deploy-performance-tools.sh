#!/bin/bash

# One-Click Performance Tools Lambda Deployment - Idempotent Version with Exponential Backoff
# Uses Docker containers (up to 10GB) to overcome 70MB layer limit
set -e

echo "🚀 One-Click Performance Tools Lambda Deployment (Idempotent with Retry Logic)"
echo "=============================================================================="

# Get script directory and source IAM utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
IAM_UTILS_PATH="$SCRIPT_DIR/../../scripts/iam_utils.sh"

if [ -f "$IAM_UTILS_PATH" ]; then
    echo "📦 Loading IAM utilities with exponential backoff..."
    source "$IAM_UTILS_PATH"
else
    echo "⚠️  Warning: IAM utilities not found at $IAM_UTILS_PATH"
    echo "   Falling back to simple retry logic"
fi

# Configuration
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
STACK_NAME="a2a-performance-tools-lambda"
ECR_REPOSITORY="a2a-performance-tools-repo"
FUNCTION_NAME="a2a-performance-tools"
ROLE_NAME="a2a-performance-tools-role"
FLOWLOGS_ROLE_NAME="flowlogsRole"

# Get Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "📋 Account: $ACCOUNT_ID | Region: $REGION"

# Helper function to check if IAM role exists
check_role_exists() {
    local role_name=$1
    aws iam get-role --role-name "$role_name" --region "$REGION" &> /dev/null
    return $?
}

# Helper function to check if policy is attached to role
check_policy_attached() {
    local role_name=$1
    local policy_arn=$2
    aws iam list-attached-role-policies --role-name "$role_name" --region "$REGION" 2>/dev/null | \
        grep -q "$policy_arn"
    return $?
}

# Helper function to check if Lambda function exists
check_lambda_exists() {
    local function_name=$1
    aws lambda get-function --function-name "$function_name" --region "$REGION" &> /dev/null
    return $?
}

# Build Docker image with Performance tools packages (no size limits!)
echo "🐳 Building Docker image for Performance Lambda (x86_64 architecture)..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR/python"
docker build --platform linux/amd64 -t a2a-performance-tools-lambda:latest .
cd "$SCRIPT_DIR"

# Build ECR URI
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPOSITORY}"

# Check if ECR repository exists, create if not (idempotent)
echo "🔍 Checking ECR repository..."
if ! aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${REGION} &> /dev/null; then
    echo "📦 Creating ECR repository..."
    aws ecr create-repository --repository-name ${ECR_REPOSITORY} --region ${REGION}
else
    echo "✅ ECR repository already exists"
fi

# Login to ECR
echo "🔑 Logging in to ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Tag and push Docker image
echo "🏷️  Tagging and pushing Docker image..."
docker tag a2a-performance-tools-lambda:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# Create Lambda execution role with retry (idempotent)
echo "🔐 Checking Lambda execution role..."
if check_role_exists "$ROLE_NAME"; then
    echo "✅ Lambda execution role already exists: $ROLE_NAME"
else
    echo "🆕 Creating Lambda execution role with retry logic..."
    aws iam create-role \
        --role-name ${ROLE_NAME} \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                },
                {
                    "Effect": "Allow", 
                    "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }' \
        --region ${REGION}
    echo "✅ Lambda execution role created"
    
    # Wait for role propagation
    LAMBDA_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
    if type wait_for_iam_role_propagation &>/dev/null; then
        wait_for_iam_role_propagation "$LAMBDA_ROLE_ARN" 30
    else
        echo "⏳ Waiting 30 seconds for Lambda role propagation..."
        sleep 30
    fi
fi

# Attach managed policies (idempotent)
echo "🔗 Attaching managed policies..."
MANAGED_POLICIES=(
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    "arn:aws:iam::aws:policy/ReadOnlyAccess"
)

for policy_arn in "${MANAGED_POLICIES[@]}"; do
    if check_policy_attached "$ROLE_NAME" "$policy_arn"; then
        echo "  ✅ Policy already attached: $(basename $policy_arn)"
    else
        echo "  🔗 Attaching policy: $(basename $policy_arn)"
        aws iam attach-role-policy \
            --role-name ${ROLE_NAME} \
            --policy-arn "$policy_arn" \
            --region ${REGION}
    fi
done

# Add inline policies (idempotent - put-role-policy overwrites)
echo "📝 Adding inline policies..."

# Bedrock permissions
echo "  📝 Adding Bedrock permissions..."
aws iam put-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-name BedrockInvokePolicy \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            "Resource": "*"
        }]
    }' \
    --region ${REGION}

# Performance Tools permissions
echo "  📝 Adding Performance Tools permissions..."
aws iam put-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-name PerformanceToolsPolicy \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:ListBucket"
                ],
                "Resource": [
                    "arn:aws:s3:::traffic-mirroring-analysis-*",
                    "arn:aws:s3:::traffic-mirroring-analysis-*/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DescribeInstances",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeVpcs",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeNetworkAcls",
                    "ec2:DescribeRouteTables",
                    "ec2:DescribeFlowLogs",
                    "ec2:CreateFlowLogs",
                    "ec2:DeleteFlowLogs",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:CreateTrafficMirrorTarget",
                    "ec2:CreateTrafficMirrorFilter",
                    "ec2:CreateTrafficMirrorFilterRule",
                    "ec2:CreateTrafficMirrorSession",
                    "ec2:DeleteTrafficMirrorTarget",
                    "ec2:DeleteTrafficMirrorFilter",
                    "ec2:DeleteTrafficMirrorSession",
                    "ec2:DescribeTrafficMirrorTargets",
                    "ec2:DescribeTrafficMirrorFilters",
                    "ec2:DescribeTrafficMirrorSessions",
                    "ec2:CreateTags",
                    "ec2:DeleteTags",
                    "ec2:DescribeTags",
                    "ec2:DescribeAvailabilityZones",
                    "ec2:DescribeRegions",
                    "ec2:CreateNetworkInsightsPath",
                    "ec2:StartNetworkInsightsAnalysis",
                    "ec2:DescribeNetworkInsightsAnalyses",
                    "ec2:DescribeNetworkInsightsPaths",
                    "ec2:DeleteNetworkInsightsPath"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "networkflowmonitor:CreateMonitor",
                    "networkflowmonitor:DeleteMonitor",
                    "networkflowmonitor:GetMonitor",
                    "networkflowmonitor:ListMonitors",
                    "networkflowmonitor:UpdateMonitor",
                    "networkflowmonitor:TagResource",
                    "networkflowmonitor:UntagResource",
                    "networkflowmonitor:ListTagsForResource",
                    "networkflowmonitor:GetQueryResultsMonitorTopContributors",
                    "networkflowmonitor:GetQueryStatusMonitorTopContributors",
                    "networkflowmonitor:StartQueryMonitorTopContributors",
                    "networkflowmonitor:StopQueryMonitorTopContributors",
                    "networkflowmonitor:CreateScope",
                    "networkflowmonitor:DeleteScope",
                    "networkflowmonitor:GetScope",
                    "networkflowmonitor:ListScopes",
                    "networkflowmonitor:UpdateScope"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "cloudwatch:GetMetricStatistics",
                    "cloudwatch:ListMetrics",
                    "cloudwatch:PutMetricData",
                    "cloudwatch:GetMetricData",
                    "cloudwatch:DescribeAlarms",
                    "cloudwatch:PutMetricAlarm",
                    "cloudwatch:DeleteAlarms"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                    "logs:TagResource",
                    "logs:UntagResource",
                    "logs:ListTagsLogGroup",
                    "logs:StartQuery",
                    "logs:StopQuery",
                    "logs:GetQueryResults",
                    "logs:DescribeQueries",
                    "logs:FilterLogEvents",
                    "logs:GetLogEvents"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ssm:SendCommand",
                    "ssm:GetCommandInvocation",
                    "ssm:DescribeInstanceInformation",
                    "ssm:ListCommandInvocations",
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:GetParametersByPath",
                    "ssm:PutParameter"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "iam:PassRole",
                    "iam:GetRole",
                    "iam:ListAttachedRolePolicies",
                    "iam:ListRolePolicies",
                    "iam:GetRolePolicy"
                ],
                "Resource": [
                    "arn:aws:iam::*:role/flowlogsRole",
                    "arn:aws:iam::*:role/performance-*",
                    "arn:aws:iam::*:role/a2a-performance-*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "sts:GetCallerIdentity"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "application-insights:CreateApplication",
                    "application-insights:DeleteApplication",
                    "application-insights:DescribeApplication",
                    "application-insights:ListApplications",
                    "application-insights:UpdateApplication"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                    "xray:GetTraceGraph",
                    "xray:GetTraceSummaries"
                ],
                "Resource": "*"
            }
        ]
    }' \
    --region ${REGION}

# Create flowlogsRole for VPC Flow Logs delivery with retry (idempotent)
echo "🔐 Checking flowlogsRole for VPC Flow Logs..."
if check_role_exists "$FLOWLOGS_ROLE_NAME"; then
    echo "✅ flowlogsRole already exists"
else
    echo "🆕 Creating flowlogsRole with retry logic..."
    aws iam create-role \
        --role-name ${FLOWLOGS_ROLE_NAME} \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "vpc-flow-logs.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }' \
        --region ${REGION}
    echo "✅ flowlogsRole created"
    
    # Wait for role propagation
    FLOWLOGS_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${FLOWLOGS_ROLE_NAME}"
    if type wait_for_iam_role_propagation &>/dev/null; then
        wait_for_iam_role_propagation "$FLOWLOGS_ROLE_ARN" 30
    else
        echo "⏳ Waiting 30 seconds for Flow Logs role propagation..."
        sleep 30
    fi
fi

# Add policy for VPC Flow Logs delivery (idempotent)
echo "📝 Adding FlowLogs delivery policy..."
aws iam put-role-policy \
    --role-name ${FLOWLOGS_ROLE_NAME} \
    --policy-name FlowLogsDeliveryRolePolicy \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams"
                ],
                "Resource": "*"
            }
        ]
    }' \
    --region ${REGION}

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "✅ IAM roles configured successfully"

# Wait for IAM role propagation with smart backoff
if type wait_for_iam_role_propagation &>/dev/null; then
    wait_for_iam_role_propagation "$ROLE_ARN" 30
else
    # Fallback to simple wait if utilities not loaded
    echo "⏳ Waiting 30 seconds for IAM role propagation..."
    sleep 30
fi

# Helper function for retry with fixed wait times
retry_with_backoff() {
    local max_attempts=$1
    shift
    local description=$1
    shift
    
    # Fixed wait times: 45s for 2nd attempt, 60s for 3rd attempt
    local wait_times=(0 45 60)
    
    for attempt in $(seq 1 $max_attempts); do
        echo "  🔄 Attempt $attempt of $max_attempts: $description"
        
        # Capture both stdout and stderr
        local output
        local exit_code
        output=$(eval "$@" 2>&1) || exit_code=$?
        
        if [ -z "${exit_code:-}" ]; then
            echo "  ✅ $description succeeded"
            return 0
        fi
        
        # Parse error message
        echo "  ⚠️  Attempt $attempt failed with exit code: $exit_code"
        echo "  📝 Error details: ${output:0:500}"
        
        # Check for specific IAM errors that need retry
        if echo "$output" | grep -qE "(InvalidParameterValueException.*role|cannot be assumed|role.*not exist|AccessDenied|not authorized)"; then
            if [ $attempt -lt $max_attempts ]; then
                local wait_time=${wait_times[$attempt]}
                echo "  🔐 Detected IAM propagation issue - will retry"
                echo "  ⏳ Waiting ${wait_time}s before retry..."
                sleep $wait_time
            else
                echo "  ❌ Max retries ($max_attempts) reached"
                echo "  💡 IAM role may need more time to propagate"
                echo "$output"
                return 1
            fi
        elif echo "$output" | grep -qE "(ResourceConflictException|TooManyRequestsException|ServiceException|InternalErrorException)"; then
            if [ $attempt -lt $max_attempts ]; then
                local wait_time=${wait_times[$attempt]}
                echo "  ⚙️  Detected transient AWS service issue - will retry"
                echo "  ⏳ Waiting ${wait_time}s before retry..."
                sleep $wait_time
            else
                echo "  ❌ Max retries ($max_attempts) reached"
                echo "$output"
                return 1
            fi
        else
            # Not a retryable error, fail immediately
            echo "  ❌ Non-retryable error detected"
            echo "$output"
            return 1
        fi
    done
    
    return 1
}

# Create/update Lambda function (idempotent with retry logic)
echo "⚡ Deploying Lambda function with retry logic..."
if check_lambda_exists "$FUNCTION_NAME"; then
    echo "  ✅ Lambda function already exists: $FUNCTION_NAME"
    echo "  🔄 Updating function code..."
    
    retry_with_backoff 3 "Lambda code update" \
        aws lambda update-function-code \
            --function-name ${FUNCTION_NAME} \
            --image-uri ${ECR_URI}:latest \
            --region ${REGION}
    
    # Wait for update to complete
    echo "  ⏳ Waiting for Lambda update to complete..."
    aws lambda wait function-updated \
        --function-name ${FUNCTION_NAME} \
        --region ${REGION} 2>&1 || {
        echo "  ⚠️  Wait timeout, checking function state..."
        local state=$(aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} --query 'Configuration.State' --output text 2>/dev/null || echo "Unknown")
        echo "  📊 Current function state: $state"
        if [ "$state" != "Active" ] && [ "$state" != "Unknown" ]; then
            echo "  ⚠️  Function not yet active, waiting 30s more..."
            sleep 30
        fi
    }
    
    # Update configuration if needed
    echo "  🔧 Updating Lambda configuration..."
    retry_with_backoff 2 "Lambda configuration update" \
        aws lambda update-function-configuration \
            --function-name ${FUNCTION_NAME} \
            --timeout 900 \
            --memory-size 3008 \
            --region ${REGION}
    
    echo "  ✅ Lambda function updated successfully"
else
    echo "  🆕 Creating new Lambda function: $FUNCTION_NAME"
    echo "  🔐 Using IAM role: $ROLE_ARN"
    echo "  🐳 Using container image: ${ECR_URI}:latest"
    
    # Verify IAM role exists before attempting Lambda creation
    echo "  🔍 Verifying IAM role exists..."
    if ! aws iam get-role --role-name ${ROLE_NAME} --region ${REGION} &>/dev/null; then
        echo "  ❌ ERROR: IAM role ${ROLE_NAME} does not exist"
        echo "     Role ARN: ${ROLE_ARN}"
        exit 1
    fi
    echo "  ✅ IAM role verified"
    
    # Additional wait for IAM propagation before Lambda creation
    echo "  ⏳ Waiting 30s for IAM role to fully propagate..."
    sleep 30
    
    # Create Lambda with retry logic (up to 3 attempts)
    retry_with_backoff 3 "Lambda function creation" \
        aws lambda create-function \
            --function-name ${FUNCTION_NAME} \
            --package-type Image \
            --code ImageUri=${ECR_URI}:latest \
            --role ${ROLE_ARN} \
            --timeout 900 \
            --memory-size 3008 \
            --region ${REGION}
    
    echo "  ✅ Lambda function created successfully"
fi

LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"

# Verify gateway execution role exists
GATEWAY_ROLE_NAME="performance-gateway-execution-role"
echo "🚪 Verifying Gateway execution role..."
GATEWAY_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${GATEWAY_ROLE_NAME}"

if ! check_role_exists "$GATEWAY_ROLE_NAME"; then
    echo "❌ Gateway execution role not found. Please deploy CloudFormation stack first:"
    echo "   cd scripts && ./prereq.sh"
    exit 1
fi
echo "✅ Gateway role verified: ${GATEWAY_ROLE_ARN}"

# Store parameters for gateway integration (idempotent with --overwrite)
echo "💾 Storing SSM parameters..."
aws ssm put-parameter \
    --name "/a2a/app/performance/agentcore/lambda_arn" \
    --value "$LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region $REGION

aws ssm put-parameter \
    --name "/a2a/app/performance/agentcore/gateway_iam_role" \
    --value "$GATEWAY_ROLE_ARN" \
    --type "String" \
    --overwrite \
    --region $REGION

echo ""
echo "✅ One-Click Performance Tools Deployment Complete!"
echo "=================================================="
echo "   Lambda ARN: $LAMBDA_ARN"
echo "   Gateway Role ARN: $GATEWAY_ROLE_ARN"
echo "   Container Image: ${ECR_URI}:latest"
echo ""
echo "🔧 Available Performance Tools:"
echo "   • analyze_vpc_flow_metrics - Analyze VPC flow monitoring data for performance issues"
echo "   • create_subnet_flow_monitor - Create subnet-level VPC Flow Logs monitoring"
echo "   • setup_traffic_mirroring - Configure VPC Traffic Mirroring for packet analysis"
echo "   • analyze_tcp_performance - Analyze TCP performance between IP addresses"
echo "   • analyze_network_flow_monitor - Analyze all Network Flow Monitors in region/account"
echo "   • install_network_flow_monitor_agent - Install network monitoring agent via SSM"
echo ""
echo "ℹ️  Script Features:"
echo "   • Idempotent - safe to run multiple times"
echo "   • Exponential backoff for IAM propagation errors"
echo "   • Automatic retry on transient failures"
echo ""
echo "🎯 Next Steps:"
echo "   python ../../scripts/agentcore_gateway.py create --name performance-gateway"
echo "   python ../../scripts/agentcore_agent_runtime.py create --name performance_agent_runtime"
