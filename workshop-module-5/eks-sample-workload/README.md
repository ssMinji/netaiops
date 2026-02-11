# EKS Sample Workload - Retail Store

This directory contains the infrastructure and deployment scripts for the AWS retail-store-sample-app, a microservices-based e-commerce application deployed on Amazon EKS. This workload serves as a target for the Module 5 Kubernetes Diagnostics Agent.

## Description

The retail-store-sample-app is a complete microservices application that demonstrates a typical cloud-native architecture with multiple services, databases, and message queues. It provides a realistic workload for testing Kubernetes monitoring and diagnostics capabilities.

## Architecture

The application consists of 5 microservices:

```
┌─────────────────────────────────────────────────────────┐
│                    LoadBalancer (UI)                    │
└────────────────────────┬────────────────────────────────┘
                         │
            ┌────────────▼───────────┐
            │    UI Service          │  (Web Frontend)
            │    Port: 80            │
            └────────────┬───────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
┌───────▼──────┐  ┌──────▼─────┐  ┌──────▼─────┐
│   Catalog    │  │   Cart     │  │   Orders   │
│   Service    │  │   Service  │  │   Service  │
└───────┬──────┘  └──────┬─────┘  └──────┬─────┘
        │                │                │
        │                │                │
┌───────▼──────┐  ┌──────▼─────┐  ┌──────▼─────┐
│  Catalog DB  │  │  Cart DB   │  │ Orders DB  │
│  (MySQL)     │  │ (DynamoDB) │  │  (MySQL)   │
└──────────────┘  └────────────┘  └────────────┘
                         │
                  ┌──────▼─────┐
                  │  Checkout  │
                  │  Service   │
                  └────────────┘
```

**Services:**
- **UI**: Web frontend (Next.js) that users interact with
- **Catalog**: Product catalog management service
- **Cart**: Shopping cart management service
- **Orders**: Order processing and history service
- **Checkout**: Checkout and payment processing service

## Prerequisites

Ensure you have the following tools installed:

- **eksctl** - EKS cluster management tool ([installation guide](https://eksctl.io/))
- **kubectl** - Kubernetes CLI ([installation guide](https://kubernetes.io/docs/tasks/tools/))
- **AWS CLI** - AWS command-line interface ([installation guide](https://aws.amazon.com/cli/))
- **AWS Profile** - Configure the `netaiops-deploy` profile with appropriate credentials

Verify installations:
```bash
eksctl version
kubectl version --client
aws --version
aws configure list-profiles | grep netaiops-deploy
```

## Quick Start

### Deploy Everything

Create the EKS cluster and deploy the application:
```bash
./deploy-eks-workload.sh deploy-all
```

This will:
1. Create an EKS cluster named `netaiops-eks-cluster` (takes ~15-20 minutes)
2. Deploy the retail-store-sample-app with all microservices
3. Display the UI LoadBalancer URL when ready

### Check Status

View cluster and application status:
```bash
./deploy-eks-workload.sh status
```

This shows:
- Cluster information
- All running pods
- All services
- UI LoadBalancer URL (if provisioned)

### Access the Application

Once deployed, access the Retail Store UI via the LoadBalancer URL displayed in the output:
```
http://<load-balancer-dns>
```

### Delete Everything

Remove the application and delete the cluster:
```bash
./deploy-eks-workload.sh delete-all
```

This will:
1. Delete the retail-store-sample-app resources
2. Delete the EKS cluster and all associated resources

## Available Commands

```bash
./deploy-eks-workload.sh <command>
```

**Commands:**
- `create-cluster` - Create only the EKS cluster
- `deploy-app` - Deploy only the application (cluster must exist)
- `status` - Show cluster and application status
- `delete-app` - Delete only the application
- `delete-cluster` - Delete only the cluster
- `deploy-all` - Full deployment (cluster + application)
- `delete-all` - Full cleanup (application + cluster)
- `help` - Show usage information

## Cluster Configuration

The EKS cluster is configured with:
- **Cluster Name**: netaiops-eks-cluster
- **Region**: us-west-2
- **Kubernetes Version**: 1.31
- **Node Group**: 2-3 m5.large instances (30GB each)
- **Observability**: CloudWatch Container Insights enabled
- **Logging**: All control plane logs enabled
- **IAM**: OIDC provider enabled for service accounts

Configuration is defined in `cluster-config.yaml`.

## Cleanup Instructions

Always clean up resources when finished to avoid unnecessary AWS charges:

1. Delete the application first:
   ```bash
   ./deploy-eks-workload.sh delete-app
   ```

2. Delete the EKS cluster:
   ```bash
   ./deploy-eks-workload.sh delete-cluster
   ```

Or use the combined command:
```bash
./deploy-eks-workload.sh delete-all
```

Verify cleanup in AWS Console:
- EKS clusters deleted
- EC2 instances terminated
- Load Balancers removed
- CloudFormation stacks deleted

## Module 5 Integration

This workload is specifically designed for the Module 5 Kubernetes Diagnostics Agent workshop. The agent will:
- Connect to this EKS cluster
- Monitor pod health and performance
- Analyze container logs
- Detect anomalies and issues
- Provide diagnostics and recommendations

See the Module 5 workshop documentation for details on integrating the diagnostics agent with this workload.

## Troubleshooting

**Cluster creation fails:**
- Check AWS credentials and permissions
- Verify the `netaiops-deploy` profile is configured
- Ensure sufficient service quotas in us-west-2

**Application pods not starting:**
- Run `kubectl describe pod <pod-name>` for details
- Check `kubectl get events` for error messages
- Verify node capacity with `kubectl top nodes`

**LoadBalancer URL not available:**
- Wait a few minutes for AWS to provision the LoadBalancer
- Run `./deploy-eks-workload.sh status` to check again
- Verify security groups allow HTTP traffic

**Cost concerns:**
- EKS cluster costs ~$0.10/hour
- m5.large instances cost ~$0.10/hour each (2 nodes)
- Total estimated cost: ~$0.30/hour
- Always delete resources when not in use
