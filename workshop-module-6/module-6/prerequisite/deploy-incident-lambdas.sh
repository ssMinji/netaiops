#!/bin/bash

# Incident Management Lambda Deployment - Docker Container Approach
# Deploys 6 Lambda functions: Datadog, OpenSearch, Container Insight, Chaos, Alarm Trigger, GitHub
set -e

PROFILE="netaiops-deploy"
REGION="us-east-1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==========================================="
echo " Incident Management Lambda Deployment"
echo "==========================================="

# -----------------------------------------------
# 1. Get Account ID
# -----------------------------------------------
ACCOUNT_ID=$(aws sts get-caller-identity --profile ${PROFILE} --query Account --output text)
echo "Account: $ACCOUNT_ID | Region: $REGION | Profile: $PROFILE"

# -----------------------------------------------
# 2. Authenticate to ECR Public (base image)
# -----------------------------------------------
echo ""
echo "Authenticating to ECR Public for base image access..."
max_retries=3
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if aws ecr-public get-login-password --region us-east-1 --profile ${PROFILE} | docker login --username AWS --password-stdin public.ecr.aws; then
        echo "Successfully authenticated to ECR Public"
        break
    else
        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            echo "ECR Public authentication failed, retrying in 5 seconds... (attempt $retry_count/$max_retries)"
            sleep 5
        else
            echo "ERROR: Failed to authenticate to ECR Public after $max_retries attempts"
            exit 1
        fi
    fi
done

# -----------------------------------------------
# 3. Authenticate to Private ECR
# -----------------------------------------------
echo ""
echo "Logging in to private ECR..."
max_retries=3
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if aws ecr get-login-password --region ${REGION} --profile ${PROFILE} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com; then
        echo "Successfully authenticated to private ECR"
        break
    else
        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            echo "Private ECR authentication failed, retrying in 5 seconds... (attempt $retry_count/$max_retries)"
            sleep 5
        else
            echo "ERROR: Failed to authenticate to private ECR after $max_retries attempts"
            exit 1
        fi
    fi
done

# -----------------------------------------------
# 4. Create shared IAM role (if not exists)
# -----------------------------------------------
ROLE_NAME="incident-tools-lambda-role"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

echo ""
echo "Creating shared IAM execution role: ${ROLE_NAME}..."
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
    --profile ${PROFILE} \
    --region ${REGION} 2>/dev/null || echo "Role already exists, continuing..."

# Attach Lambda basic execution
aws iam attach-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    --profile ${PROFILE} 2>/dev/null || true

# Add combined inline policy for all 3 Lambdas
echo "Attaching combined permissions policy..."
aws iam put-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-name IncidentToolsCombinedPolicy \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "CloudWatchReadForContainerInsight",
                "Effect": "Allow",
                "Action": [
                    "cloudwatch:DescribeAlarms",
                    "cloudwatch:DescribeAlarmsForMetric",
                    "cloudwatch:GetMetricData",
                    "cloudwatch:GetMetricStatistics",
                    "cloudwatch:ListMetrics",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                    "logs:GetLogEvents",
                    "logs:FilterLogEvents",
                    "logs:StartQuery",
                    "logs:StopQuery",
                    "logs:GetQueryResults",
                    "logs:DescribeQueries"
                ],
                "Resource": "*"
            },
            {
                "Sid": "OpenSearchAccess",
                "Effect": "Allow",
                "Action": [
                    "es:ESHttpGet",
                    "es:ESHttpHead",
                    "es:ESHttpPost",
                    "es:ESHttpPut",
                    "es:ESHttpDelete",
                    "es:ESHttpPatch"
                ],
                "Resource": "*"
            },
            {
                "Sid": "SSMParameterAccess",
                "Effect": "Allow",
                "Action": [
                    "ssm:GetParameter",
                    "ssm:GetParameters"
                ],
                "Resource": "arn:aws:ssm:*:*:parameter/app/incident/*"
            },
            {
                "Sid": "EKSAccessForChaosLambda",
                "Effect": "Allow",
                "Action": [
                    "eks:DescribeCluster",
                    "eks:ListClusters"
                ],
                "Resource": "*"
            },
            {
                "Sid": "STSForEKSAuth",
                "Effect": "Allow",
                "Action": [
                    "sts:GetCallerIdentity"
                ],
                "Resource": "*"
            }
        ]
    }' \
    --profile ${PROFILE} \
    --region ${REGION} 2>/dev/null || true

echo "Role ready: $ROLE_ARN"

# Wait for role to propagate
echo "Waiting for IAM role to propagate..."
sleep 20

# Verify role propagation
echo "Verifying role propagation..."
for i in {1..12}; do
    if aws iam get-role --role-name ${ROLE_NAME} --profile ${PROFILE} --region ${REGION} &>/dev/null; then
        echo "Role verified and ready"
        break
    fi
    if [ $i -eq 12 ]; then
        echo "ERROR: Role verification failed after 60 seconds"
        exit 1
    fi
    echo "  Attempt $i/12 - waiting 5 more seconds..."
    sleep 5
done

# -----------------------------------------------
# Helper function: deploy a single Lambda
# -----------------------------------------------
deploy_lambda() {
    local FUNCTION_NAME="$1"
    local ECR_REPOSITORY="$2"
    local LAMBDA_DIR="$3"
    local ENV_VARS="$4"

    echo ""
    echo "==========================================="
    echo " Deploying: ${FUNCTION_NAME}"
    echo "==========================================="

    # Build Docker image
    echo "Building Docker image for ${FUNCTION_NAME} (x86_64)..."
    docker build --platform linux/amd64 -t ${FUNCTION_NAME}:latest "${SCRIPT_DIR}/${LAMBDA_DIR}/python"

    # Create ECR repo if needed
    local ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPOSITORY}"
    echo "Checking ECR repository: ${ECR_REPOSITORY}..."
    if ! aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${REGION} --profile ${PROFILE} &>/dev/null; then
        echo "Creating ECR repository: ${ECR_REPOSITORY}..."
        aws ecr create-repository --repository-name ${ECR_REPOSITORY} --region ${REGION} --profile ${PROFILE}
    fi

    # Tag and push
    echo "Tagging and pushing Docker image..."
    docker tag ${FUNCTION_NAME}:latest ${ECR_URI}:latest
    docker push ${ECR_URI}:latest

    # Create or update Lambda function
    echo "Deploying Lambda function: ${FUNCTION_NAME}..."
    if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} --profile ${PROFILE} &>/dev/null; then
        echo "Function exists, updating code..."
        aws lambda update-function-code \
            --function-name ${FUNCTION_NAME} \
            --image-uri ${ECR_URI}:latest \
            --region ${REGION} \
            --profile ${PROFILE}

        # Wait for update to complete before updating configuration
        echo "Waiting for function update to complete..."
        aws lambda wait function-updated \
            --function-name ${FUNCTION_NAME} \
            --region ${REGION} \
            --profile ${PROFILE} 2>/dev/null || sleep 10

        # Update environment variables if provided
        if [ -n "$ENV_VARS" ]; then
            echo "Updating environment variables..."
            aws lambda update-function-configuration \
                --function-name ${FUNCTION_NAME} \
                --environment "${ENV_VARS}" \
                --region ${REGION} \
                --profile ${PROFILE}
        fi
    else
        echo "Function does not exist, creating..."
        if [ -n "$ENV_VARS" ]; then
            aws lambda create-function \
                --function-name ${FUNCTION_NAME} \
                --package-type Image \
                --code ImageUri=${ECR_URI}:latest \
                --role ${ROLE_ARN} \
                --timeout 300 \
                --memory-size 1024 \
                --environment "${ENV_VARS}" \
                --region ${REGION} \
                --profile ${PROFILE}
        else
            aws lambda create-function \
                --function-name ${FUNCTION_NAME} \
                --package-type Image \
                --code ImageUri=${ECR_URI}:latest \
                --role ${ROLE_ARN} \
                --timeout 300 \
                --memory-size 1024 \
                --region ${REGION} \
                --profile ${PROFILE}
        fi
    fi

    echo "Deployed: arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"
}

# -----------------------------------------------
# 5. Read SSM parameters for environment variables
# -----------------------------------------------
echo ""
echo "Reading SSM parameters for Lambda environment variables..."

# Datadog parameters
DATADOG_API_KEY=$(aws ssm get-parameter --name "/app/incident/datadog/api_key" --with-decryption --query "Parameter.Value" --output text --region ${REGION} --profile ${PROFILE} 2>/dev/null || echo "")
DATADOG_APP_KEY=$(aws ssm get-parameter --name "/app/incident/datadog/app_key" --with-decryption --query "Parameter.Value" --output text --region ${REGION} --profile ${PROFILE} 2>/dev/null || echo "")
DATADOG_SITE=$(aws ssm get-parameter --name "/app/incident/datadog/site" --query "Parameter.Value" --output text --region ${REGION} --profile ${PROFILE} 2>/dev/null || echo "us5.datadoghq.com")

# OpenSearch parameters
OPENSEARCH_ENDPOINT=$(aws ssm get-parameter --name "/app/incident/opensearch/endpoint" --query "Parameter.Value" --output text --region ${REGION} --profile ${PROFILE} 2>/dev/null || echo "")

if [ -z "$DATADOG_API_KEY" ] || [ -z "$DATADOG_APP_KEY" ]; then
    echo "WARNING: Datadog API/APP keys not found in SSM. Datadog Lambda will be deployed without keys."
    echo "  Set them later with:"
    echo "    aws ssm put-parameter --name /app/incident/datadog/api_key --value YOUR_KEY --type SecureString --profile ${PROFILE} --region ${REGION}"
    echo "    aws ssm put-parameter --name /app/incident/datadog/app_key --value YOUR_KEY --type SecureString --profile ${PROFILE} --region ${REGION}"
fi

if [ -z "$OPENSEARCH_ENDPOINT" ]; then
    echo "WARNING: OpenSearch endpoint not found in SSM. OpenSearch Lambda will be deployed without endpoint."
    echo "  Set it later with:"
    echo "    aws ssm put-parameter --name /app/incident/opensearch/endpoint --value YOUR_ENDPOINT --type String --profile ${PROFILE} --region ${REGION}"
fi

# -----------------------------------------------
# 6. Deploy all 3 Lambda functions
# -----------------------------------------------

# 6a. Datadog Lambda
DATADOG_ENV=""
if [ -n "$DATADOG_API_KEY" ] && [ -n "$DATADOG_APP_KEY" ]; then
    DATADOG_ENV='{"Variables":{"DATADOG_API_KEY":"'"${DATADOG_API_KEY}"'","DATADOG_APP_KEY":"'"${DATADOG_APP_KEY}"'","DATADOG_SITE":"'"${DATADOG_SITE}"'"}}'
fi
deploy_lambda "incident-datadog-tools" "incident-datadog-tools-repo" "lambda-datadog" "$DATADOG_ENV"

# 6b. OpenSearch Lambda
OPENSEARCH_ENV=""
if [ -n "$OPENSEARCH_ENDPOINT" ]; then
    OPENSEARCH_ENV='{"Variables":{"OPENSEARCH_ENDPOINT":"'"${OPENSEARCH_ENDPOINT}"'","AWS_REGION_NAME":"'"${REGION}"'"}}'
fi
deploy_lambda "incident-opensearch-tools" "incident-opensearch-tools-repo" "lambda-opensearch" "$OPENSEARCH_ENV"

# 6c. Container Insight Lambda (no special env vars needed)
deploy_lambda "incident-container-insight-tools" "incident-container-insight-tools-repo" "lambda-container-insight" ""

# 6d. Chaos Engineering Lambda
CHAOS_ENV='{"Variables":{"EKS_CLUSTER_NAME":"netaiops-eks-cluster","EKS_CLUSTER_REGION":"us-west-2"}}'
deploy_lambda "incident-chaos-tools" "incident-chaos-tools-repo" "lambda-chaos" "$CHAOS_ENV"

# 6e. Alarm Trigger Lambda (SNS → Agent invocation)
ALARM_TRIGGER_ENV='{"Variables":{"AGENT_REGION":"'"${REGION}"'"}}'
deploy_lambda "incident-alarm-trigger" "incident-alarm-trigger-repo" "lambda-alarm-trigger" "$ALARM_TRIGGER_ENV"

# 6f. GitHub Issues Lambda
GITHUB_ENV='{"Variables":{"AGENT_REGION":"'"${REGION}"'"}}'
deploy_lambda "incident-github-tools" "incident-github-tools-repo" "lambda-github" "$GITHUB_ENV"

# -----------------------------------------------
# 7. Store Lambda ARNs in SSM
# -----------------------------------------------
echo ""
echo "==========================================="
echo " Storing Lambda ARNs in SSM"
echo "==========================================="

DATADOG_LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:incident-datadog-tools"
OPENSEARCH_LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:incident-opensearch-tools"
CONTAINER_INSIGHT_LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:incident-container-insight-tools"
CHAOS_LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:incident-chaos-tools"
ALARM_TRIGGER_LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:incident-alarm-trigger"
GITHUB_LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:incident-github-tools"

aws ssm put-parameter \
    --name "/app/incident/agentcore/datadog_lambda_arn" \
    --value "$DATADOG_LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}

aws ssm put-parameter \
    --name "/app/incident/agentcore/opensearch_lambda_arn" \
    --value "$OPENSEARCH_LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}

aws ssm put-parameter \
    --name "/app/incident/agentcore/container_insight_lambda_arn" \
    --value "$CONTAINER_INSIGHT_LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}

aws ssm put-parameter \
    --name "/app/incident/agentcore/chaos_lambda_arn" \
    --value "$CHAOS_LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}

aws ssm put-parameter \
    --name "/app/incident/agentcore/alarm_trigger_lambda_arn" \
    --value "$ALARM_TRIGGER_LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}

aws ssm put-parameter \
    --name "/app/incident/agentcore/github_lambda_arn" \
    --value "$GITHUB_LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}

# -----------------------------------------------
# 8. Summary
# -----------------------------------------------
echo ""
echo "==========================================="
echo " Incident Lambda Deployment Complete!"
echo "==========================================="
echo ""
echo "Lambda Functions:"
echo "  Datadog:           $DATADOG_LAMBDA_ARN"
echo "  OpenSearch:        $OPENSEARCH_LAMBDA_ARN"
echo "  Container Insight: $CONTAINER_INSIGHT_LAMBDA_ARN"
echo "  Chaos Tools:       $CHAOS_LAMBDA_ARN"
echo "  Alarm Trigger:     $ALARM_TRIGGER_LAMBDA_ARN"
echo "  GitHub Issues:     $GITHUB_LAMBDA_ARN"
echo ""
echo "IAM Role: $ROLE_ARN"
echo ""
echo "SSM Parameters:"
echo "  /app/incident/agentcore/datadog_lambda_arn"
echo "  /app/incident/agentcore/opensearch_lambda_arn"
echo "  /app/incident/agentcore/container_insight_lambda_arn"
echo "  /app/incident/agentcore/chaos_lambda_arn"
echo "  /app/incident/agentcore/alarm_trigger_lambda_arn"
echo "  /app/incident/agentcore/github_lambda_arn"
echo ""
echo "Next Steps:"
echo "  1. Setup GitHub integration:"
echo "     ./setup-github.sh"
echo "  2. Setup EKS RBAC for chaos Lambda:"
echo "     ./setup-eks-rbac.sh"
echo "  3. Create gateway with incident tools (include chaos + github Lambdas):"
echo "     python ../../scripts/agentcore_gateway.py create --name incident-gateway"
echo "  4. Deploy runtime:"
echo "     python ../../scripts/agentcore_agent_runtime.py create --name incident_agent_runtime"
echo "  5. Setup CloudWatch alarms:"
echo "     ./setup-alarms.sh"
