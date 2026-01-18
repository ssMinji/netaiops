!/bin/bash
#
# Traffic Generator Runner Script
#
# This script runs the continuous database traffic generator in background mode
# with configurable parameters.
#
# Usage:
#   ./run-traffic-generator.sh <DB_HOST>
#   ./run-traffic-generator.sh <DB_HOST> <DURATION> <WORKERS>
#
# Examples:
#   ./run-traffic-generator.sh sample-app-image-metadata-db.c2b86g0qcqy8.us-east-1.rds.amazonaws.com
#   ./run-traffic-generator.sh sample-app-image-metadata-db.c2b86g0qcqy8.us-east-1.rds.amazonaws.com 30 10
#

set -e

# Default values
DEFAULT_PASSWORD="ReInvent2025!"
DEFAULT_DURATION=60
DEFAULT_WORKERS=20
SCRIPT_NAME="continuous_database_traffic_generator-v4.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if DB_HOST parameter is provided
if [ -z "$1" ]; then
    print_error "Database host parameter is required!"
    echo ""
    echo "Usage: $0 <DB_HOST> [DURATION] [WORKERS]"
    echo ""
    echo "Parameters:"
    echo "  DB_HOST   : RDS database endpoint (required)"
    echo "  DURATION  : Duration in minutes (optional, default: ${DEFAULT_DURATION})"
    echo "  WORKERS   : Number of worker threads (optional, default: ${DEFAULT_WORKERS})"
    echo ""
    echo "Example:"
    echo "  $0 sample-app-image-metadata-db.c2b86g0qcqy8.us-east-1.rds.amazonaws.com"
    echo "  $0 sample-app-image-metadata-db.c2b86g0qcqy8.us-east-1.rds.amazonaws.com 30 10"
    exit 1
fi

# Get parameters
DB_HOST="$1"
DURATION="${2:-$DEFAULT_DURATION}"
WORKERS="${3:-$DEFAULT_WORKERS}"
DB_PASSWORD="${DB_PASSWORD:-$DEFAULT_PASSWORD}"

# Get script directory for reference
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if Python script exists (using relative path)
if [ ! -f "$(dirname "${BASH_SOURCE[0]}")/${SCRIPT_NAME}" ]; then
    print_error "Python script not found: ${SCRIPT_NAME}"
    print_error "Please ensure the script is in the same directory as run-traffic-generator.sh"
    exit 1
fi

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    print_error "python3 is not installed or not in PATH"
    exit 1
fi

# Check if MySQL client is available
if ! command -v mysql &> /dev/null; then
    print_warning "mysql client is not installed. The script may fail if it's required."
fi

print_info "Starting Traffic Generator in Background Mode"
echo "================================================"
echo "Database Host: ${DB_HOST}"
echo "Duration:      ${DURATION} minutes"
echo "Workers:       ${WORKERS}"
echo "Password:      ${DB_PASSWORD}"
echo "Script:        ${SCRIPT_NAME}"
echo "Script Dir:    ${SCRIPT_DIR}"
echo "================================================"
echo ""

# Run the Python script using relative path from script location
python3 "$(dirname "${BASH_SOURCE[0]}")/${SCRIPT_NAME}" \
  --local-mode \
  --db-host "${DB_HOST}" \
  --db-password "${DB_PASSWORD}" \
  --duration "${DURATION}" \
  --workers "${WORKERS}" \
  --background

# Check if script started successfully
if [ $? -eq 0 ]; then
    echo ""
    print_info "Traffic generator started successfully in background!"
    echo ""
    echo "Monitor progress:"
    echo "  tail -f ${SCRIPT_DIR}/continuous_traffic_generator.log"
    echo ""
    echo "Check status:"
    echo "  ps -p \$(cat ${SCRIPT_DIR}/continuous_traffic_generator.pid)"
    echo ""
    echo "Stop the process:"
    echo "  kill \$(cat ${SCRIPT_DIR}/continuous_traffic_generator.pid)"
    echo ""
    echo "Log files:"
    echo "  Output: ${SCRIPT_DIR}/continuous_traffic_generator.log"
    echo "  Errors: ${SCRIPT_DIR}/continuous_traffic_generator.err"
    echo "  PID:    ${SCRIPT_DIR}/continuous_traffic_generator.pid"
    echo ""
else
    print_error "Failed to start traffic generator"
    exit 1
fi
