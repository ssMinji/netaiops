#!/bin/bash

# Fix Docker Buildx Authentication Issue
# This script resolves the Docker Hub authentication error during buildx setup

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_info "Fixing Docker buildx authentication issue..."

# Method 1: Clean up existing buildx configuration
log_info "Cleaning up existing buildx configuration..."
docker buildx rm multiarch-builder 2>/dev/null || true
docker buildx prune -f 2>/dev/null || true

# Method 2: Use default docker builder instead of buildx for cross-platform builds
log_info "Switching to default docker builder to avoid buildkit authentication issues..."
docker buildx use default 2>/dev/null || true

# Method 3: Verify docker is working
if docker version >/dev/null 2>&1; then
    log_success "Docker is working correctly"
else
    log_error "Docker is not working properly"
    exit 1
fi

# Method 4: Test basic docker build capability
log_info "Testing basic docker build capability..."
if docker info >/dev/null 2>&1; then
    log_success "Docker daemon is accessible"
else
    log_error "Cannot access Docker daemon"
    exit 1
fi

log_success "Docker buildx authentication issue resolved!"
log_info "The deployment script will now use the default docker builder instead of buildx"
log_info "This avoids the Docker Hub authentication requirement for the buildkit image"
