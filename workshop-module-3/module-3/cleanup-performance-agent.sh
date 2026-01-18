#!/bin/bash

# Performance Agent Cleanup Script
# This script removes all resources created during the performance agent setup
# Enhanced to read from performance-agent-resources.yml for comprehensive cleanup

set -e

echo "🧹 Performance Agent Cleanup Script"
echo "=================================="
echo "This script will remove ALL resources created during performance agent setup."
echo "⚠️  WARNING: This action cannot be undone!"
echo ""

# Get AWS region and account info
REGION=${AWS_DEFAULT_REGION:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
RESOURCES_FILE="performance-agent-resources.yml"

echo "📋 Account: $ACCOUNT_ID | Region: $REGION"

# Check if resources file exists
if [[ -f "$RESOURCES_FILE" ]]; then
    echo "📋 Found resource file: $RESOURCES_FILE"
    echo "   This file will be used to ensure complete cleanup"
else
    echo "⚠️  Resource file not found: $RESOURCES_FILE"
    echo "   Proceeding with standard cleanup (may miss some resources)"
fi

echo ""

# Confirmation prompt
read -p "Are you sure you want to proceed with cleanup? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "❌ Cleanup cancelled"
    exit 0
fi

echo ""
echo "🚀 Starting Performance Agent Cleanup..."
echo ""

# Function to handle errors gracefully
handle_error() {
    local error_message="$1"
    echo "⚠️  Warning: $error_message"
    echo "   Continuing with cleanup..."
}

# Function to extract values from YAML file
extract_yaml_value() {
    local key="$1"
    local file="$2"
    if [[ -f "$file" ]]; then
        grep -A 1000 "^resources:" "$file" | grep -E "^\s*${key}:" | head -1 | sed "s/.*${key}:\s*[\"']\?\([^\"']*\)[\"']\?.*/\1/" | tr -d '"' | tr -d "'"
    fi
}

# Function to extract all SSM parameters from YAML
extract_ssm_parameters() {
    local file="$1"
    if [[ -f "$file" ]]; then
        grep -A 1000 "^ssm_parameters:" "$file" | grep -E "^\s*-\s*name:" | sed 's/.*name:\s*[\"'"'"']\?\([^\"'"'"']*\)[\"'"'"']\?.*/\1/' | tr -d '"' | tr -d "'"
    fi
}

# Function to extract resource names by type from YAML
extract_resources_by_type() {
    local resource_type="$1"
    local file="$2"
    if [[ -f "$file" ]]; then
        # Use awk to parse YAML and extract names for specific resource types
        awk -v type="$resource_type" '
        /^resources:/ { in_resources = 1; next }
        /^[a-zA-Z]/ && !/^\s/ && in_resources { in_resources = 0 }
        in_resources && /^\s*-\s*type:/ { 
            if ($0 ~ type) { 
                found_type = 1 
            } else { 
                found_type = 0 
            }
        }
        in_resources && found_type && /^\s*name:/ { 
            gsub(/.*name:\s*[\"'"'"']?/, "")
            gsub(/[\"'"'"'].*/, "")
            print $0
            found_type = 0
        }
        ' "$file"
    fi
}

# Navigate to agentcore-performance-agent directory if it exists
if [[ -d "agentcore-performance-agent" ]]; then
    cd agentcore-performance-agent
    echo "📁 Changed to agentcore-performance-agent directory"
    
    # Activate virtual environment if it exists
    if [[ -d ".venv" ]]; then
        source .venv/bin/activate
        echo "🐍 Activated virtual environment"
    fi
fi

# Step 1: Delete Agent Runtime
echo "🗑️  Step 1: Deleting Agent Runtime..."
RUNTIME_NAMES=()
if [[ -f "../$RESOURCES_FILE" ]]; then
    while IFS= read -r name; do
        [[ -n "$name" ]] && RUNTIME_NAMES+=("$name")
    done < <(extract_resources_by_type "Bedrock Agent Runtime" "../$RESOURCES_FILE")
fi

# Add default runtime name if not found in YAML
[[ ${#RUNTIME_NAMES[@]} -eq 0 ]] && RUNTIME_NAMES=("a2a_performance_agent_runtime")

for runtime_name in "${RUNTIME_NAMES[@]}"; do
    if python3 scripts/agentcore_agent_runtime.py delete "$runtime_name" 2>/dev/null; then
        echo "✅ Agent runtime deleted: $runtime_name"
    else
        handle_error "Failed to delete agent runtime: $runtime_name (may not exist)"
    fi
done
echo ""

# Step 2: Delete Gateway
echo "🗑️  Step 2: Deleting Gateway..."
GATEWAY_NAMES=()
if [[ -f "../$RESOURCES_FILE" ]]; then
    while IFS= read -r name; do
        [[ -n "$name" ]] && GATEWAY_NAMES+=("$name")
    done < <(extract_resources_by_type "Bedrock Agent Gateway" "../$RESOURCES_FILE")
fi

# Add default gateway name if not found in YAML
[[ ${#GATEWAY_NAMES[@]} -eq 0 ]] && GATEWAY_NAMES=("a2a-performance-gateway")

for gateway_name in "${GATEWAY_NAMES[@]}"; do
    if python3 scripts/agentcore_gateway.py delete --confirm 2>/dev/null; then
        echo "✅ Gateway deleted: $gateway_name"
    else
        handle_error "Failed to delete gateway: $gateway_name (may not exist)"
    fi
done
echo ""

# Step 3: Delete Memory Configuration
echo "🗑️  Step 3: Deleting Memory Configuration..."
if python3 scripts/setup_memory.py --action delete 2>/dev/null; then
    echo "✅ Memory configuration deleted successfully"
else
    handle_error "Failed to delete memory configuration (may not exist)"
fi
echo ""

# Step 4: Delete Performance Tools (Lambda, ECR, IAM roles)
echo "🗑️  Step 4: Deleting Performance Tools..."

# Delete Lambda functions
echo "   Deleting Lambda functions..."
LAMBDA_NAMES=()
if [[ -f "../$RESOURCES_FILE" ]]; then
    while IFS= read -r name; do
        [[ -n "$name" ]] && LAMBDA_NAMES+=("$name")
    done < <(extract_resources_by_type "Lambda Function" "../$RESOURCES_FILE")
fi

# Add default lambda name if not found in YAML
[[ ${#LAMBDA_NAMES[@]} -eq 0 ]] && LAMBDA_NAMES=("a2a-performance-tools")

for lambda_name in "${LAMBDA_NAMES[@]}"; do
    if aws lambda delete-function --function-name "$lambda_name" --region $REGION 2>/dev/null; then
        echo "   ✅ Lambda function deleted: $lambda_name"
    else
        handle_error "Lambda function not found or already deleted: $lambda_name"
    fi
done

# Delete ECR repositories
echo "   Deleting ECR repositories..."
ECR_NAMES=()
if [[ -f "../$RESOURCES_FILE" ]]; then
    while IFS= read -r name; do
        [[ -n "$name" ]] && ECR_NAMES+=("$name")
    done < <(extract_resources_by_type "ECR Repository" "../$RESOURCES_FILE")
fi

# Add default ECR name if not found in YAML
[[ ${#ECR_NAMES[@]} -eq 0 ]] && ECR_NAMES=("a2a-performance-tools-repo")

for ecr_name in "${ECR_NAMES[@]}"; do
    if aws ecr delete-repository --repository-name "$ecr_name" --region $REGION --force 2>/dev/null; then
        echo "   ✅ ECR repository deleted: $ecr_name"
    else
        handle_error "ECR repository not found or already deleted: $ecr_name"
    fi
done

# Delete IAM roles
echo "   Deleting IAM roles..."
IAM_ROLE_NAMES=()
if [[ -f "../$RESOURCES_FILE" ]]; then
    while IFS= read -r name; do
        [[ -n "$name" ]] && IAM_ROLE_NAMES+=("$name")
    done < <(extract_resources_by_type "IAM Role" "../$RESOURCES_FILE")
fi

# Add default role names if not found in YAML
[[ ${#IAM_ROLE_NAMES[@]} -eq 0 ]] && IAM_ROLE_NAMES=("a2a-performance-tools-role" "performance-gateway-execution-role")

for role_name in "${IAM_ROLE_NAMES[@]}"; do
    echo "   Processing IAM role: $role_name"
    
    # Detach managed policies
    echo "     Detaching managed policies..."
    aws iam detach-role-policy --role-name "$role_name" --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true
    aws iam detach-role-policy --role-name "$role_name" --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess 2>/dev/null || true
    
    # Delete all inline policies
    echo "     Deleting inline policies..."
    if POLICIES=$(aws iam list-role-policies --role-name "$role_name" --query 'PolicyNames' --output text 2>/dev/null); then
        for policy in $POLICIES; do
            if [[ -n "$policy" && "$policy" != "None" ]]; then
                aws iam delete-role-policy --role-name "$role_name" --policy-name "$policy" 2>/dev/null || true
                echo "       Deleted inline policy: $policy"
            fi
        done
    fi
    
    # Delete the role
    if aws iam delete-role --role-name "$role_name" 2>/dev/null; then
        echo "   ✅ IAM role deleted: $role_name"
    else
        handle_error "IAM role not found or already deleted: $role_name"
    fi
done

echo "✅ Performance tools cleanup completed"
echo ""

# Step 5: Delete Cognito Credentials Provider
echo "🗑️  Step 5: Deleting Cognito Credentials Provider..."
if python3 scripts/cognito_credentials_provider.py delete-provider 2>/dev/null; then
    echo "✅ Cognito credentials provider deleted successfully"
else
    handle_error "Failed to delete Cognito credentials provider (may not exist)"
fi
echo ""

# Step 6: Delete Infrastructure (CloudFormation stacks, Cognito pools)
echo "🗑️  Step 6: Deleting Infrastructure..."

# Delete CloudFormation stacks
echo "   Deleting CloudFormation stacks..."
CF_STACK_NAMES=()
if [[ -f "../$RESOURCES_FILE" ]]; then
    while IFS= read -r name; do
        [[ -n "$name" ]] && CF_STACK_NAMES+=("$name")
    done < <(extract_resources_by_type "CloudFormation Stack" "../$RESOURCES_FILE")
fi

# Add default stack names if not found in YAML
[[ ${#CF_STACK_NAMES[@]} -eq 0 ]] && CF_STACK_NAMES=("a2a-performance-agentcore-cognito" "performance-agent-infrastructure")

for stack_name in "${CF_STACK_NAMES[@]}"; do
    echo "   Checking for CloudFormation stack: $stack_name"
    if aws cloudformation describe-stacks --stack-name "$stack_name" --region $REGION >/dev/null 2>&1; then
        echo "   Deleting CloudFormation stack: $stack_name"
        aws cloudformation delete-stack --stack-name "$stack_name" --region $REGION
        echo "   ⏳ Waiting for stack deletion to complete..."
        aws cloudformation wait stack-delete-complete --stack-name "$stack_name" --region $REGION
        echo "   ✅ CloudFormation stack deleted: $stack_name"
    else
        echo "   ℹ️  CloudFormation stack not found: $stack_name"
    fi
done

# Delete Cognito User Pools
echo "   Deleting Cognito User Pools..."
COGNITO_POOL_IDS=()
if [[ -f "../$RESOURCES_FILE" ]]; then
    while IFS= read -r name; do
        [[ -n "$name" ]] && COGNITO_POOL_IDS+=("$name")
    done < <(extract_resources_by_type "Cognito User Pool" "../$RESOURCES_FILE")
fi

# If no pools found in YAML, try to find them by name pattern
if [[ ${#COGNITO_POOL_IDS[@]} -eq 0 ]]; then
    USER_POOL_NAME="performance-agent-pool"
    USER_POOL_ID=$(aws cognito-idp list-user-pools --max-results 50 --region $REGION --query "UserPools[?Name=='$USER_POOL_NAME'].Id" --output text 2>/dev/null || echo "")
    [[ -n "$USER_POOL_ID" && "$USER_POOL_ID" != "None" ]] && COGNITO_POOL_IDS+=("$USER_POOL_ID")
fi

for pool_id in "${COGNITO_POOL_IDS[@]}"; do
    echo "   Deleting Cognito User Pool: $pool_id"
    if aws cognito-idp delete-user-pool --user-pool-id "$pool_id" --region $REGION 2>/dev/null; then
        echo "   ✅ Cognito User Pool deleted: $pool_id"
    else
        handle_error "Failed to delete Cognito User Pool: $pool_id"
    fi
done

echo "✅ Infrastructure cleanup completed"
echo ""

# Step 7: Clean up SSM Parameters
echo "🗑️  Step 7: Cleaning up SSM Parameters..."

# Get SSM parameters from YAML file
SSM_PARAMETERS=()
if [[ -f "../$RESOURCES_FILE" ]]; then
    while IFS= read -r param; do
        [[ -n "$param" ]] && SSM_PARAMETERS+=("$param")
    done < <(extract_ssm_parameters "../$RESOURCES_FILE")
fi

# Add default parameters if not found in YAML
if [[ ${#SSM_PARAMETERS[@]} -eq 0 ]]; then
    SSM_PARAMETERS=(
        "/a2a/app/performance/agentcore/lambda_arn"
        "/a2a/app/performance/agentcore/gateway_iam_role"
        "/a2a/app/performance/agentcore/gateway_id"
        "/a2a/app/performance/agentcore/gateway_name"
        "/a2a/app/performance/agentcore/gateway_arn"
        "/a2a/app/performance/agentcore/gateway_url"
        "/a2a/app/performance/agentcore/machine_client_id"
        "/a2a/app/performance/agentcore/web_client_id"
        "/a2a/app/performance/agentcore/cognito_provider"
        "/a2a/app/performance/agentcore/cognito_domain"
        "/a2a/app/performance/agentcore/cognito_token_url"
        "/a2a/app/performance/agentcore/cognito_discovery_url"
        "/a2a/app/performance/agentcore/cognito_auth_url"
        "/a2a/app/performance/agentcore/cognito_auth_scope"
        "/a2a/app/performance/agentcore/userpool_id"
    )
fi

for param in "${SSM_PARAMETERS[@]}"; do
    if aws ssm delete-parameter --name "$param" --region $REGION 2>/dev/null; then
        echo "   ✅ Deleted SSM parameter: $param"
    else
        echo "   ℹ️  SSM parameter not found: $param"
    fi
done

echo "✅ SSM parameters cleanup completed"
echo ""

# Step 8: Clean up CloudWatch Log Groups
echo "🗑️  Step 8: Cleaning up CloudWatch Log Groups..."
LOG_GROUPS=(
    "/aws/lambda/a2a-performance-tools"
    "/aws/bedrock-agentcore/runtimes/a2a_performance_agent_runtime"
    "/aws/vpc/flowlogs"
)

for log_group in "${LOG_GROUPS[@]}"; do
    # List all log groups that match the pattern
    aws logs describe-log-groups --log-group-name-prefix "$log_group" --region $REGION --query 'logGroups[].logGroupName' --output text 2>/dev/null | tr '\t' '\n' | while read group; do
        if [[ -n "$group" ]]; then
            if aws logs delete-log-group --log-group-name "$group" --region $REGION 2>/dev/null; then
                echo "   ✅ Deleted log group: $group"
            else
                echo "   ⚠️  Failed to delete log group: $group"
            fi
        fi
    done
done

echo "✅ CloudWatch log groups cleanup completed"
echo ""

# Step 9: Clean up Docker images (local cleanup)
echo "🗑️  Step 9: Cleaning up local Docker images..."
if command -v docker >/dev/null 2>&1; then
    echo "   Removing performance-related Docker images..."
    docker images --format "table {{.Repository}}:{{.Tag}}" | grep -E "(a2a-performance|performance-tools)" | while read image; do
        if [[ -n "$image" && "$image" != "REPOSITORY:TAG" ]]; then
            docker rmi "$image" 2>/dev/null || handle_error "Failed to remove Docker image: $image"
            echo "   ✅ Removed Docker image: $image"
        fi
    done
    
    # Clean up dangling images
    docker image prune -f >/dev/null 2>&1 || true
    echo "   ✅ Docker cleanup completed"
else
    echo "   ℹ️  Docker not found, skipping Docker cleanup"
fi
echo ""

# Step 10: Clean up local files
echo "🗑️  Step 10: Cleaning up local files..."

# Remove virtual environment
if [[ -d ".venv" ]]; then
    rm -rf .venv
    echo "   ✅ Removed virtual environment: .venv"
fi

# Remove configuration backup
if [[ -f "../stage4-config.json.backup" ]]; then
    rm -f "../stage4-config.json.backup"
    echo "   ✅ Removed configuration backup: stage4-config.json.backup"
fi

# Remove resources file
if [[ -f "../$RESOURCES_FILE" ]]; then
    rm -f "../$RESOURCES_FILE"
    echo "   ✅ Removed resources file: $RESOURCES_FILE"
fi

echo "✅ Local files cleanup completed"
echo ""

# Final summary
echo "🎉 Performance Agent Cleanup Complete!"
echo "======================================"
echo ""
echo "✅ Cleaned up resources:"
echo "   • Agent runtime and gateway"
echo "   • Memory configuration"
echo "   • Performance tools (Lambda, ECR, IAM roles)"
echo "   • Cognito credentials provider"
echo "   • Infrastructure (CloudFormation stacks, Cognito pools, IAM roles)"
echo "   • SSM parameters"
echo "   • CloudWatch log groups"
echo "   • Local Docker images"
echo "   • Local files (virtual environment, backups, resource file)"
echo ""
echo "ℹ️  Note: Some resources may have been already deleted or may not have existed."
echo "ℹ️  If you encounter any remaining resources, you may need to delete them manually."
echo ""
echo "🔍 To verify cleanup, you can check:"
echo "   • AWS Lambda console for any remaining functions"
echo "   • AWS ECR console for any remaining repositories"
echo "   • AWS IAM console for any remaining roles"
echo "   • AWS Cognito console for any remaining user pools"
echo "   • AWS CloudWatch console for any remaining log groups"
echo "   • AWS CloudFormation console for any remaining stacks"
echo "   • AWS Systems Manager Parameter Store for any remaining parameters"
echo ""
echo "✨ Cleanup completed successfully!"
