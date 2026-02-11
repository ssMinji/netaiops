#!/bin/bash

# NetAIOps EKS Sample Workload Deployment Script
# Deploys the AWS retail-store-sample-app to an EKS cluster for Module 5 K8s diagnostics

set -euo pipefail

# Configuration
export AWS_PROFILE=netaiops-deploy
export AWS_REGION=us-west-2
CLUSTER_NAME="netaiops-eks-cluster"
RETAIL_STORE_MANIFEST="https://github.com/aws-containers/retail-store-sample-app/releases/latest/download/kubernetes.yaml"

# Get script directory for relative path resolution
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_CONFIG="${SCRIPT_DIR}/cluster-config.yaml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    local missing=0

    if ! command -v eksctl &> /dev/null; then
        log_error "eksctl is not installed. Install from: https://eksctl.io/"
        missing=1
    fi

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed. Install from: https://kubernetes.io/docs/tasks/tools/"
        missing=1
    fi

    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Install from: https://aws.amazon.com/cli/"
        missing=1
    fi

    if [ $missing -eq 1 ]; then
        log_error "Missing required tools. Please install them and try again."
        exit 1
    fi

    # Check AWS profile
    if ! aws configure list-profiles | grep -q "^${AWS_PROFILE}$"; then
        log_error "AWS profile '${AWS_PROFILE}' not found. Please configure it first."
        exit 1
    fi

    # Check cluster config exists
    if [ ! -f "${CLUSTER_CONFIG}" ]; then
        log_error "Cluster config not found at: ${CLUSTER_CONFIG}"
        exit 1
    fi

    log_info "All prerequisites satisfied."
}

# Create EKS cluster
create_cluster() {
    log_info "Creating EKS cluster '${CLUSTER_NAME}'..."
    log_info "This will take approximately 15-20 minutes..."

    check_prerequisites

    eksctl create cluster -f "${CLUSTER_CONFIG}"

    log_info "EKS cluster created successfully."
    log_info "Updating kubeconfig..."

    aws eks update-kubeconfig --name "${CLUSTER_NAME}" --region "${AWS_REGION}"

    log_info "Cluster is ready!"
}

# Deploy retail store application
deploy_app() {
    log_info "Deploying retail-store-sample-app..."

    # Apply the manifest
    kubectl apply -f "${RETAIL_STORE_MANIFEST}"

    log_info "Waiting for deployments to be ready..."

    # Wait for all deployments in the default namespace to be available
    kubectl wait --for=condition=available --timeout=300s deployment --all -n default

    log_info "All deployments are ready."
    log_info "Waiting for UI service LoadBalancer to be provisioned..."

    # Wait for the UI service LoadBalancer to get an external IP
    local attempts=0
    local max_attempts=60
    local ui_url=""

    while [ $attempts -lt $max_attempts ]; do
        ui_url=$(kubectl get svc ui -n default -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")

        if [ -n "$ui_url" ]; then
            log_info "Application deployed successfully!"
            echo ""
            log_info "Access the Retail Store UI at: http://${ui_url}"
            echo ""
            return 0
        fi

        sleep 5
        attempts=$((attempts + 1))
    done

    log_warn "LoadBalancer provisioning is taking longer than expected."
    log_info "Run './deploy-eks-workload.sh status' to check the UI service URL later."
}

# Show cluster and application status
status() {
    log_info "Cluster information:"
    eksctl get cluster --name "${CLUSTER_NAME}" --region "${AWS_REGION}" || log_warn "Cluster not found or not accessible."

    echo ""
    log_info "All pods:"
    kubectl get pods --all-namespaces

    echo ""
    log_info "All services:"
    kubectl get svc --all-namespaces

    echo ""
    log_info "Retail Store UI Service:"
    local ui_url=$(kubectl get svc ui -n default -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")

    if [ -n "$ui_url" ]; then
        echo -e "${GREEN}UI URL: http://${ui_url}${NC}"
    else
        log_warn "UI LoadBalancer not yet provisioned or service not found."
    fi
}

# Delete retail store application
delete_app() {
    log_info "Deleting retail-store-sample-app..."

    kubectl delete -f "${RETAIL_STORE_MANIFEST}" || log_warn "Application resources may not exist or already deleted."

    log_info "Application deleted."
}

# Delete EKS cluster
delete_cluster() {
    log_info "Deleting EKS cluster '${CLUSTER_NAME}'..."
    log_warn "This will delete all resources associated with the cluster."

    eksctl delete cluster --name "${CLUSTER_NAME}" --region "${AWS_REGION}" --wait

    log_info "Cluster deleted successfully."
}

# Deploy everything (cluster + app)
deploy_all() {
    log_info "Starting full deployment: cluster + application..."

    create_cluster
    echo ""
    deploy_app

    echo ""
    log_info "Full deployment complete!"
}

# Delete everything (app + cluster)
delete_all() {
    log_info "Starting full cleanup: application + cluster..."

    delete_app
    echo ""
    delete_cluster

    echo ""
    log_info "Full cleanup complete!"
}

# Show usage
usage() {
    cat << EOF
NetAIOps EKS Sample Workload Deployment Script

Usage: $0 <command>

Commands:
    create-cluster    Create the EKS cluster (takes ~15-20 minutes)
    deploy-app        Deploy the retail-store-sample-app
    status            Show cluster and application status
    delete-app        Delete the retail-store-sample-app
    delete-cluster    Delete the EKS cluster
    deploy-all        Create cluster and deploy application
    delete-all        Delete application and cluster
    help              Show this help message

Examples:
    $0 deploy-all     # Full deployment
    $0 status         # Check status
    $0 delete-all     # Full cleanup

EOF
}

# Main script logic
main() {
    if [ $# -eq 0 ]; then
        usage
        exit 1
    fi

    case "$1" in
        create-cluster)
            create_cluster
            ;;
        deploy-app)
            deploy_app
            ;;
        status)
            status
            ;;
        delete-app)
            delete_app
            ;;
        delete-cluster)
            delete_cluster
            ;;
        deploy-all)
            deploy_all
            ;;
        delete-all)
            delete_all
            ;;
        help|--help|-h)
            usage
            ;;
        *)
            log_error "Unknown command: $1"
            echo ""
            usage
            exit 1
            ;;
    esac
}

main "$@"
