#!/bin/bash
# =============================================================================
# Istio Prometheus Lambda Deployment (Module 7)
# Istio Prometheus Lambda 배포 (모듈 7)
# =============================================================================
set -e

PROFILE="${AWS_PROFILE:-netaiops-deploy}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==========================================="
echo " Istio Prometheus Lambda Deployment"
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
ROLE_NAME="istio-tools-lambda-role"
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

# Add inline policy for AMP access
echo "Attaching AMP query permissions policy..."
aws iam put-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-name IstioToolsPolicy \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AMPQueryAccess",
                "Effect": "Allow",
                "Action": [
                    "aps:QueryMetrics",
                    "aps:GetMetricData",
                    "aps:GetSeries",
                    "aps:GetLabels",
                    "aps:RemoteWrite"
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
                "Resource": "arn:aws:ssm:*:*:parameter/app/istio/*"
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
# 5. Read AMP endpoint from SSM
# -----------------------------------------------
echo ""
echo "Reading AMP endpoint from SSM..."
AMP_QUERY_ENDPOINT=$(aws ssm get-parameter \
    --name "/app/istio/agentcore/amp_query_endpoint" \
    --query "Parameter.Value" \
    --output text \
    --region ${REGION} \
    --profile ${PROFILE} 2>/dev/null || echo "")

if [ -z "$AMP_QUERY_ENDPOINT" ]; then
    echo "WARNING: AMP query endpoint not found in SSM."
    echo "  Run setup-amp.sh first, or set it manually:"
    echo "    aws ssm put-parameter --name /app/istio/agentcore/amp_query_endpoint --value YOUR_ENDPOINT --type String"
fi

# -----------------------------------------------
# 6. Deploy Lambda function
# -----------------------------------------------
FUNCTION_NAME="istio-prometheus-tools"
ECR_REPOSITORY="istio-prometheus-tools-repo"
LAMBDA_DIR="lambda-istio-prometheus"

echo ""
echo "==========================================="
echo " Deploying: ${FUNCTION_NAME}"
echo "==========================================="

# Build Docker image
echo "Building Docker image for ${FUNCTION_NAME} (x86_64)..."
docker build --platform linux/amd64 -t ${FUNCTION_NAME}:latest "${SCRIPT_DIR}/${LAMBDA_DIR}/python"

# Create ECR repo if needed
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPOSITORY}"
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
ENV_VARS=""
if [ -n "$AMP_QUERY_ENDPOINT" ]; then
    ENV_VARS='{"Variables":{"AMP_QUERY_ENDPOINT":"'"${AMP_QUERY_ENDPOINT}"'","AWS_REGION_NAME":"'"${REGION}"'"}}'
fi

if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} --profile ${PROFILE} &>/dev/null; then
    echo "Function exists, updating code..."
    aws lambda update-function-code \
        --function-name ${FUNCTION_NAME} \
        --image-uri ${ECR_URI}:latest \
        --region ${REGION} \
        --profile ${PROFILE}

    echo "Waiting for function update to complete..."
    aws lambda wait function-updated \
        --function-name ${FUNCTION_NAME} \
        --region ${REGION} \
        --profile ${PROFILE} 2>/dev/null || sleep 10

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

LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"
echo "Deployed: ${LAMBDA_ARN}"

# -----------------------------------------------
# 7. Store Lambda ARN in SSM
# -----------------------------------------------
echo ""
echo "Storing Lambda ARN in SSM..."
aws ssm put-parameter \
    --name "/app/istio/agentcore/prometheus_lambda_arn" \
    --value "$LAMBDA_ARN" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}

# -----------------------------------------------
# 8. Summary
# -----------------------------------------------
echo ""
echo "==========================================="
echo " Istio Lambda Deployment Complete!"
echo "==========================================="
echo ""
echo "Lambda Function: $LAMBDA_ARN"
echo "IAM Role:        $ROLE_ARN"
echo ""
echo "SSM Parameters:"
echo "  /app/istio/agentcore/prometheus_lambda_arn"
echo ""
echo "Test invocation:"
echo '  aws lambda invoke --function-name istio-prometheus-tools \'
echo '    --payload '"'"'{"method":"tools/list"}'"'"' /tmp/out.json --profile '"${PROFILE}"' --region '"${REGION}"
echo '  cat /tmp/out.json | python -m json.tool'
echo ""
echo "Next Steps:"
echo "  1. Deploy agent: cd agentcore-istio-agent && agentcore deploy"
echo "  2. Create gateway: python scripts/agentcore_gateway.py create --name istio-mesh-gateway"
