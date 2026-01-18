#!/bin/bash

# Fix Docker Hub Authentication Issue for A2A Connectivity Agent
# This script automatically applies the ECR Public Gallery base image fix

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

log_info "=== Docker Hub Authentication Fix for A2A Connectivity Agent ==="
log_info "Automatically applying ECR Public Gallery base image fix..."
echo ""

# Function to apply ECR Public Gallery base image fix
fix_with_ecr_public() {
    log_info "Applying ECR Public Gallery base image fix..."
    
    # Find all Dockerfiles in the current directory and subdirectories
    DOCKERFILES=$(find . -name "Dockerfile" -type f 2>/dev/null)
    
    if [ -z "$DOCKERFILES" ]; then
        log_error "No Dockerfile found in current directory or subdirectories"
        exit 1
    fi
    
    for dockerfile in $DOCKERFILES; do
        log_info "Processing: $dockerfile"
        
        # Create backup of original Dockerfile if it doesn't exist
        if [ ! -f "${dockerfile}.backup" ]; then
            cp "$dockerfile" "${dockerfile}.backup"
            log_info "Created backup: ${dockerfile}.backup"
        fi
        
        # Check if the file contains the Docker Hub python image
        if grep -q "FROM.*python:3.11-slim" "$dockerfile"; then
            # Replace Docker Hub image with ECR Public Gallery equivalent
            sed -i.tmp 's|FROM --platform=linux/amd64 python:3.11-slim|FROM --platform=linux/amd64 public.ecr.aws/docker/library/python:3.11-slim|g' "$dockerfile"
            sed -i.tmp 's|FROM python:3.11-slim|FROM --platform=linux/amd64 public.ecr.aws/docker/library/python:3.11-slim|g' "$dockerfile"
            rm -f "${dockerfile}.tmp"
            
            log_success "Updated $dockerfile to use ECR Public Gallery base image"
            log_info "Changed: python:3.11-slim -> public.ecr.aws/docker/library/python:3.11-slim"
        else
            log_info "No python:3.11-slim base image found in $dockerfile, skipping..."
        fi
    done
}

# Function to fix Docker buildx configuration
fix_docker_buildx() {
    log_info "Fixing Docker buildx configuration..."
    
    # Clean up existing buildx configuration
    docker buildx rm multiarch-builder 2>/dev/null || true
    docker buildx prune -f 2>/dev/null || true
    
    # Use default docker builder
    docker buildx use default 2>/dev/null || true
    
    log_success "Docker buildx configuration fixed"
}

# Apply the fixes
fix_with_ecr_public
fix_docker_buildx

echo ""
log_success "Docker Hub authentication fix completed!"
echo ""
log_info "=== What was fixed ==="
log_info "1. ✓ Updated Dockerfile(s) to use ECR Public Gallery base image"
log_info "2. ✓ Fixed Docker buildx configuration"
echo ""
log_info "=== Next Steps ==="
log_info "You can now re-run your deployment script:"
log_info "   ./deploy-to-ecs.sh"
echo ""
log_info "If you need to restore the original Dockerfile:"
log_info "   cp Dockerfile.backup Dockerfile"
echo ""
log_info "The ECR Public Gallery provides the same images as Docker Hub"
log_info "but without authentication requirements or rate limits."
