#!/bin/bash

# Docker Setup Script for Module-4 Evaluation Framework
# This script builds and runs the Docker container to execute setup_aws_prerequisites.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

IMAGE_NAME="agentcore-evaluation-setup"
IMAGE_TAG="latest"
CONTAINER_NAME="agentcore-setup-$(date +%s)"

echo -e "${BLUE}🐳 AgentCore Evaluation Framework - Docker Setup${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    echo -e "${YELLOW}Visit: https://docs.docker.com/get-docker/${NC}"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker daemon is not running. Please start Docker.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker is installed and running${NC}"
echo ""

# Build Docker image
echo -e "${YELLOW}Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}${NC}"
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Docker image built successfully${NC}"
else
    echo -e "${RED}❌ Failed to build Docker image${NC}"
    exit 1
fi
echo ""

# Check if AWS credentials are available
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo -e "${YELLOW}⚠️  AWS credentials not found in environment variables${NC}"
    echo -e "${YELLOW}The container will try to use your AWS credentials from ~/.aws${NC}"
    
    if [ ! -d "$HOME/.aws" ]; then
        echo -e "${RED}❌ No AWS credentials found. Please configure AWS CLI first.${NC}"
        echo -e "${YELLOW}Run: aws configure${NC}"
        exit 1
    fi
    
    MOUNT_AWS_CREDS="-v $HOME/.aws:/home/evaluation_user/.aws:ro"
else
    echo -e "${GREEN}✅ Using AWS credentials from environment variables${NC}"
    MOUNT_AWS_CREDS="-e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY"
    
    if [ -n "$AWS_SESSION_TOKEN" ]; then
        MOUNT_AWS_CREDS="$MOUNT_AWS_CREDS -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN"
    fi
fi
echo ""

# Set AWS region
AWS_REGION=${AWS_DEFAULT_REGION:-us-east-1}
echo -e "${BLUE}Using AWS Region: ${AWS_REGION}${NC}"
echo ""

# Run the container
echo -e "${YELLOW}Running setup in Docker container...${NC}"
echo -e "${BLUE}Container name: ${CONTAINER_NAME}${NC}"
echo ""

docker run --rm \
    --name ${CONTAINER_NAME} \
    ${MOUNT_AWS_CREDS} \
    -e AWS_DEFAULT_REGION=${AWS_REGION} \
    -e AWS_REGION=${AWS_REGION} \
    -v "$(pwd):/app" \
    ${IMAGE_NAME}:${IMAGE_TAG} \
    bash -c "cd /app && ./scripts/setup_aws_prerequisites.sh"

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Setup completed successfully in Docker container!${NC}"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo -e "1. The .env file has been created in your module-4 directory"
    echo -e "2. Review the configuration in .env"
    echo -e "3. Run evaluations using Docker:"
    echo -e "   ${YELLOW}docker run --rm -v \$(pwd):/app ${MOUNT_AWS_CREDS} -e AWS_DEFAULT_REGION=${AWS_REGION} ${IMAGE_NAME}:${IMAGE_TAG} ./scripts/run_evaluation.sh --safety-only${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}❌ Setup failed in Docker container${NC}"
    exit 1
fi
