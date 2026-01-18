# CloudFormation Template Resource Comparison

## Overview
This document compares the AWS resources created by `sample-app.yaml` and `sample-application.yaml`.

## Summary Statistics
- **sample-app.yaml**: 132 resources
- **sample-application.yaml**: 129 resources
- **Net difference**: 3 fewer resources in sample-application.yaml

## Resources Only in sample-app.yaml (43 resources)

### VPC Endpoints & Security
- `AppEC2MessagesVPCEndpoint`
- `AppEC2VPCEndpoint`
- `AppSSMMessagesVPCEndpoint`
- `AppSSMVPCEndpoint`
- `AppVPCEndpointSecurityGroup`

### Outputs/Parameters
- `AppPrivateSubnet1Id`
- `AppPrivateSubnet2Id`
- `BastionInstanceIP`
- `DatabaseName`
- `DatabaseUsername`
- `ImageBucketName`
- `LoadBalancerDNS`
- `Region`
- `ReportingPrivateSubnetId`
- `ReportingServerInstanceId`
- `ReportingServerIP`
- `StackName`

### Lambda Functions & Permissions
- `HTMLRenderingLambdaInvokePermission`
- `HTMLRenderingLambdaLogGroup`
- `ImageProcessingLambdaInvokePermission`
- `ImageProcessingLambdaLogGroup`
- `UserInteractionLambdaInvokePermission`
- `UserInteractionLambdaLogGroup`

### Traffic Mirroring Infrastructure
- `PacketAnalysisFunction`
- `PacketAnalysisFunctionArn`
- `PacketAnalysisLambdaInvokePermission`
- `PacketAnalysisLambdaLogGroup`
- `PacketAnalysisLambdaRole`
- `TrafficMirroringAlertsTopic`
- `TrafficMirroringAlertsTopicArn`
- `TrafficMirroringDashboard`
- `TrafficMirroringDashboardURL`
- `TrafficMirroringS3Bucket`
- `TrafficMirroringS3BucketName`
- `TrafficMirroringS3BucketPolicy`
- `TrafficMirroringTargetInstance`
- `TrafficMirroringTargetInstanceId`
- `TrafficMirroringTargetInstanceProfile`
- `TrafficMirroringTargetInstanceRole`
- `TrafficMirroringTargetPrivateIP`
- `TrafficMirroringTargetSecurityGroup`

### ALB Listener Rules
- `CorrespondenceListenerRule`
- `WorkshopProgressListenerRule`

### Logging
- `ImageAccessLogGroup`

### Reporting Server
- `ReportingServer`

## Resources Only in sample-application.yaml (40 resources)

### VPC Flow Logs
- `AppVPCFlowLog`
- `AppVPCLogGroup`
- `ReportingVPCFlowLog`
- `ReportingVPCLogGroup`
- `VPCFlowLogsRole`

### Route 53 & DNS
- `AppALBRecord`
- `PrivateHostedZoneId`

### SSM Parameters
- `ALBURLParameter`
- `DatabaseHostParameter`
- `DatabaseNameParameter`
- `DatabasePasswordParameter`
- `DatabaseUsernameParameter`

### Lambda Functions & Permissions (Updated naming)
- `HTMLRenderingLambdaPermission` (replaces HTMLRenderingLambdaInvokePermission)
- `HTMLRenderingLogGroup` (replaces HTMLRenderingLambdaLogGroup)
- `ImageProcessingLambdaPermission` (replaces ImageProcessingLambdaInvokePermission)
- `ImageProcessingLogGroup` (replaces ImageProcessingLambdaLogGroup)
- `UserInteractionLambdaPermission` (replaces UserInteractionLambdaInvokePermission)
- `UserInteractionLogGroup` (replaces UserInteractionLambdaLogGroup)
- `CreatePyMySQLLayerLogGroup`
- `UploadContentLogGroup`

### Support Ticket API Gateway
- `SupportTicketApiDeployment`
- `SupportTicketApiGateway`
- `SupportTicketApiGatewayURL`
- `SupportTicketApiMethod`
- `SupportTicketApiMethodProxy`
- `SupportTicketApiResource`
- `SupportTicketApiResourceProxy`
- `SupportTicketFunction`
- `SupportTicketFunctionArn`
- `SupportTicketLambdaPermission`
- `UpdateSupportURLFunction`
- `UpdateSupportURLResource`

### ALB Listener Rules
- `AnalyticsProxyListenerRule`
- `ProxyEndpointListenerRule`

### Database
- `DatabaseParameterGroup`

### Outputs/Parameters
- `ApplicationURL`
- `PrivateApplicationURL`
- `PrivateDatabaseURL`
- `S3BucketName`

### Reporting Server
- `ReportingEC2Instance` (replaces ReportingServer)
- `ReportingInstanceId`
- `ReportingServerLogGroup`

## Key Functional Differences

### 1. Traffic Mirroring (Removed in sample-application.yaml)
sample-app.yaml includes a complete traffic mirroring infrastructure with:
- Packet analysis Lambda function
- S3 bucket for packet storage
- CloudWatch dashboard
- SNS alerts
- Dedicated EC2 instance for traffic mirroring target

**Impact**: sample-application.yaml does not support network packet capture and analysis.

### 2. VPC Endpoints (Removed in sample-application.yaml)
sample-app.yaml includes VPC endpoints for:
- EC2
- EC2 Messages
- SSM
- SSM Messages

**Impact**: sample-application.yaml relies on NAT Gateway/Internet Gateway for AWS service access instead of private VPC endpoints.

### 3. VPC Flow Logs (Added in sample-application.yaml)
sample-application.yaml adds VPC Flow Logs for both App and Reporting VPCs with dedicated CloudWatch Log Groups.

**Impact**: Better network traffic visibility and troubleshooting capabilities.

### 4. Support Ticket System (Added in sample-application.yaml)
sample-application.yaml includes a complete API Gateway-based support ticket system with:
- API Gateway REST API
- Lambda functions for ticket processing
- Multiple API resources and methods

**Impact**: Enhanced application functionality with support ticket management.

### 5. Route 53 Private Hosted Zone (Added in sample-application.yaml)
sample-application.yaml includes:
- Private hosted zone
- ALB DNS record
- Private URLs for application and database access

**Impact**: Better internal DNS management and service discovery.

### 6. SSM Parameter Store (Added in sample-application.yaml)
sample-application.yaml stores configuration in SSM Parameter Store:
- ALB URL
- Database credentials
- Database host information

**Impact**: Centralized configuration management and better secrets handling.

### 7. Database Configuration (Enhanced in sample-application.yaml)
sample-application.yaml adds:
- Custom database parameter group
- More granular database configuration

**Impact**: Better database performance tuning capabilities.

### 8. Lambda Naming Convention
Lambda permissions and log groups have slightly different naming:
- sample-app.yaml: Uses "InvokePermission" suffix
- sample-application.yaml: Uses "Permission" suffix

**Impact**: Naming convention change only, no functional difference.

## Recommendation

**Use sample-application.yaml if you need:**
- VPC Flow Logs for network monitoring
- Support ticket system functionality
- Private hosted zone for internal DNS
- SSM Parameter Store for configuration management
- Modern infrastructure patterns

**Use sample-app.yaml if you need:**
- Traffic mirroring and packet analysis capabilities
- VPC endpoints for private AWS service access
- Simpler infrastructure without API Gateway

## Default Password Difference
- **sample-app.yaml**: Default DB password is `SapConcurWorkshop25`
- **sample-application.yaml**: Default DB password is `ReInvent2025!`
