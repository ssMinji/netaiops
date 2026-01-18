# CloudFormation Template Comparison: sample-app.yaml vs sample-application.yaml

## Overview
This document outlines the key differences between the two CloudFormation templates used for deploying the ACME Image Gallery application.

## File Information
- **sample-app.yaml**: Original template (3-Lambda architecture)
- **sample-application.yaml**: Enhanced template with improved flow implementation

---

## Major Differences

### 1. **Description and Architecture Flow**

**sample-app.yaml:**
- Description: 'Image Sharing Sample Application - 3 Lambda Architecture'
- No explicit flow documentation

**sample-application.yaml:**
- Description: 'Enhanced ACME Image Sharing Sample Application - Implementing Required Flow:
  1. User clicks like/share → User Interaction Lambda → Database update
  2. User refreshes → HTML Rendering Lambda → Database query → Updated counts displayed  
  3. User clicks Reports tab → HTML Rendering Lambda → Reporting server → Database → Analytics displayed
  4. Reporting server → Direct database query → Local analytics dashboard'

### 2. **Default Database Password**

**sample-app.yaml:**
- Default: `SapConcurWorkshop25`

**sample-application.yaml:**
- Default: `ReInvent2025!`

### 3. **S3 Bucket Naming**

**sample-app.yaml:**
```yaml
BucketName: !Sub "sample-app-${AWS::AccountId}-image-${AWS::StackName}"
```

**sample-application.yaml:**
```yaml
BucketName: !Sub "sample-app-${AWS::AccountId}-image-${AWS::StackName}-${AWS::Region}"
```
- Includes region in bucket name for better uniqueness

### 4. **Bastion Instance Configuration**

**sample-app.yaml:**
- InstanceType: `t3.micro`
