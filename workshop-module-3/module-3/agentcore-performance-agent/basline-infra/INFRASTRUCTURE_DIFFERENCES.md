# Infrastructure Differences: Workshop vs Base Stack

This document outlines the key infrastructure differences between the base sample application stack and the workshop-enhanced version.

## Overview

The workshop version (`sample-app.yaml`) extends the base stack (`agent-based-network-ops-amazon-bedrock-agents-and-bedockcore/static/sample-application.yaml`) with advanced network monitoring and performance analysis capabilities, specifically designed for the AgentCore Performance Agent workshop.

---

## Major Infrastructure Additions

### 1. **Traffic Mirroring Infrastructure** ⭐ NEW

The workshop stack includes a complete traffic mirroring solution for deep packet inspection and network performance analysis.

#### Components Added:
- **Traffic Mirroring S3 Bucket** (`TrafficMirroringS3Bucket`)
  - Dedicated storage for captured network packets
  - Lifecycle policies: 30 days → Standard-IA, 90 days → Glacier, 365 days → Deep Archive
  - 7-year retention policy
  - Bucket name: `traffic-mirroring-analysis-${AWS::AccountId}`

- **Traffic Mirroring Target Instance** (`TrafficMirroringTargetInstance`)
  - Instance type: `t3.medium` (vs `t2.micro` for other instances)
  - Runs tcpdump for continuous packet capture
  - Captures stored with 15-minute rotation
  - Uses Mountpoint for Amazon S3 for efficient storage
  - Located in `AppPrivateSubnet2`

- **Packet Analysis Lambda Function** (`PacketAnalysisFunction`)
  - Runtime: Python 3.9
  - Memory: 1024 MB
  - Timeout: 300 seconds
  - Analyzes captured packets and generates performance metrics
  - Sends alerts for critical issues

- **Traffic Mirroring Security Group** (`TrafficMirroringTargetSecurityGroup`)
  - Allows VXLAN traffic (UDP 4789) from both VPCs
  - Ingress from 10.2.0.0/16 (App VPC) and 10.1.0.0/16 (Reporting VPC)

#### IAM Roles:
- `TrafficMirroringTargetInstanceRole`: Permissions for S3 access, CloudWatch metrics, and traffic mirroring management
- `PacketAnalysisLambdaRole`: Permissions for S3 access, CloudWatch metrics, and SNS publishing

#### Monitoring:
- **SNS Topic** (`TrafficMirroringAlertsTopic`): Performance alerts
- **CloudWatch Dashboard** (`TrafficMirroringDashboard`): Real-time monitoring
- **Service Health Monitoring**: Automated service status checks every 5 minutes

---

### 2. **Enhanced VPC Endpoints**

#### App VPC Endpoints (NEW):
- `AppSSMVPCEndpoint`: SSM service endpoint
- `AppSSMMessagesVPCEndpoint`: SSM messages endpoint
- `AppEC2MessagesVPCEndpoint`: EC2 messages endpoint
- `AppEC2VPCEndpoint`: EC2 service endpoint
- `AppVPCEndpointSecurityGroup`: Dedicated security group for VPC endpoints

#### Reporting VPC Endpoints (Enhanced):
- Added `PrivateDnsEnabled: true` for better DNS resolution
- Enhanced security group rules for VPC endpoint access

**Purpose**: Enable private connectivity to AWS services without internet gateway, improving security and reducing data transfer costs.

---

### 3. **CloudWatch Network Flow Monitor Integration**

#### Bastion Instance Enhancements:
- Added `CloudWatchNetworkFlowMonitorAgentPublishPolicy` managed policy
- Tag: `NetworkFlowMonitor: enabled`
- Enhanced egress rules for HTTPS to VPC endpoints

#### Reporting Server Enhancements:
- Added `CloudWatchNetworkFlowMonitorAgentPublishPolicy` managed policy
- Tag: `NetworkFlowMonitor: enabled`
- Enhanced egress rules for HTTPS to VPC endpoints

#### Traffic Mirroring Target:
- Tag: `NetworkFlowMonitor: enabled`
- Integrated with CloudWatch for flow monitoring

**Purpose**: Enable CloudWatch Network Flow Monitor for comprehensive network traffic analysis and performance monitoring.

---

### 4. **Database Configuration Changes**

#### Base Stack:
- Custom DB Parameter Group with charset compatibility settings
- Character set: `utf8` with `utf8_general_ci` collation
- Authentication: `mysql_native_password`

#### Workshop Stack:
- **Removed** custom DB Parameter Group
- Uses default MySQL 8.0 parameter group
- Simplified configuration for workshop environment

---

### 5. **Instance Type Changes**

| Component | Base Stack | Workshop Stack | Reason |
|-----------|------------|----------------|---------|
| Bastion Instance | `t2.small` | `t3.micro` | Cost optimization |
| Reporting Server | `t2.micro` | `t3.micro` | Better performance |
| Traffic Mirror Target | N/A | `t3.medium` | Packet processing needs |

---

### 6. **Security Group Enhancements**

#### Bastion Security Group:
- **Removed**: ICMP ping from Reporting VPC (10.1.0.0/16)
- **Added**: HTTPS egress to VPC endpoints (10.2.0.0/16)

#### Reporting Server Security Group:
- **Removed**: HTTP ingress from both VPCs
- **Removed**: MySQL ingress from both VPCs
- **Removed**: ICMP ping from App VPC
- **Added**: HTTPS egress to VPC endpoints (10.1.0.0/16)
- **Simplified**: Focus on SSM connectivity only

---

### 7. **Lambda Function Differences**

#### HTML Rendering Function:
**Workshop Version Additions:**
- Database tables for workshop progress tracking:
  - `sev1_correspondence_history`: Tracks ticket correspondence
  - `workshop_modules`: Tracks module completion progress
- API endpoints for correspondence and progress tracking:
  - `/api/correspondence` (GET/POST)
  - `/api/workshop-progress` (GET)
- Enhanced HTML with workshop progress widgets
- Support ticket system with correspondence functionality

**Base Version Features:**
- Support ticket API Gateway integration
- Analytics proxy endpoint for reporting server
- More comprehensive HTML with multiple tabs

#### Key Differences:
| Feature | Base Stack | Workshop Stack |
|---------|------------|----------------|
| Support Ticket API Gateway | ✅ Yes | ❌ No |
| Workshop Progress Tracking | ❌ No | ✅ Yes |
| Correspondence History | ❌ No | ✅ Yes |
| Analytics Proxy | ✅ Yes | ❌ No |
| Reporting Server Integration | ✅ Full | ⚠️ Simplified |

---

### 8. **Removed Components (Workshop Stack)**

The following components from the base stack are **NOT** included in the workshop version:

1. **Support Ticket API Gateway** (`SupportTicketApiGateway`)
   - API Gateway REST API
   - API resources and methods
   - Lambda integration for ticket management
   - Dedicated Lambda function for ticket operations

2. **Support Ticket Lambda Function** (`SupportTicketFunction`)
   - Complete ticket CRUD operations
   - Correspondence management
   - Database integration for tickets

3. **Support URL Management** (`UpdateSupportURLFunction`)
   - Custom resource for URL updates
   - SSM parameter management

4. **Database Parameter Group** (`DatabaseParameterGroup`)
   - Custom MySQL configuration
   - Charset compatibility settings

5. **Route 53 DNS Record** for ALB (`AppALBRecord`)
   - Private DNS: `app.acme.com`

6. **Reporting Server Web Server**
   - Apache/PHP installation
   - Analytics API endpoint
   - Database query functionality

---

### 9. **Reporting Server Differences**

#### Base Stack Reporting Server:
- Installs Apache, PHP, MySQL client
- Creates PHP-based analytics API (`/analytics.php`)
- Serves web interface on port 80
- Direct database queries for analytics
- Stores analytics in SSM Parameter Store

#### Workshop Stack Reporting Server:
- Python-based reporting script
- No web server installation
- CloudWatch metrics publishing
- Systemd service for continuous monitoring
- 5-minute metric publication interval

**Key Change**: Workshop version focuses on CloudWatch integration rather than web-based reporting.

---

### 10. **S3 Bucket Naming**

| Component | Base Stack | Workshop Stack |
|-----------|------------|----------------|
| Image Bucket | `sample-app-${AccountId}-image-${StackName}-${Region}` | `sample-app-${AccountId}-image-${StackName}` |

**Note**: Workshop version removes region suffix for simpler naming.

---

### 11. **Default Password Change**

| Parameter | Base Stack | Workshop Stack |
|-----------|------------|----------------|
| DBPassword Default | `ReInvent2025!` | `SapConcurWorkshop25` |

**Security Note**: Both use NoEcho for password protection.

---

## CloudWatch Monitoring Enhancements

### Workshop Stack Additions:

1. **Traffic Mirroring Metrics**:
   - `TrafficMirroring/Performance`: PacketCount, BytesPerSecond
   - `TrafficMirroring/Health`: ServiceStatus

2. **CloudWatch Dashboard**:
   - Real-time traffic mirroring metrics
   - Critical performance issues log insights
   - Service health monitoring

3. **Log Groups**:
   - `/aws/lambda/${PacketAnalysisFunction}`: Packet analysis logs
   - Enhanced retention policies (14 days)

---

## Network Architecture Comparison

### Base Stack:
```
Internet → ALB → Lambda Functions → RDS
                ↓
            S3 Bucket
                ↓
        Reporting Server (Web)
```

### Workshop Stack:
```
Internet → ALB → Lambda Functions → RDS
                ↓
            S3 Bucket
                ↓
        Reporting Server (Metrics)
                ↓
          CloudWatch
                ↓
    Traffic Mirroring Target → S3 → Lambda Analysis
```

---

## Use Case Differences

### Base Stack:
- **Purpose**: Complete image sharing application
- **Focus**: User-facing functionality
- **Monitoring**: Basic CloudWatch logs
- **Reporting**: Web-based analytics dashboard

### Workshop Stack:
- **Purpose**: Network performance monitoring workshop
- **Focus**: Deep packet inspection and analysis
- **Monitoring**: Advanced traffic mirroring and flow monitoring
- **Reporting**: CloudWatch metrics and automated alerts

---

## Migration Considerations

### Moving from Base to Workshop:

1. **Add Traffic Mirroring Infrastructure**:
   - Deploy traffic mirroring target instance
   - Configure S3 bucket for packet storage
   - Set up packet analysis Lambda

2. **Update IAM Roles**:
   - Add CloudWatch Network Flow Monitor policies
   - Add traffic mirroring permissions

3. **Configure VPC Endpoints**:
   - Deploy App VPC endpoints
   - Update security groups

4. **Modify Reporting Server**:
   - Replace web server with Python metrics script
   - Update systemd services

### Moving from Workshop to Base:

1. **Add Support Ticket System**:
   - Deploy API Gateway
   - Create support ticket Lambda
   - Update HTML rendering function

2. **Add Reporting Web Server**:
   - Install Apache/PHP on reporting server
   - Create analytics API endpoint

3. **Add Database Parameter Group**:
   - Create custom parameter group
   - Update RDS instance configuration

---

## Outputs Comparison

### Workshop Stack Additional Outputs:
- `TrafficMirroringS3BucketName`
- `TrafficMirroringTargetInstanceId`
- `TrafficMirroringTargetPrivateIP`
- `TrafficMirroringTargetENI`
- `PacketAnalysisFunctionArn`
- `TrafficMirroringAlertsTopicArn`
- `BastionInstanceENI`
- `ReportingServerInstanceId`
- `ReportingServerENI`
- `TrafficMirroringDashboardURL`

### Base Stack Additional Outputs:
- `SupportTicketApiGatewayURL`
- `SupportTicketFunctionArn`
- `PrivateApplicationURL`
- `PrivateDatabaseURL`
- `PrivateHostedZoneId`

---

## Cost Implications

### Workshop Stack Additional Costs:
1. **Traffic Mirroring Target**: t3.medium instance (~$30/month)
2. **S3 Storage**: Packet capture storage (variable, depends on traffic volume)
3. **Lambda Invocations**: Packet analysis function
4. **CloudWatch**: Additional metrics and dashboard
5. **VPC Endpoints**: Interface endpoints (~$7.20/month each × 8 = ~$57.60/month)

### Estimated Monthly Cost Difference: +$100-150

---

## Summary

The workshop stack is specifically designed for the **AgentCore Performance Agent workshop**, focusing on:

✅ **Deep packet inspection** with traffic mirroring  
✅ **Network flow monitoring** with CloudWatch integration  
✅ **Automated performance analysis** with Lambda  
✅ **Real-time alerting** via SNS  
✅ **Comprehensive monitoring** with CloudWatch dashboards  

The base stack provides a **complete image sharing application** with:

✅ **Support ticket system** with API Gateway  
✅ **Web-based analytics** dashboard  
✅ **Full CRUD operations** for tickets  
✅ **Private DNS** integration  
✅ **Production-ready** configuration  

Choose the appropriate stack based on your use case:
- **Workshop Stack**: Network performance monitoring and analysis
- **Base Stack**: Production image sharing application with support system
