#!/bin/bash

# AgentCore Evaluation Framework - Main Evaluation Runner
# This script provides a simple interface to run evaluations and generate reports

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORTS_DIR="$PROJECT_DIR/reports"

echo -e "${BLUE}AgentCore Evaluation Framework${NC}"
echo -e "${BLUE}===================================${NC}"

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

OPTIONS:
  -a, --agent AGENT        Specific agent to evaluate (TroubleshootingAgent, PerformanceAgent, CollaboratorAgent, all)
  -s, --safety-only        Run only safety-critical test scenarios
  -r, --report             Generate HTML report after evaluation
  -o, --output FILE        Output file for results (default: auto-generated)
  --html-output FILE       HTML output file (default: auto-generated)
  --no-s3-upload           Disable S3 upload for HTML reports (uploads to bucket root by default)
  --timeout SECONDS        Timeout for evaluation (default: 300)
  --debug                  Enable debug logging
  -h, --help               Show this help message

EXAMPLES:
  $0                       # Run all evaluations with HTML report (uploads to S3)
  $0 --agent all --report # Same as above (explicit)
  $0 --safety-only         # Run only safety tests (uploads to S3)
  $0 --agent TroubleshootingAgent --debug  # Debug single agent
  $0 --report              # Generate report (uploads to S3)
  $0 --no-s3-upload        # Generate report without S3 upload

QUICK COMMANDS:
  $0 --quick               # Safety tests + HTML report + S3 upload
  $0 --full                # Complete evaluation + detailed report + S3 upload

S3 UPLOAD:
  By default, HTML reports are automatically uploaded to your S3 bucket
  agentcore-evaluation-results-{ACCOUNT_ID} in the root folder.
EOF
}

# Function to check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"
    
    # Check if we're in the right directory
    if [[ ! -f "$PROJECT_DIR/requirements.txt" ]]; then
        echo -e "${RED}ERROR: Not in correct project directory. Please run from module-4/scripts/${NC}"
        exit 1
    fi
    
    # Check Python
    if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
        echo -e "${RED}ERROR: Python not found. Please install Python 3.8+${NC}"
        exit 1
    fi
    
    # Set Python command
    PYTHON_CMD="python3"
    if ! command -v python3 &> /dev/null; then
        PYTHON_CMD="python"
    fi
    
    # Check if virtual environment is active (recommended) - silently skip warning
    # if [[ -z "$VIRTUAL_ENV" ]]; then
    #     echo -e "${YELLOW}Virtual environment not detected. Consider using 'python -m venv venv && source venv/bin/activate'${NC}"
    # fi
    
    # Check environment configuration
    if [[ -f "$PROJECT_DIR/.env" ]]; then
        echo -e "${GREEN}SUCCESS: Environment configuration found${NC}"
        # Source environment variables
        set -a
        source "$PROJECT_DIR/.env"
        set +a
    else
        echo -e "${YELLOW}WARNING: No .env file found. Run setup_aws_prerequisites.sh first for optimal configuration.${NC}"
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${YELLOW}WARNING: AWS credentials not configured or invalid${NC}"
        echo -e "${YELLOW}         Evaluations may fail without proper AWS access${NC}"
    else
        echo -e "${GREEN}SUCCESS: AWS credentials configured${NC}"
    fi
    
    echo -e "${GREEN}SUCCESS: Prerequisites check completed${NC}"
    echo ""
}

# Function to install dependencies
install_dependencies() {
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    
    cd "$PROJECT_DIR"
    
    # Try to install dependencies
    if $PYTHON_CMD -m pip install -r requirements.txt > /dev/null 2>&1; then
        echo -e "${GREEN}SUCCESS: Dependencies installed successfully${NC}"
    else
        echo -e "${YELLOW}WARNING: Some dependencies may not have installed correctly${NC}"
        echo -e "${YELLOW}         Consider running: pip install -r requirements.txt${NC}"
    fi
    echo ""
}

# Function to show agent evaluation progress
show_agent_progress() {
    local agent_name="$1"
    local runtime_arn="$2"
    
    # Agent-specific colors
    local agent_color="${BLUE}"
    case "$agent_name" in
        "TroubleshootingAgent")
            agent_color="${GREEN}"
            ;;
        "PerformanceAgent")
            agent_color="${BLUE}"
            ;;
        "HostAgent"|"CollaboratorAgent")
            agent_color="${MAGENTA}"
            ;;
    esac
    
    # Beautiful header
    echo -e "${agent_color}$(printf '=%.0s' {1..70})${NC}"
    echo -e "${agent_color}$(printf '%*s' $((35 + ${#agent_name}/2)) "EVALUATING ${agent_name^^}")${NC}"
    echo -e "${agent_color}$(printf '=%.0s' {1..70})${NC}"
    echo ""
    
    # Agent details
    echo -e "${agent_color}Agent${NC}: ${BOLD}$agent_name${NC}"
    echo -e "${CYAN}Runtime${NC}: ${runtime_arn}"
    echo ""
}

# Function to show evaluation phases with beautiful formatting
show_evaluation_phases() {
    local agent_name="$1"
    
    # Agent-specific colors
    local agent_color="${BLUE}"
    case "$agent_name" in
        "TroubleshootingAgent")
            agent_color="${GREEN}"
            ;;
        "PerformanceAgent")
            agent_color="${BLUE}"
            ;;
        "HostAgent"|"CollaboratorAgent")
            agent_color="${MAGENTA}"
            ;;
    esac
    
    echo -e "${CYAN}Phase 1: Agent Initialization${NC}"
    echo -e "  ${CYAN}Scenario${NC}: $(get_scenario_1_name "$agent_name")"
    echo -e "  ${YELLOW}Question${NC}: \"Hello, this is a test message to verify agent accessibility.\""
    echo ""
    
    echo -e "${CYAN}Phase 2: Workflow Evaluation${NC}"
    echo -e "  ${CYAN}Scenario${NC}: $(get_scenario_2_name "$agent_name")"
    show_test_questions "$agent_name"
    echo ""
    
    echo -e "${CYAN}Phase 3: LLM Judge Evaluation${NC}"
    echo -e "  ${BLUE}Analyzing response quality and accuracy${NC}"
    echo ""
}

# Function to get scenario names
get_scenario_1_name() {
    local agent_name="$1"
    case "$agent_name" in
        "TroubleshootingAgent")
            echo "Network connectivity diagnosis"
            ;;
        "PerformanceAgent")
            echo "Performance bottleneck identification"
            ;;
        "HostAgent"|"CollaboratorAgent")
            echo "Multi-agent coordination"
            ;;
        *)
            echo "Comprehensive evaluation scenario 1"
            ;;
    esac
}

get_scenario_2_name() {
    local agent_name="$1"
    case "$agent_name" in
        "TroubleshootingAgent")
            echo "VPC troubleshooting"
            ;;
        "PerformanceAgent")
            echo "Network latency analysis"
            ;;
        "HostAgent"|"CollaboratorAgent")
            echo "Task delegation"
            ;;
        *)
            echo "Comprehensive evaluation scenario 2"
            ;;
    esac
}

get_scenario_3_name() {
    local agent_name="$1"
    case "$agent_name" in
        "TroubleshootingAgent")
            echo "Security group analysis"
            ;;
        "PerformanceAgent")
            echo "Resource optimization"
            ;;
        "HostAgent"|"CollaboratorAgent")
            echo "Conflict resolution"
            ;;
        *)
            echo "Comprehensive evaluation scenario 3"
            ;;
    esac
}

# Function to show test questions for each agent
show_test_questions() {
    local agent_name="$1"
    case "$agent_name" in
        "TroubleshootingAgent")
              echo -e "  Test 1: ${YELLOW}\"Help me troubleshoot connectivity issues with my EC2 instance\"${NC}"
            echo -e "  Test 2: ${YELLOW}\"My instance cannot resolve DNS names. What should I check?\"${NC}"
            ;;
        "PerformanceAgent")
            echo -e "  Test 1: ${YELLOW}\"Analyze network performance issues in my VPC\"${NC}"
            echo -e "  Test 2: ${YELLOW}\"I'm seeing high TCP retransmissions. Can you help identify the cause?\"${NC}"
            ;;
        "HostAgent"|"CollaboratorAgent")
            echo -e "  Test 1: ${YELLOW}\"Coordinate with other agents to resolve this network issue\"${NC}"
            echo -e "  Test 2: ${YELLOW}\"Delegate performance analysis to the appropriate agent\"${NC}"
            ;;
    esac
}

# Function to show specialized testing information
show_specialized_info() {
    local agent_name="$1"
    case "$agent_name" in
        "TroubleshootingAgent")
            echo -e "  ${BLUE}Running safety feature validation${NC}"
            ;;
        "PerformanceAgent")
            echo -e "  ${BLUE}Running performance analysis validation${NC}"
            ;;
        "HostAgent"|"CollaboratorAgent")
            echo -e "  ${BLUE}Running A2A communication validation${NC}"
            ;;
    esac
}

# Function to run evaluation with real-time progress display
run_evaluation() {
    local agent="$1"
    local safety_only="$2"
    local output_file="$3"
    local timeout="$4"
    local debug="$5"
    
    echo -e "${YELLOW}Starting evaluation...${NC}"
    
    cd "$PROJECT_DIR"
    
    # Build command
    local cmd="$PYTHON_CMD scripts/run_evaluation.py"
    
    if [[ "$agent" != "all" ]]; then
        cmd="$cmd --agent $agent"
    fi
    
    if [[ "$safety_only" == "true" ]]; then
        cmd="$cmd --safety-only"
    fi
    
    if [[ -n "$output_file" ]]; then
        cmd="$cmd --output $output_file"
    fi
    
    if [[ -n "$timeout" ]]; then
        cmd="$cmd --timeout $timeout"
    fi
    
    if [[ "$debug" == "true" ]]; then
        cmd="$cmd --debug"
    fi
    
    # Add shell-friendly flag to show real-time progress
    cmd="$cmd --shell-progress"
    
    # Run evaluation with real-time output
    local exit_code=0
    if ! eval "$cmd"; then
        exit_code=$?
    fi
    
    # Don't show generic failure message - let the Python script handle its own output
    echo ""
    return $exit_code
}

# Function to generate HTML report with enhanced progress
generate_html_report() {
    local html_output="$1"
    local open_browser="$2"
    local debug="$3"
    local no_s3_upload="$4"
    local agent_filter="$5"
    
    echo -e "${YELLOW}Generating HTML report...${NC}"
    
    # Get AWS account ID for display
    local account_id=""
    if aws sts get-caller-identity &> /dev/null; then
        account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
    fi
    
    if [[ "$no_s3_upload" == "true" ]]; then
        echo -e "${YELLOW}WARNING: S3 upload disabled${NC}"
    else
        if [[ -n "$account_id" && "$account_id" != "unknown" ]]; then
            echo -e "${BLUE}S3 upload enabled - reports will be uploaded to agentcore-evaluation-results-${account_id}${NC}"
        else
            echo -e "${BLUE}S3 upload enabled - reports will be uploaded to bucket root${NC}"
        fi
    fi
    
    cd "$PROJECT_DIR"
    
    # Build command
    local cmd="$PYTHON_CMD scripts/generate_html_report.py --latest"
    
    if [[ -n "$html_output" ]]; then
        cmd="$cmd --output $html_output"
    fi
    
    # Add agent filter for individual agent reports
    if [[ -n "$agent_filter" && "$agent_filter" != "all" ]]; then
        cmd="$cmd --agent $agent_filter"
        echo -e "${CYAN}Generating individual report for: ${agent_filter}${NC}"
    fi
    
    if [[ "$open_browser" == "true" ]]; then
        cmd="$cmd --open"
    fi
    
    if [[ "$no_s3_upload" == "true" ]]; then
        cmd="$cmd --no-s3-upload"
    fi
    
    if [[ "$debug" == "true" ]]; then
        cmd="$cmd --debug"
    fi
    
    # Generate report and capture output in real-time while also logging
    local temp_log="/tmp/agentcore_report.log"
    
    # Run command and capture output while displaying it in real-time
    if eval "$cmd" 2>&1 | tee "$temp_log"; then
        
        # Extract S3 information from the output if S3 upload was enabled
        if [[ "$no_s3_upload" != "true" ]]; then
            local s3_path=$(grep "Report uploaded to S3:" "$temp_log" 2>/dev/null | sed 's/.*Report uploaded to S3: //' || echo "")
            local s3_url=$(grep "S3 URL:" "$temp_log" 2>/dev/null | sed 's/.*S3 URL: //' || echo "")
            
            # If S3 information wasn't displayed by the Python script, show it here
            if [[ -n "$s3_path" && ! $(grep -q "Report uploaded to S3:" "$temp_log" 2>/dev/null) ]]; then
                echo -e "${GREEN}Report uploaded to S3: ${s3_path}${NC}"
            fi
            if [[ -n "$s3_url" && ! $(grep -q "S3 URL:" "$temp_log" 2>/dev/null) ]]; then
                echo -e "${CYAN}S3 URL: ${s3_url}${NC}"
            fi
        fi
        
        return 0
    else
        echo -e "${RED}ERROR: HTML report generation failed${NC}"
        echo -e "${YELLOW}Error details:${NC}"
        tail -10 "$temp_log" 2>/dev/null || echo "No error details available"
        return 1
    fi
}

# Function to run quick evaluation (safety + report)
run_quick() {
    local no_s3_upload="$1"
    echo -e "${BLUE}Running Quick Evaluation (Safety Tests + HTML Report)${NC}"
    echo ""
    
    if run_evaluation "all" "true" "" "300" "false"; then
        generate_html_report "" "false" "false" "$no_s3_upload"
    fi
}

# Function to run full evaluation
run_full() {
    local no_s3_upload="$1"
    echo -e "${BLUE}Running Full Evaluation Suite${NC}"
    echo ""
    
    if run_evaluation "all" "false" "" "600" "false"; then
        generate_html_report "" "false" "false" "$no_s3_upload"
    fi
}

# Main function
main() {
    local agent="all"
    local safety_only="false"
    local generate_report="false"
    local output_file=""
    local html_output=""
    local open_browser="false"
    local no_s3_upload="false"
    local timeout="300"
    local debug="false"
    local quick="false"
    local full="false"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -a|--agent)
                agent="$2"
                shift 2
                ;;
            -s|--safety-only)
                safety_only="true"
                shift
                ;;
            -r|--report)
                generate_report="true"
                shift
                ;;
            -o|--output)
                output_file="$2"
                shift 2
                ;;
            --html-output)
                html_output="$2"
                shift 2
                ;;
            --open)
                open_browser="true"
                shift
                ;;
            --no-s3-upload)
                no_s3_upload="true"
                shift
                ;;
            --timeout)
                timeout="$2"
                shift 2
                ;;
            --debug)
                debug="true"
                shift
                ;;
            --quick)
                quick="true"
                shift
                ;;
            --full)
                full="true"
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Handle quick and full modes
    if [[ "$quick" == "true" ]]; then
        check_prerequisites
        install_dependencies
        run_quick "$no_s3_upload"
        echo -e "${GREEN}AgentCore evaluation completed successfully!${NC}"
        exit $?
    fi
    
    if [[ "$full" == "true" ]]; then
        check_prerequisites
        install_dependencies
        run_full "$no_s3_upload"
        echo -e "${GREEN}AgentCore evaluation completed successfully!${NC}"
        exit $?
    fi
    
    # Default behavior: if no specific options, behave like --full
    if [[ "$safety_only" == "false" && "$generate_report" == "false" && -z "$output_file" && "$agent" == "all" && "$timeout" == "300" && "$debug" == "false" ]]; then
        echo -e "${BLUE}No arguments provided - running full evaluation mode${NC}"
        generate_report="true"
        timeout="600"
        open_browser="false"
    fi
    
    # Validate agent parameter
    case "$agent" in
        all|TroubleshootingAgent|PerformanceAgent|HostAgent|CollaboratorAgent)
            ;;
        *)
            echo -e "${RED}Invalid agent: $agent${NC}"
            echo -e "${YELLOW}Valid options: all, TroubleshootingAgent, PerformanceAgent, CollaboratorAgent${NC}"
            exit 1
            ;;
    esac
    
    # Run setup steps
    check_prerequisites
    install_dependencies
    
    # Create reports directory
    mkdir -p "$REPORTS_DIR"
    
    # Run evaluation
    if run_evaluation "$agent" "$safety_only" "$output_file" "$timeout" "$debug"; then
        
        # Generate HTML report if requested
        if [[ "$generate_report" == "true" ]]; then
            echo -e "${YELLOW}Generating HTML report (optional)...${NC}"
            if generate_html_report "$html_output" "$open_browser" "$debug" "$no_s3_upload" "$agent"; then
                echo -e "${GREEN}SUCCESS: HTML report generated successfully${NC}"
            else
                echo -e "${YELLOW}WARNING: HTML report generation failed, but evaluation was successful${NC}"
                echo -e "${YELLOW}         You can generate the report manually later using: python scripts/generate_html_report.py --latest${NC}"
            fi
        fi
        
        echo -e "${GREEN}SUCCESS: AgentCore evaluation completed successfully!${NC}"
        
        exit 0
    else
        echo -e "${RED}ERROR: AgentCore evaluation failed${NC}"
        exit 1
    fi
}

# Handle script interruption
trap 'echo -e "\n${RED}ERROR: Evaluation interrupted. Cleaning up...${NC}"; exit 1' INT TERM

# Check for help flag first
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    show_usage
    exit 0
fi

# Run main function
main "$@"
