#!/bin/bash

# deploy-postprovision.sh
# Script to run the a2a connectivity agent post-provisioning deployment scripts
# Author: Auto-generated deployment script
# Date: $(date)

set -e  # Exit on any error
set -u  # Exit on undefined variables

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✓${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ✗${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠${NC} $1"
}

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Define the scripts to run in sequence
SCRIPTS=(
    "03-connect-service-to-alb.sh"
)

# Function to run a script with error handling
run_script() {
    local script_name="$1"
    local script_path="$SCRIPT_DIR/$script_name"
    
    log "Starting execution of: $script_name"
    
    # Check if script exists
    if [[ ! -f "$script_path" ]]; then
        log_error "Script not found: $script_path"
        return 1
    fi
    
    # Check if script is executable
    if [[ ! -x "$script_path" ]]; then
        log_warning "Making script executable: $script_name"
        chmod +x "$script_path"
    fi
    
    # Execute the script
    if "$script_path"; then
        log_success "Successfully completed: $script_name"
        return 0
    else
        log_error "Failed to execute: $script_name"
        return 1
    fi
}

# Main execution
main() {
    log "Starting A2A Connectivity Agent Post-provisioning Deployment"
    log "Running scripts in sequence from: $SCRIPT_DIR"
    echo
    
    local failed_scripts=()
    local success_count=0
    
    # Run each script in sequence
    for script in "${SCRIPTS[@]}"; do
        echo -e "${BLUE}===========================================${NC}"
        if run_script "$script"; then
            ((success_count++))
        else
            failed_scripts+=("$script")
            log_error "Stopping deployment due to failure in: $script"
            break
        fi
        echo
    done
    
    # Summary
    echo -e "${BLUE}===========================================${NC}"
    log "Deployment Summary:"
    log "Total scripts: ${#SCRIPTS[@]}"
    log "Successfully executed: $success_count"
    log "Failed: ${#failed_scripts[@]}"
    
    if [[ ${#failed_scripts[@]} -eq 0 ]]; then
        log_success "All deployment scripts completed successfully!"
        return 0
    else
        log_error "The following scripts failed:"
        for failed in "${failed_scripts[@]}"; do
            echo -e "  ${RED}• $failed${NC}"
        done
        return 1
    fi
}

# Trap to handle script interruption
trap 'log_error "Deployment interrupted by user"; exit 130' INT TERM

# Run main function
main "$@"
