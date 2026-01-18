# ACME Image Gallery - Sample Application Infrastructure

This CloudFormation template deploys a comprehensive 3-tier web application architecture for an image sharing platform called "ACME.com Image Gallery". The infrastructure is designed to demonstrate network performance monitoring, troubleshooting, and agentic AI capabilities for NetOps scenarios.

## Architecture Overview

### High-Level Architecture
The application implements a modern serverless web architecture with the following components:

- **Frontend**: React-based single-page application served via Lambda
- **Backend**: Three separate Lambda functions handling different concerns
- **Database**: RDS MySQL instance for metadata storage
- **Storage**: S3 bucket for image assets
- **Networking**: Multi-VPC setup with Transit Gateway connectivity
- **Load Balancing**: Application Load Balancer with path-based routing
- **Monitoring**: CloudWatch integration and reporting server

### Network Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Cloud                               │
├─────────────────────────────────────────────────────────────────┤
│  App VPC (10.2.0.0/16)          Transit Gateway               │
│  ┌─────────────────────────┐           │                      │
│  │ Public Subnets          │           │                      │
│  │ - ALB                   │           │                      │
│  │ - NAT Gateway           │           │                      │
│  └─────────────────────────┘           │                      │
│  ┌─────────────────────────┐           │                      │
│  │ Private Subnets         │           │                      │
│  │ - Lambda Functions      │◄──────────┤                      │
│  │ - RDS Database          │           │                      │
│  │ - Bastion Host          │           │                      │
│  └─────────────────────────┘           │                      │
│                                        │                      │
│  Reporting VPC (10.1.0.0/16)          │                      │
│  ┌─────────────────────────┐           │                      │
│  │ Private Subnet          │           │                      │
│  │ - Reporting Server      │◄──────────┘                      │
│  │ - VPC Endpoints         │                                  │
│  └─────────────────────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Application Architecture
```
Internet → ALB → Lambda Functions → RDS/S3
                     │
                     ├─ HTML Renderer (/) → Database reads
                     ├─ Image Processor (/images/*) → S3 access
                     └─ User Interactions (/api/track/*) → Database writes
```

## Components

### Core Infrastructure

#### VPCs and Networking
- **App VPC (10.2.0.0/16)**: Main application environment
  - 2 Public subnets for ALB and NAT Gateway
  - 2 Private subnets for Lambda functions and RDS
- **Reporting VPC (10.1.0.0/16)**: Isolated reporting environment
  - 1 Public subnet for internet access
  - 1 Private subnet for reporting server
- **Transit Gateway**: Connects both VPCs for cross-VPC communication
- **Route 53 Private Hosted Zone**: Internal DNS resolution for acme.com

#### Compute Resources
- **3 Lambda Functions**:
  - `sample-app-html-renderer`: Serves web UI and handles API requests
  - `sample-app-image-processor`: Serves static images from S3
  - `sample-app-user-interactions`: Tracks user engagement metrics
- **Bastion Host**: EC2 instance in App VPC for troubleshooting access
- **Reporting Server**: EC2 instance in Reporting VPC for analytics

#### Storage and Database
- **RDS MySQL**: Stores image metadata, user interactions, and workshop progress
- **S3 Bucket**: Stores image files with proper CORS configuration
- **Lambda Layers**: PyMySQL library for database connectivity

#### Database Schema

The application uses a MySQL database (`image_metadata`) with the following tables:

**Images Table (`images`)**
```sql
CREATE TABLE images (
    id INT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    image_url VARCHAR(500) NOT NULL,
    width INT,
    height INT,
    likes_count INT DEFAULT 0,
    shares_count INT DEFAULT 0,
    views_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

**Image Interactions Table (`image_interactions`)**
```sql
CREATE TABLE image_interactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_id INT NOT NULL,
    action ENUM('like', 'share', 'view') NOT NULL,
    session_id VARCHAR(255),
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (image_id) REFERENCES images(id)
);
```

**SEV1 Correspondence History Table (`sev1_correspondence_history`)**
```sql
CREATE TABLE sev1_correspondence_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id VARCHAR(50) NOT NULL,
    correspondence_id INT NOT NULL,
    author VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    message_type ENUM('system', 'user', 'agent') DEFAULT 'user',
    module_name VARCHAR(100),
    module_progress_before INT DEFAULT 0,
    module_progress_after INT DEFAULT 0,
    module_completed BOOLEAN DEFAULT FALSE,
    session_id VARCHAR(255),
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_ticket_id (ticket_id),
    INDEX idx_correspondence_id (correspondence_id),
    INDEX idx_created_at (created_at),
    INDEX idx_module_completed (module_completed)
);
```

**Workshop Modules Table (`workshop_modules`)**
```sql
CREATE TABLE workshop_modules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    module_name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL,
    current_progress INT DEFAULT 0,
    max_progress INT DEFAULT 100,
    is_completed BOOLEAN DEFAULT FALSE,
    completion_date TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_module_name (module_name),
    INDEX idx_is_completed (is_completed)
);
```

**Initial Data**

The database is populated with initial data including:

- **Images**: 6 re:Invent conference images (2020-2025) with metadata
- **Workshop Modules**: 4 modules for tracking workshop progress:
  - AgentCore Runtime
  - AgentCore Memory  
  - A2A (Agent-to-Agent)
  - CloudWatch Investigations

**Database Relationships**
- `image_interactions.image_id` → `images.id` (Foreign Key)
- `sev1_correspondence_history` tracks workshop progress through module completion
- `workshop_modules` maintains current progress state for each workshop module

#### Load Balancing and Routing
- **Application Load Balancer**: Routes traffic based on path patterns
  - `/` → HTML Renderer
  - `/images/*` → Image Processor  
  - `/api/track/*` → User Interactions
  - `/api/correspondence` → HTML Renderer
  - `/api/workshop-progress` → HTML Renderer

### Security Features
- **Security Groups**: Properly configured ingress/egress rules
- **VPC Endpoints**: Secure access to AWS services from Reporting VPC
- **IAM Roles**: Least-privilege access for all components
- **Database Security**: Private subnets with restricted access

## Prerequisites

Before deploying this template, ensure you have:

1. **AWS CLI configured** with appropriate permissions
2. **CloudFormation deployment permissions** including:
   - VPC, EC2, RDS, Lambda, S3, Route53, CloudWatch access
   - IAM role creation permissions
3. **Available resources in target region**:
   - At least 2 Availability Zones
   - Available Elastic IP addresses
   - RDS subnet group capacity

## Parameters

The template accepts the following parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `DBUsername` | String | `admin` | Database administrator username |
| `DBPassword` | String | `SapConcurWorkshop25` | Database administrator password (8+ chars) |

## Deployment Instructions

### Method 1: AWS Console
1. Navigate to CloudFormation in AWS Console
2. Click "Create Stack" → "With new resources"
3. Upload the `sample-app.yaml` file
4. Provide stack name and parameters
5. Review and create stack

### Method 2: AWS CLI
```bash
aws cloudformation create-stack \
  --stack-name acme-image-gallery \
  --template-body file://sample-app.yaml \
  --parameters ParameterKey=DBUsername,ParameterValue=admin \
               ParameterKey=DBPassword,ParameterValue=YourSecurePassword123 \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

### Method 3: Using AWS CDK/SAM
The template is compatible with AWS SAM and CDK deployment workflows.

## Post-Deployment Access

### Application Access
After deployment, access the application via the ALB DNS name:
```
http://<ALB-DNS-NAME>
```

The application provides:
- **Gallery Tab**: Image browsing with like/share functionality
- **Support Tickets Tab**: Ticketing system with workshop progress tracking

### Infrastructure Access
- **Bastion Host**: Access via Session Manager (no SSH keys required)
- **Database**: Connect through bastion host using provided credentials
- **Reporting Server**: Access via Session Manager from Reporting VPC

### DNS Resolution
Internal DNS records are automatically created:
- `database.acme.com` → RDS endpoint
- `reporting.acme.com` → Reporting server IP
- `bastion.acme.com` → Bastion host IP

## Features

### Image Gallery
- Responsive web interface for image browsing
- Real-time like/share tracking
- Image metadata management
- S3-based image serving with caching

### Support Ticket System
- SEV1 ticket simulation for troubleshooting scenarios
- Correspondence tracking with database persistence  
- Workshop progress monitoring
- Resource impact tracking

### Performance Monitoring
- CloudWatch metrics integration
- Real-time reporting dashboard
- Database performance tracking
- Network flow monitoring capabilities

### Workshop Integration
- Progress tracking for NetOps workshop modules:
  - AgentCore Runtime
  - AgentCore Memory
  - A2A (Agent-to-Agent)
  - CloudWatch Investigations
- Interactive correspondence system
- Automated progress updates

## Troubleshooting

### Common Issues

#### Lambda Functions Not Responding
- Check VPC configuration and security groups
- Verify Lambda has internet access through NAT Gateway
- Review CloudWatch logs for function-specific errors

#### Database Connection Issues
- Verify security group allows Lambda access to RDS
- Check database endpoint resolution
- Validate credentials and database initialization

#### Image Loading Problems  
- Confirm S3 bucket policy allows Lambda access
- Check CORS configuration on S3 bucket
- Verify image upload process completed successfully

#### Cross-VPC Communication Issues
- Validate Transit Gateway attachment states
- Check route table configurations
- Verify security group cross-references

### Monitoring and Logs
- **Lambda Logs**: Available in CloudWatch under `/aws/lambda/`
- **ALB Logs**: Can be enabled to S3 for access pattern analysis
- **VPC Flow Logs**: Enable for network troubleshooting
- **RDS Logs**: Available in RDS console for database issues

## Architecture Benefits

### Scalability
- Serverless Lambda functions auto-scale based on demand
- RDS can be scaled vertically as needed
- S3 provides virtually unlimited storage capacity

### High Availability  
- Multi-AZ deployment across 2 availability zones
- ALB provides health checking and failover
- RDS supports Multi-AZ deployments (configurable)

### Security
- Private subnets isolate backend resources
- Security groups implement defense in depth
- VPC endpoints reduce internet exposure
- IAM roles follow least-privilege principles

### Cost Optimization
- Pay-per-request Lambda pricing model
- S3 lifecycle policies (can be configured)
- RDS instance sizing appropriate for demo workloads
- Reserved capacity options available for production

## Cleanup

To remove all resources created by this template:

```bash
aws cloudformation delete-stack --stack-name acme-image-gallery
```

**Note**: Ensure S3 bucket is empty before deletion, as CloudFormation cannot delete non-empty buckets.

## Customization

### Environment-Specific Modifications
- Adjust CIDR blocks for VPC integration requirements
- Modify instance types based on performance needs  
- Update security groups for organizational policies
- Configure custom domain names and SSL certificates

### Application Enhancements
- Add CloudFront distribution for global content delivery
- Implement ElastiCache for session management
- Add SQS/SNS for asynchronous processing
- Integrate with AWS Cognito for user authentication

## Support and Maintenance

This infrastructure template is designed for:
- **Development and Testing**: Workshop scenarios and proof-of-concepts
- **Performance Analysis**: Network monitoring and troubleshooting training
- **Agentic AI Demonstrations**: NetOps automation and intelligent remediation

For production deployments, consider additional hardening:
- Enable encryption at rest for RDS and S3
- Implement AWS WAF for ALB protection
- Add AWS Config for compliance monitoring
- Configure AWS CloudTrail for audit logging

## Version History

- **v1.0**: Initial release with basic 3-tier architecture
- **v2.0**: Added workshop progress tracking and correspondence system
- **v3.0**: Enhanced monitoring and reporting capabilities
- **Current**: Integrated with AgentCore performance monitoring agent

---

**Created for AWS NetOps Agentic AI Workshop**  
Part of the AgentCore Performance Agent baseline infrastructure
