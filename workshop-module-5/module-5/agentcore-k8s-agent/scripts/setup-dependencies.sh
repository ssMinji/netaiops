#!/bin/bash

# NetOps K8s Agent Dependencies Setup Script
# Based on proven working reference implementation

set -e

echo "K8s Agent Dependencies Setup"
echo "==================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory and project paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}Project root: $PROJECT_DIR${NC}"

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to setup Python virtual environment and dependencies
setup_python_environment() {
    echo -e "${BLUE}Setting up Python virtual environment...${NC}"

    if [[ ! -f "${PROJECT_DIR}/requirements.txt" ]]; then
        echo -e "${RED}requirements.txt not found in ${PROJECT_DIR}${NC}"
        return 1
    fi

    # Create virtual environment if it doesn't exist (idempotent check)
    if [[ ! -d "${PROJECT_DIR}/.venv" ]]; then
        echo "   Creating virtual environment..."
        if python3 -m venv "${PROJECT_DIR}/.venv"; then
            echo -e "${GREEN}Virtual environment created${NC}"
        else
            echo -e "${RED}Failed to create virtual environment${NC}"
            return 1
        fi
    else
        echo -e "${GREEN}Virtual environment already exists (skipping creation)${NC}"
    fi

    # Activate virtual environment and install dependencies
    echo "   Installing Python dependencies..."
    cd "${PROJECT_DIR}"
    source .venv/bin/activate

    # Upgrade pip first
    pip install --upgrade pip > /dev/null 2>&1

    # Check Python version for compatibility
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)
    echo "   Python version detected: $PYTHON_VERSION"

    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
        echo "   Python 3.10+ detected - compatible with AWS AgentCore samples"
        PYTHON_CMD="python3"
    else
        echo -e "${YELLOW}   Python $PYTHON_VERSION detected - AWS AgentCore samples require Python 3.10+${NC}"
        echo "   Installing Python 3.11 for AgentCore compatibility..."

        if command -v python3.11 &> /dev/null; then
            echo "   Python 3.11 already available"
            PYTHON_CMD="python3.11"
        elif sudo yum install -y python3.11 python3.11-pip 2>/dev/null; then
            echo -e "${GREEN}   Python 3.11 installed via yum${NC}"
            PYTHON_CMD="python3.11"
        else
            echo -e "${RED}   Cannot install Python 3.11${NC}"
            echo -e "${RED}   AWS AgentCore samples require Python 3.10+${NC}"
            exit 1
        fi
    fi

    # Update virtual environment to use compatible Python version
    if [[ "$PYTHON_CMD" != "python3" ]]; then
        echo "   Recreating virtual environment with $PYTHON_CMD..."
        rm -rf "${PROJECT_DIR}/.venv"
        if $PYTHON_CMD -m venv "${PROJECT_DIR}/.venv"; then
            echo -e "${GREEN}   Virtual environment recreated with compatible Python${NC}"
        else
            echo -e "${RED}   Failed to create virtual environment with $PYTHON_CMD${NC}"
            exit 1
        fi

        source "${PROJECT_DIR}/.venv/bin/activate"
        pip install --upgrade pip > /dev/null 2>&1
    fi

    # Install bedrock-agentcore
    echo "   Checking bedrock-agentcore SDK..."
    if python3 -c "import bedrock_agentcore" 2>/dev/null; then
        echo -e "${GREEN}   bedrock-agentcore SDK already installed (skipping)${NC}"
    else
        echo "   Installing bedrock-agentcore SDK with $PYTHON_CMD..."
        if pip install "bedrock-agentcore>=0.1.1" --quiet; then
            echo -e "${GREEN}   bedrock-agentcore SDK installed${NC}"
        else
            echo -e "${RED}   Failed to install bedrock-agentcore SDK${NC}"
            exit 1
        fi
    fi

    # Install requirements.txt
    echo "   Installing requirements from requirements.txt..."

    REQUIREMENTS_FILE="${PROJECT_DIR}/requirements.txt"
    if [[ -f "$REQUIREMENTS_FILE" ]]; then
        while IFS= read -r line; do
            if [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]]; then
                continue
            fi

            if [[ "$line" == "bedrock-agentcore>=0.1.1" ]]; then
                echo "     Skipping bedrock-agentcore (already installed)"
                continue
            fi

            if [[ "$line" == "bedrock-agentcore-starter-toolkit" ]]; then
                echo "     Installing REQUIRED: $line"
                if pip install "$line" --quiet 2>/dev/null; then
                    echo "     Installed: $line"
                    continue
                else
                    echo -e "${RED}     Failed to install bedrock-agentcore-starter-toolkit${NC}"
                    exit 1
                fi
            fi

            if [[ "$line" =~ ^strands-agents ]]; then
                echo "     Installing strands package: $line"
                if pip install "$line" --quiet 2>/dev/null; then
                    echo "     Installed: $line"
                    continue
                else
                    echo "     strands-agents not available - continuing without it"
                    continue
                fi
            fi

            echo "     Installing: $line"
            if pip install "$line" --quiet 2>/dev/null; then
                echo "     Installed: $line"
            else
                package_name=$(echo "$line" | cut -d'=' -f1 | cut -d'>' -f1 | cut -d'<' -f1)
                echo "     Specific version failed, trying latest: $package_name"
                if pip install "$package_name" --quiet 2>/dev/null; then
                    echo "     Installed compatible version: $package_name"
                else
                    echo "     Could not install: $line (continuing)"
                fi
            fi
        done < "$REQUIREMENTS_FILE"

        echo -e "${GREEN}Requirements.txt processing completed${NC}"
    fi

    # Install essential dependencies
    echo "   Checking essential dependencies..."

    declare -A ESSENTIAL_DEPS=(
        ["pyyaml>=6.0"]="yaml"
        ["boto3>=1.34.0"]="boto3"
        ["requests>=2.31.0"]="requests"
        ["jinja2>=3.1.0"]="jinja2"
    )

    for dep in "${!ESSENTIAL_DEPS[@]}"; do
        import_name="${ESSENTIAL_DEPS[$dep]}"
        if python3 -c "import ${import_name}" 2>/dev/null; then
            echo "     ${dep} already installed (skipping)"
        else
            echo "     Installing essential: $dep"
            if pip install "$dep" --quiet; then
                echo "     Installed: $dep"
            else
                echo -e "${RED}   Failed to install essential dependency: $dep${NC}"
                exit 1
            fi
        fi
    done

    return 0
}

# Function to check AWS credentials
check_aws_credentials() {
    echo -e "${BLUE}Checking AWS credentials...${NC}"

    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}AWS credentials not configured or invalid${NC}"
        echo "   Please configure AWS credentials using:"
        echo "   - aws configure"
        echo "   - aws sso login (if using SSO)"
        return 1
    fi

    local caller_identity=$(aws sts get-caller-identity 2>/dev/null)
    local current_account=$(echo "$caller_identity" | grep -o '"Account": "[^"]*"' | cut -d'"' -f4)

    echo -e "${GREEN}AWS credentials valid for account: $current_account${NC}"
    return 0
}

# Main execution
main() {
    echo -e "${BLUE}Checking dependencies...${NC}"

    local deps_ok=true

    if command_exists aws; then
        echo -e "${GREEN}AWS CLI is available${NC}"
    else
        echo -e "${RED}AWS CLI is not installed${NC}"
        deps_ok=false
    fi

    if command_exists python3; then
        echo -e "${GREEN}Python 3 is available${NC}"
    else
        echo -e "${RED}Python 3 is not installed${NC}"
        deps_ok=false
    fi

    if [[ "$deps_ok" != true ]]; then
        echo -e "${RED}Missing required dependencies${NC}"
        exit 1
    fi

    echo ""

    setup_python_environment || exit 1

    echo ""

    check_aws_credentials || exit 1

    echo ""
    echo -e "${GREEN}Dependencies setup completed!${NC}"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo "   1. Deploy EKS MCP Server: cd prerequisite/eks-mcp-server && ./deploy-eks-mcp-server.sh"
    echo "   2. Create gateway: python3 scripts/agentcore_gateway.py create --name k8s-gateway"
    echo "   3. Deploy K8s Agent runtime: python3 scripts/agentcore_agent_runtime.py create --name k8s_agent_runtime"
    echo ""
    echo -e "${GREEN}Setup complete! You can now run the K8s Agent deployment scripts.${NC}"
}

# Run main function
main "$@"
