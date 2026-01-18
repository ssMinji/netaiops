#!/bin/bash

# AgentCore Evaluation Framework - AWS Prerequisites Setup Script
# This script automatically sets up all required AWS resources and permissions

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
EVALUATION_ROLE_NAME="AgentCoreEvaluationRole"
EVALUATION_POLICY_NAME="AgentCoreEvaluationPolicy"
S3_BUCKET_NAME=""  # Will be set after getting AWS account ID
REGION=${AWS_DEFAULT_REGION:-us-east-1}

echo -e "${BLUE}🚀 AgentCore Evaluation Framework - AWS Setup${NC}"
echo -e "${BLUE}===============================================${NC}"

# Function to check if AWS CLI is configured
check_aws_config() {
    echo -e "${YELLOW}Checking AWS CLI configuration...${NC}"
    
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}❌ AWS CLI is not installed. Please install it first.${NC}"
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}❌ AWS CLI is not configured or credentials are invalid.${NC}"
        echo -e "${YELLOW}Please run 'aws configure' first.${NC}"
        exit 1
    fi
    
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    echo -e "${GREEN}✅ AWS CLI configured for account: ${ACCOUNT_ID}${NC}"
    
    # Set S3 bucket name using account ID (only if not already set via command line)
    if [ -z "$S3_BUCKET_NAME" ]; then
        S3_BUCKET_NAME="agentcore-evaluation-results-${ACCOUNT_ID}"
    fi
    
    # Display current AWS identity
    echo -e "${YELLOW}Current AWS Identity:${NC}"
    aws sts get-caller-identity 2>/dev/null
}

# Function to install Python dependencies
install_python_dependencies() {
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    
    # Check if Python 3 is available
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python 3 is not available.${NC}"
        echo -e "${YELLOW}Please install Python 3 manually and re-run this script.${NC}"
        exit 1
    fi
    
    # Display Python version
    echo -e "${GREEN}✅ Using Python version: $(python3 --version)${NC}"
    
    # Ensure pip is available for Python 3
    if ! python3 -m pip --version &> /dev/null; then
        echo -e "${YELLOW}Installing pip for Python 3...${NC}"
        curl -sS https://bootstrap.pypa.io/get-pip.py | python3 2>/dev/null
    fi
    
    # Check if requirements.txt exists
    if [ ! -f "requirements.txt" ]; then
        echo -e "${RED}❌ requirements.txt not found. Please ensure you're running from the module-4 directory.${NC}"
        exit 1
    fi
    
    # Upgrade pip to latest version
    echo -e "${YELLOW}Upgrading pip to latest version...${NC}"
    python3 -m pip install --upgrade pip --user --quiet --root-user-action=ignore 2>/dev/null || python3 -m pip install --upgrade pip --user --quiet 2>/dev/null || true
    
    # Install dependencies using Python 3
    echo -e "${YELLOW}Installing Python packages from requirements.txt...${NC}"
    python3 -m pip install -r requirements.txt --user --quiet --root-user-action=ignore 2>/dev/null || python3 -m pip install -r requirements.txt --user --quiet 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Python dependencies installed successfully${NC}"
    else
        echo -e "${RED}❌ Failed to install Python dependencies${NC}"
        echo -e "${YELLOW}Trying alternative installation method...${NC}"
        
        # Try without --user flag as fallback
        python3 -m pip install -r requirements.txt --quiet --root-user-action=ignore 2>/dev/null || python3 -m pip install -r requirements.txt --quiet 2>/dev/null
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ Python dependencies installed successfully (fallback method)${NC}"
        else
            echo -e "${RED}❌ Failed to install Python dependencies with all methods${NC}"
            exit 1
        fi
    fi
}

# Function to check Bedrock model access
check_bedrock_access() {
    echo -e "${YELLOW}Checking Bedrock model access...${NC}"
    
    # Check if Claude Sonnet 4 is available
    if aws bedrock list-foundation-models --region $REGION --query 'modelSummaries[?contains(modelId, `claude-sonnet-4`)]' --output text | grep -q claude; then
        echo -e "${GREEN}✅ Claude Sonnet 4 model access available${NC}"
    else
        echo -e "${YELLOW}⚠️  Claude Sonnet 4 not available, checking for Claude 3.5 Sonnet...${NC}"
        if aws bedrock list-foundation-models --region $REGION --query 'modelSummaries[?contains(modelId, `claude-3-5-sonnet`)]' --output text | grep -q claude; then
            echo -e "${GREEN}✅ Claude 3.5 Sonnet available as fallback${NC}"
        else
            echo -e "${RED}❌ No Claude models available. Please request access in Bedrock console.${NC}"
            echo -e "${YELLOW}Navigate to: AWS Console > Bedrock > Model Access > Request Access${NC}"
            exit 1
        fi
    fi
}

# Function to create IAM policy
create_iam_policy() {
    echo -e "${YELLOW}Creating IAM policy: ${EVALUATION_POLICY_NAME}...${NC}"
    
    # Create policy document
    cat > /tmp/evaluation_policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ListFoundationModels"
            ],
            "Resource": [
                "arn:aws:bedrock:*::foundation-model/global.anthropic.claude-sonnet-4-*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:StartQuery",
                "logs:GetQueryResults",
                "logs:FilterLogEvents",
                "logs:DescribeLogGroups",
                "logs:DescribeLogStreams"
            ],
            "Resource": [
                "arn:aws:logs:*:${ACCOUNT_ID}:log-group:/aws/lambda/agentcore-*",
                "arn:aws:logs:*:${ACCOUNT_ID}:log-group:/aws/ecs/agentcore-*",
                "arn:aws:logs:*:${ACCOUNT_ID}:log-group:/aws/bedrock-agentcore/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "bedrock-agent:GetAgent",
                "bedrock-agent:ListAgents",
                "bedrock-agent:InvokeAgent"
            ],
            "Resource": "arn:aws:bedrock-agent:*:${ACCOUNT_ID}:agent/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "cloudformation:DescribeStacks",
                "cloudformation:ListStacks",
                "cloudformation:DescribeStackResources"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "lambda:GetFunction",
                "lambda:ListFunctions",
                "lambda:GetFunctionConfiguration"
            ],
            "Resource": "arn:aws:lambda:*:${ACCOUNT_ID}:function:*agentcore*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "iam:GetRole",
                "iam:ListRoles",
                "iam:GetPolicy",
                "iam:ListPolicies"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::${S3_BUCKET_NAME}",
                "arn:aws:s3:::${S3_BUCKET_NAME}/*",
                "arn:aws:s3:::${S3_BUCKET_NAME}/baseline-deploy-${ACCOUNT_ID}/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "sts:GetCallerIdentity"
            ],
            "Resource": "*"
        }
    ]
}
EOF

    # Create or update policy
    if aws iam get-policy --policy-arn "arn:aws:iam::${ACCOUNT_ID}:policy/${EVALUATION_POLICY_NAME}" &> /dev/null; then
        echo -e "${YELLOW}Policy exists, updating...${NC}"
        aws iam create-policy-version \
            --policy-arn "arn:aws:iam::${ACCOUNT_ID}:policy/${EVALUATION_POLICY_NAME}" \
            --policy-document file:///tmp/evaluation_policy.json \
            --set-as-default
    else
        aws iam create-policy \
            --policy-name "${EVALUATION_POLICY_NAME}" \
            --policy-document file:///tmp/evaluation_policy.json \
            --description "Policy for AgentCore Evaluation Framework"
    fi
    
    echo -e "${GREEN}✅ IAM policy created/updated: ${EVALUATION_POLICY_NAME}${NC}"
    rm /tmp/evaluation_policy.json
}

# Function to create IAM role
create_iam_role() {
    echo -e "${YELLOW}Creating IAM role: ${EVALUATION_ROLE_NAME}...${NC}"
    
    # Create trust policy
    cat > /tmp/trust_policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::${ACCOUNT_ID}:root"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

    # Create role if it doesn't exist
    if ! aws iam get-role --role-name "${EVALUATION_ROLE_NAME}" &> /dev/null; then
        aws iam create-role \
            --role-name "${EVALUATION_ROLE_NAME}" \
            --assume-role-policy-document file:///tmp/trust_policy.json \
            --description "Role for AgentCore Evaluation Framework"
    else
        echo -e "${YELLOW}Role already exists, updating trust policy...${NC}"
        aws iam update-assume-role-policy \
            --role-name "${EVALUATION_ROLE_NAME}" \
            --policy-document file:///tmp/trust_policy.json
    fi
    
    # Attach policy to role
    aws iam attach-role-policy \
        --role-name "${EVALUATION_ROLE_NAME}" \
        --policy-arn "arn:aws:iam::${ACCOUNT_ID}:policy/${EVALUATION_POLICY_NAME}"
    
    echo -e "${GREEN}✅ IAM role created/updated: ${EVALUATION_ROLE_NAME}${NC}"
    rm /tmp/trust_policy.json
}

# Function to create S3 bucket for results
create_s3_bucket() {
    echo -e "${YELLOW}Creating S3 bucket for evaluation results...${NC}"
    echo -e "${BLUE}Bucket name: ${S3_BUCKET_NAME}${NC}"
    
    # Check if bucket already exists
    if aws s3 ls "s3://${S3_BUCKET_NAME}" &> /dev/null; then
        echo -e "${GREEN}✅ S3 bucket already exists: ${S3_BUCKET_NAME}${NC}"
    else
        echo -e "${YELLOW}Creating new S3 bucket: ${S3_BUCKET_NAME}${NC}"
        # Create bucket
        if [ "$REGION" = "us-east-1" ]; then
            aws s3 mb "s3://${S3_BUCKET_NAME}" --region $REGION
        else
            aws s3 mb "s3://${S3_BUCKET_NAME}" --region $REGION --create-bucket-configuration LocationConstraint=$REGION
        fi
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ S3 bucket created successfully: ${S3_BUCKET_NAME}${NC}"
        else
            echo -e "${RED}❌ Failed to create S3 bucket: ${S3_BUCKET_NAME}${NC}"
            exit 1
        fi
    fi
    
    # Enable versioning
    aws s3api put-bucket-versioning \
        --bucket "${S3_BUCKET_NAME}" \
        --versioning-configuration Status=Enabled
    
    # Wait for IAM role propagation before setting bucket policy
    echo -e "${YELLOW}Waiting for IAM role propagation...${NC}"
    sleep 15
    
    # Set bucket policy for evaluation results with retry logic
    cat > /tmp/bucket_policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::${ACCOUNT_ID}:role/${EVALUATION_ROLE_NAME}"
            },
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::${S3_BUCKET_NAME}",
                "arn:aws:s3:::${S3_BUCKET_NAME}/*"
            ]
        }
    ]
}
EOF

    # Apply bucket policy with retry logic
    echo -e "${YELLOW}Applying S3 bucket policy...${NC}"
    for i in {1..5}; do
        if aws s3api put-bucket-policy \
            --bucket "${S3_BUCKET_NAME}" \
            --policy file:///tmp/bucket_policy.json 2>/dev/null; then
            echo -e "${GREEN}✅ S3 bucket policy applied successfully${NC}"
            break
        else
            echo -e "${YELLOW}⚠️  Attempt $i failed, retrying in 15 seconds...${NC}"
            if [ $i -eq 5 ]; then
                echo -e "${RED}❌ Failed to apply bucket policy after 5 attempts${NC}"
                echo -e "${YELLOW}⚠️  Continuing without bucket policy - you may need to configure it manually${NC}"
            else
                sleep 15
            fi
        fi
    done
    
    echo -e "${GREEN}✅ S3 bucket created: ${S3_BUCKET_NAME}${NC}"
    rm /tmp/bucket_policy.json
}

# Function to create environment configuration file
create_env_config() {
    echo -e "${YELLOW}Creating environment configuration...${NC}"
    
    cat > .env << EOF
# AgentCore Evaluation Framework Configuration
AWS_DEFAULT_REGION=${REGION}
AWS_ACCOUNT_ID=${ACCOUNT_ID}
EVALUATION_ROLE_ARN=arn:aws:iam::${ACCOUNT_ID}:role/${EVALUATION_ROLE_NAME}
S3_RESULTS_BUCKET=${S3_BUCKET_NAME}

# Bedrock Configuration
BEDROCK_MODEL_ID=global.anthropic.claude-opus-4-5-20251101-v1:0
BEDROCK_FALLBACK_MODEL=global.anthropic.claude-opus-4-5-20251101-v1:0

# CloudWatch Configuration
CLOUDWATCH_TIMEOUT=30
CLOUDWATCH_MAX_RETRIES=3

# Evaluation Configuration
EVALUATION_TIMEOUT=300
MAX_CONCURRENT_EVALUATIONS=3
HTML_REPORT_TEMPLATE=dashboard

# S3 Upload Configuration
S3_UPLOAD_ENABLED=true
S3_BASELINE_FOLDER=baseline-deploy-${ACCOUNT_ID}
EOF

    echo -e "${GREEN}✅ Environment configuration created: .env${NC}"
}

# Function to validate setup
validate_setup() {
    echo -e "${YELLOW}Validating setup...${NC}"
    
    # Test role assumption
    TEMP_CREDS=$(aws sts assume-role \
        --role-arn "arn:aws:iam::${ACCOUNT_ID}:role/${EVALUATION_ROLE_NAME}" \
        --role-session-name "validation-test" \
        --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
        --output text)
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Role assumption test passed${NC}"
    else
        echo -e "${RED}❌ Role assumption test failed${NC}"
        exit 1
    fi
    
    # Test S3 access
    echo "test" | aws s3 cp - "s3://${S3_BUCKET_NAME}/validation-test.txt"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ S3 access test passed${NC}"
        aws s3 rm "s3://${S3_BUCKET_NAME}/validation-test.txt"
    else
        echo -e "${RED}❌ S3 access test failed${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ All validation tests passed${NC}"
}

# Function to display next steps
display_next_steps() {
    echo -e "${BLUE}🎉 Setup Complete! Next Steps:${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
    echo -e "${GREEN}1. Run a quick test:${NC}"
    echo -e "   ${YELLOW}./scripts/run_evaluation.sh --safety-only${NC}"
    echo ""
    echo -e "${GREEN}2. Generate HTML report:${NC}"
    echo -e "   ${YELLOW}./scripts/generate_html_report.sh${NC}"
    echo ""
    echo -e "${GREEN}3. View results:${NC}"
    echo -e "   ${YELLOW}open reports/evaluation_dashboard.html${NC}"
    echo ""
    echo -e "${BLUE}Configuration Details:${NC}"
    echo -e "   AWS Account: ${ACCOUNT_ID}"
    echo -e "   Region: ${REGION}"
    echo -e "   IAM Role: ${EVALUATION_ROLE_NAME}"
    echo -e "   S3 Bucket: ${S3_BUCKET_NAME}"
    echo -e "   Config File: .env"
    echo -e "   Python Dependencies: ✅ Installed"
    echo ""
    echo -e "${GREEN}🚀 Ready to evaluate your AgentCore agents!${NC}"
}

# Main execution
main() {
    echo -e "${BLUE}Starting AWS prerequisites setup...${NC}"
    
    # Ensure we're in the correct directory (module-4)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    MODULE4_DIR="$(dirname "$SCRIPT_DIR")"
    
    echo -e "${YELLOW}Script directory: ${SCRIPT_DIR}${NC}"
    echo -e "${YELLOW}Module-4 directory: ${MODULE4_DIR}${NC}"
    
    # Change to module-4 directory
    cd "$MODULE4_DIR" || {
        echo -e "${RED}❌ Failed to change to module-4 directory: ${MODULE4_DIR}${NC}"
        exit 1
    }
    
    echo -e "${GREEN}✅ Working from directory: $(pwd)${NC}"
    
    check_aws_config
    install_python_dependencies
    check_bedrock_access
    create_iam_policy
    create_iam_role
    create_s3_bucket
    create_env_config
    validate_setup
    display_next_steps
    
    echo -e "${GREEN}✅ AWS prerequisites setup completed successfully!${NC}"
}

# Handle script interruption
trap 'echo -e "\n${RED}Setup interrupted. Cleaning up...${NC}"; exit 1' INT TERM

# Check for help flag
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "AgentCore Evaluation Framework - AWS Prerequisites Setup"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  --region       AWS region (default: \$AWS_DEFAULT_REGION or us-east-1)"
    echo "  --role-name    Custom IAM role name (default: AgentCoreEvaluationRole)"
    echo "  --bucket-name  Custom S3 bucket name (default: auto-generated)"
    echo ""
    echo "Prerequisites:"
    echo "  - AWS CLI installed and configured"
    echo "  - Admin permissions in target AWS account"
    echo "  - Bedrock service available in target region"
    exit 0
fi

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --region)
            REGION="$2"
            shift 2
            ;;
        --role-name)
            EVALUATION_ROLE_NAME="$2"
            shift 2
            ;;
        --bucket-name)
            S3_BUCKET_NAME="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Run main function
main
