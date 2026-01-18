# Connectivity Troubleshooting SOP

## Overview

This Standard Operating Procedure (SOP) provides comprehensive guidelines for troubleshooting connectivity issues in the EXAMPLECORP Image Gallery Platform's AgentCore Memory integration. This document covers network connectivity, database connections, memory service connectivity, and inter-service communication issues.

## Troubleshooting Framework

### Issue Classification

#### Severity Levels
- **Critical (P0)**: Complete system outage affecting all users
- **High (P1)**: Major functionality impaired, affecting multiple users
- **Medium (P2)**: Minor functionality issues, affecting some users
- **Low (P3)**: Cosmetic issues or single-user problems

#### Issue Categories
- **Network Connectivity**: VPC, subnet, routing, security group issues
- **Database Connectivity**: RDS connection pool, authentication, timeout issues
- **Memory Service**: AgentCore Memory API connectivity and authentication
- **Inter-Service Communication**: Lambda-to-Lambda, API Gateway issues
- **External Dependencies**: S3, Cognito, third-party service connectivity

## Network Connectivity Troubleshooting

### VPC and Subnet Issues

#### Diagnostic Commands
```bash
#!/bin/bash
# scripts/network_diagnostics.sh

echo "=== Network Connectivity Diagnostics ==="
echo "Timestamp: $(date)"

# Check VPC configuration
echo "1. VPC Configuration:"
aws ec2 describe-vpcs \
    --filters "Name=tag:Name,Values=examplecorp-gallery-vpc" \
    --query 'Vpcs[0].[VpcId,State,CidrBlock]' \
    --output table

# Check subnet configuration
echo "2. Subnet Configuration:"
aws ec2 describe-subnets \
    --filters "Name=tag:Environment,Values=production" \
    --query 'Subnets[*].[SubnetId,AvailabilityZone,CidrBlock,State]' \
    --output table

# Check route tables
echo "3. Route Tables:"
aws ec2 describe-route-tables \
    --filters "Name=tag:Environment,Values=production" \
    --query 'RouteTables[*].Routes[*].[DestinationCidrBlock,GatewayId,State]' \
    --output table

# Check NAT Gateway status
echo "4. NAT Gateway Status:"
aws ec2 describe-nat-gateways \
    --query 'NatGateways[*].[NatGatewayId,State,SubnetId]' \
    --output table

# Check Internet Gateway
echo "5. Internet Gateway:"
aws ec2 describe-internet-gateways \
    --filters "Name=attachment.vpc-id,Values=$(aws ec2 describe-vpcs --filters 'Name=tag:Name,Values=examplecorp-gallery-vpc' --query 'Vpcs[0].VpcId' --output text)" \
    --query 'InternetGateways[*].[InternetGatewayId,State]' \
    --output table

echo "=== Network Diagnostics Complete ==="
```

#### Security Group Analysis
```python
# scripts/security_group_analyzer.py
import boto3
import json
from typing import Dict, List

class SecurityGroupAnalyzer:
    """Analyze security group configurations for connectivity issues"""
    
    def __init__(self):
        self.ec2 = boto3.client('ec2')
    
    def analyze_security_groups(self, instance_id: str = None, sg_ids: List[str] = None) -> Dict:
        """Analyze security group rules for potential connectivity issues"""
        
        if instance_id:
            # Get security groups from instance
            instance = self.ec2.describe_instances(InstanceIds=[instance_id])
            sg_ids = [sg['GroupId'] for sg in instance['Reservations'][0]['Instances'][0]['SecurityGroups']]
        
        if not sg_ids:
            raise ValueError("Either instance_id or sg_ids must be provided")
        
        analysis = {
            "security_groups": [],
            "potential_issues": [],
            "recommendations": []
        }
        
        for sg_id in sg_ids:
            sg_info = self.analyze_single_security_group(sg_id)
            analysis["security_groups"].append(sg_info)
            
            # Check for common issues
            issues = self.check_common_sg_issues(sg_info)
            analysis["potential_issues"].extend(issues)
        
        # Generate recommendations
        analysis["recommendations"] = self.generate_sg_recommendations(analysis["potential_issues"])
        
        return analysis
    
    def analyze_single_security_group(self, sg_id: str) -> Dict:
        """Analyze a single security group"""
        
        sg = self.ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
        
        return {
            "group_id": sg_id,
            "group_name": sg['GroupName'],
            "description": sg['Description'],
            "vpc_id": sg['VpcId'],
            "inbound_rules": sg['IpPermissions'],
            "outbound_rules": sg['IpPermissionsEgress']
        }
    
    def check_common_sg_issues(self, sg_info: Dict) -> List[Dict]:
        """Check for common security group issues"""
        
        issues = []
        
        # Check for overly permissive rules
        for rule in sg_info["inbound_rules"]:
            for ip_range in rule.get("IpRanges", []):
                if ip_range.get("CidrIp") == "0.0.0.0/0":
                    issues.append({
                        "type": "overly_permissive_inbound",
                        "severity": "high",
                        "description": f"Inbound rule allows traffic from anywhere (0.0.0.0/0) on port {rule.get('FromPort', 'all')}",
                        "security_group": sg_info["group_id"]
                    })
        
        # Check for missing database access
        db_ports = [3306, 5432, 1433]  # MySQL, PostgreSQL, SQL Server
        has_db_access = any(
            rule.get("FromPort") in db_ports or rule.get("ToPort") in db_ports
            for rule in sg_info["inbound_rules"] + sg_info["outbound_rules"]
        )
        
        if not has_db_access:
            issues.append({
                "type": "missing_database_access",
                "severity": "medium",
                "description": "No database port access found in security group rules",
                "security_group": sg_info["group_id"]
            })
        
        # Check for HTTPS access
        has_https = any(
            rule.get("FromPort") == 443 or rule.get("ToPort") == 443
            for rule in sg_info["outbound_rules"]
        )
        
        if not has_https:
            issues.append({
                "type": "missing_https_access",
                "severity": "medium",
                "description": "No HTTPS outbound access found",
                "security_group": sg_info["group_id"]
            })
        
        return issues
    
    def generate_sg_recommendations(self, issues: List[Dict]) -> List[str]:
        """Generate recommendations based on identified issues"""
        
        recommendations = []
        
        for issue in issues:
            if issue["type"] == "overly_permissive_inbound":
                recommendations.append(f"Restrict inbound access in {issue['security_group']} to specific IP ranges or security groups")
            
            elif issue["type"] == "missing_database_access":
                recommendations.append(f"Add database port access to {issue['security_group']} for RDS connectivity")
            
            elif issue["type"] == "missing_https_access":
                recommendations.append(f"Add HTTPS outbound access to {issue['security_group']} for external API calls")
        
        return list(set(recommendations))  # Remove duplicates

# Usage example
if __name__ == "__main__":
    analyzer = SecurityGroupAnalyzer()
    
    # Analyze specific security groups
    sg_analysis = analyzer.analyze_security_groups(sg_ids=["sg-12345678", "sg-87654321"])
    
    print(json.dumps(sg_analysis, indent=2))
```

### Transit Gateway Troubleshooting

#### Transit Gateway Status Check
```bash
#!/bin/bash
# scripts/tgw_diagnostics.sh

echo "=== Transit Gateway Diagnostics ==="

# Check Transit Gateway status
echo "1. Transit Gateway Status:"
aws ec2 describe-transit-gateways \
    --query 'TransitGateways[*].[TransitGatewayId,State,Description]' \
    --output table

# Check Transit Gateway attachments
echo "2. Transit Gateway Attachments:"
aws ec2 describe-transit-gateway-attachments \
    --query 'TransitGatewayAttachments[*].[TransitGatewayAttachmentId,TransitGatewayId,ResourceId,State]' \
    --output table

# Check Transit Gateway route tables
echo "3. Transit Gateway Route Tables:"
aws ec2 describe-transit-gateway-route-tables \
    --query 'TransitGatewayRouteTables[*].[TransitGatewayRouteTableId,TransitGatewayId,State]' \
    --output table

# Check specific routes
TGW_ROUTE_TABLE_ID=$(aws ec2 describe-transit-gateway-route-tables --query 'TransitGatewayRouteTables[0].TransitGatewayRouteTableId' --output text)

if [ "$TGW_ROUTE_TABLE_ID" != "None" ]; then
    echo "4. Transit Gateway Routes:"
    aws ec2 search-transit-gateway-routes \
        --transit-gateway-route-table-id $TGW_ROUTE_TABLE_ID \
        --filters "Name=state,Values=active" \
        --query 'Routes[*].[DestinationCidrBlock,TransitGatewayAttachments[0].TransitGatewayAttachmentId,State]' \
        --output table
fi

echo "=== Transit Gateway Diagnostics Complete ==="
```

## Database Connectivity Troubleshooting

### RDS Connection Issues

#### Database Connection Tester
```python
# scripts/database_connection_tester.py
import asyncio
import aiomysql
import time
import json
from datetime import datetime
from typing import Dict, List, Optional

class DatabaseConnectionTester:
    """Test and diagnose database connectivity issues"""
    
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connection_pool = None
    
    async def comprehensive_connection_test(self) -> Dict:
        """Perform comprehensive database connectivity tests"""
        
        test_results = {
            "timestamp": datetime.now().isoformat(),
            "database_info": {
                "host": self.host,
                "port": self.port,
                "database": self.database
            },
            "tests": {}
        }
        
        # Test 1: Basic connectivity
        test_results["tests"]["basic_connectivity"] = await self.test_basic_connectivity()
        
        # Test 2: Connection pool
        test_results["tests"]["connection_pool"] = await self.test_connection_pool()
        
        # Test 3: Query performance
        test_results["tests"]["query_performance"] = await self.test_query_performance()
        
        # Test 4: Connection limits
        test_results["tests"]["connection_limits"] = await self.test_connection_limits()
        
        # Test 5: SSL connectivity
        test_results["tests"]["ssl_connectivity"] = await self.test_ssl_connectivity()
        
        # Generate recommendations
        test_results["recommendations"] = self.generate_recommendations(test_results["tests"])
        
        return test_results
    
    async def test_basic_connectivity(self) -> Dict:
        """Test basic database connectivity"""
        
        start_time = time.time()
        
        try:
            connection = await aiomysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                connect_timeout=10
            )
            
            # Test simple query
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT 1")
                result = await cursor.fetchone()
            
            await connection.ensure_closed()
            
            connection_time = (time.time() - start_time) * 1000
            
            return {
                "status": "success",
                "connection_time_ms": round(connection_time, 2),
                "query_result": result[0] if result else None
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "connection_time_ms": (time.time() - start_time) * 1000
            }
    
    async def test_connection_pool(self) -> Dict:
        """Test connection pool functionality"""
        
        try:
            # Create connection pool
            pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                minsize=1,
                maxsize=10,
                pool_recycle=3600
            )
            
            # Test multiple concurrent connections
            async def test_connection():
                async with pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute("SELECT CONNECTION_ID()")
                        return await cursor.fetchone()
            
            # Test 5 concurrent connections
            tasks = [test_connection() for _ in range(5)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            pool.close()
            await pool.wait_closed()
            
            successful_connections = [r for r in results if not isinstance(r, Exception)]
            
            return {
                "status": "success",
                "concurrent_connections_tested": 5,
                "successful_connections": len(successful_connections),
                "connection_ids": [r[0] for r in successful_connections if r]
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def test_query_performance(self) -> Dict:
        """Test database query performance"""
        
        try:
            connection = await aiomysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database
            )
            
            performance_tests = {}
            
            # Test 1: Simple SELECT
            start_time = time.time()
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT 1")
                await cursor.fetchone()
            performance_tests["simple_select_ms"] = round((time.time() - start_time) * 1000, 2)
            
            # Test 2: Table count query
            start_time = time.time()
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (self.database,))
                table_count = await cursor.fetchone()
            performance_tests["table_count_query_ms"] = round((time.time() - start_time) * 1000, 2)
            performance_tests["table_count"] = table_count[0] if table_count else 0
            
            # Test 3: Memory-related table queries (if they exist)
            memory_tables = ['workshop_progress', 'support_tickets', 'correspondence_messages']
            for table in memory_tables:
                try:
                    start_time = time.time()
                    async with connection.cursor() as cursor:
                        await cursor.execute(f"SELECT COUNT(*) FROM {table} LIMIT 1")
                        count = await cursor.fetchone()
                    performance_tests[f"{table}_query_ms"] = round((time.time() - start_time) * 1000, 2)
                    performance_tests[f"{table}_count"] = count[0] if count else 0
                except:
                    performance_tests[f"{table}_query_ms"] = "table_not_found"
            
            await connection.ensure_closed()
            
            return {
                "status": "success",
                "performance_metrics": performance_tests
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def test_connection_limits(self) -> Dict:
        """Test database connection limits"""
        
        try:
            connection = await aiomysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database
            )
            
            async with connection.cursor() as cursor:
                # Get current connection count
                await cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                current_connections = await cursor.fetchone()
                
                # Get max connections
                await cursor.execute("SHOW VARIABLES LIKE 'max_connections'")
                max_connections = await cursor.fetchone()
                
                # Get connection usage percentage
                current_count = int(current_connections[1]) if current_connections else 0
                max_count = int(max_connections[1]) if max_connections else 0
                usage_percentage = (current_count / max_count) * 100 if max_count > 0 else 0
            
            await connection.ensure_closed()
            
            return {
                "status": "success",
                "current_connections": current_count,
                "max_connections": max_count,
                "usage_percentage": round(usage_percentage, 2)
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def test_ssl_connectivity(self) -> Dict:
        """Test SSL database connectivity"""
        
        try:
            # Test SSL connection
            connection = await aiomysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                ssl={'ssl': True}
            )
            
            async with connection.cursor() as cursor:
                await cursor.execute("SHOW STATUS LIKE 'Ssl_cipher'")
                ssl_cipher = await cursor.fetchone()
            
            await connection.ensure_closed()
            
            return {
                "status": "success",
                "ssl_enabled": True,
                "ssl_cipher": ssl_cipher[1] if ssl_cipher else "unknown"
            }
            
        except Exception as e:
            # Try without SSL
            try:
                connection = await aiomysql.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    db=self.database
                )
                await connection.ensure_closed()
                
                return {
                    "status": "success",
                    "ssl_enabled": False,
                    "note": "SSL connection failed, but non-SSL connection succeeded"
                }
            except:
                return {
                    "status": "failed",
                    "error": str(e)
                }
    
    def generate_recommendations(self, test_results: Dict) -> List[str]:
        """Generate recommendations based on test results"""
        
        recommendations = []
        
        # Basic connectivity recommendations
        if test_results.get("basic_connectivity", {}).get("status") == "failed":
            recommendations.append("Check network connectivity, security groups, and database credentials")
        
        # Performance recommendations
        basic_conn_time = test_results.get("basic_connectivity", {}).get("connection_time_ms", 0)
        if basic_conn_time > 1000:
            recommendations.append("Database connection time is high. Check network latency and database performance")
        
        # Connection pool recommendations
        pool_test = test_results.get("connection_pool", {})
        if pool_test.get("status") == "success":
            successful = pool_test.get("successful_connections", 0)
            if successful < 5:
                recommendations.append("Connection pool test showed limited concurrent connections. Check connection limits")
        
        # Connection limits recommendations
        limits_test = test_results.get("connection_limits", {})
        if limits_test.get("status") == "success":
            usage = limits_test.get("usage_percentage", 0)
            if usage > 80:
                recommendations.append("Database connection usage is high. Consider increasing max_connections or optimizing connection usage")
        
        # SSL recommendations
        ssl_test = test_results.get("ssl_connectivity", {})
        if ssl_test.get("status") == "success" and not ssl_test.get("ssl_enabled", False):
            recommendations.append("Consider enabling SSL for database connections to improve security")
        
        return recommendations

# Usage example
async def main():
    tester = DatabaseConnectionTester(
        host="examplecorp-gallery-db.cluster-xyz.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin",
        password="your-password",
        database="examplecorp_gallery"
    )
    
    results = await tester.comprehensive_connection_test()
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
```

### RDS Performance Analysis
```bash
#!/bin/bash
# scripts/rds_performance_check.sh

echo "=== RDS Performance Analysis ==="

DB_INSTANCE_ID="examplecorp-gallery-db"

# Check RDS instance status
echo "1. RDS Instance Status:"
aws rds describe-db-instances \
    --db-instance-identifier $DB_INSTANCE_ID \
    --query 'DBInstances[0].[DBInstanceStatus,Engine,DBInstanceClass,AllocatedStorage]' \
    --output table

# Check recent performance metrics
echo "2. CPU Utilization (last 1 hour):"
aws cloudwatch get-metric-statistics \
    --namespace "AWS/RDS" \
    --metric-name "CPUUtilization" \
    --dimensions Name=DBInstanceIdentifier,Value=$DB_INSTANCE_ID \
    --start-time $(date -d "1 hour ago" --iso-8601) \
    --end-time $(date --iso-8601) \
    --period 300 \
    --statistics Average,Maximum \
    --query 'Datapoints[*].[Timestamp,Average,Maximum]' \
    --output table

echo "3. Database Connections (last 1 hour):"
aws cloudwatch get-metric-statistics \
    --namespace "AWS/RDS" \
    --metric-name "DatabaseConnections" \
    --dimensions Name=DBInstanceIdentifier,Value=$DB_INSTANCE_ID \
    --start-time $(date -d "1 hour ago" --iso-8601) \
    --end-time $(date --iso-8601) \
    --period 300 \
    --statistics Average,Maximum \
    --query 'Datapoints[*].[Timestamp,Average,Maximum]' \
    --output table

echo "4. Read/Write Latency (last 1 hour):"
aws cloudwatch get-metric-statistics \
    --namespace "AWS/RDS" \
    --metric-name "ReadLatency" \
    --dimensions Name=DBInstanceIdentifier,Value=$DB_INSTANCE_ID \
    --start-time $(date -d "1 hour ago" --iso-8601) \
    --end-time $(date --iso-8601) \
    --period 300 \
    --statistics Average \
    --query 'Datapoints[*].[Timestamp,Average]' \
    --output table

aws cloudwatch get-metric-statistics \
    --namespace "AWS/RDS" \
    --metric-name "WriteLatency" \
    --dimensions Name=DBInstanceIdentifier,Value=$DB_INSTANCE_ID \
    --start-time $(date -d "1 hour ago" --iso-8601) \
    --end-time $(date --iso-8601) \
    --period 300 \
    --statistics Average \
    --query 'Datapoints[*].[Timestamp,Average]' \
    --output table

echo "=== RDS Performance Analysis Complete ==="
```

## Memory Service Connectivity

### AgentCore Memory Service Testing
```python
# scripts/memory_service_tester.py
import asyncio
import aiohttp
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

class MemoryServiceTester:
    """Test AgentCore Memory service connectivity and functionality"""
    
    def __init__(self, memory_endpoint: str, api_key: str):
        self.memory_endpoint = memory_endpoint
        self.api_key = api_key
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def comprehensive_memory_test(self) -> Dict:
        """Perform comprehensive memory service tests"""
        
        test_results = {
            "timestamp": datetime.now().isoformat(),
            "memory_endpoint": self.memory_endpoint,
            "tests": {}
        }
        
        # Test 1: Service health check
        test_results["tests"]["health_check"] = await self.test_health_check()
        
        # Test 2: Authentication
        test_results["tests"]["authentication"] = await self.test_authentication()
        
        # Test 3: Memory storage
        test_results["tests"]["memory_storage"] = await self.test_memory_storage()
        
        # Test 4: Memory retrieval
        test_results["tests"]["memory_retrieval"] = await self.test_memory_retrieval()
        
        # Test 5: Strategy-specific tests
        test_results["tests"]["strategy_tests"] = await self.test_memory_strategies()
        
        # Test 6: Performance testing
        test_results["tests"]["performance"] = await self.test_performance()
        
        # Generate recommendations
        test_results["recommendations"] = self.generate_recommendations(test_results["tests"])
        
        return test_results
    
    async def test_health_check(self) -> Dict:
        """Test memory service health endpoint"""
        
        start_time = time.time()
        
        try:
            async with self.session.get(f"{self.memory_endpoint}/health") as response:
                response_time = (time.time() - start_time) * 1000
                
                if response.status == 200:
                    health_data = await response.json()
                    return {
                        "status": "success",
                        "response_time_ms": round(response_time, 2),
                        "health_data": health_data
                    }
                else:
                    return {
                        "status": "failed",
                        "response_time_ms": round(response_time, 2),
                        "http_status": response.status,
                        "error": await response.text()
                    }
        
        except Exception as e:
            return {
                "status": "failed",
                "response_time_ms": (time.time() - start_time) * 1000,
                "error": str(e)
            }
    
    async def test_authentication(self) -> Dict:
        """Test memory service authentication"""
        
        try:
            # Test with valid API key
            async with self.session.get(f"{self.memory_endpoint}/auth/validate") as response:
                if response.status == 200:
                    auth_data = await response.json()
                    return {
                        "status": "success",
                        "auth_valid": True,
                        "auth_data": auth_data
                    }
                else:
                    return {
                        "status": "failed",
                        "auth_valid": False,
                        "http_status": response.status,
                        "error": await response.text()
                    }
        
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def test_memory_storage(self) -> Dict:
        """Test memory storage functionality"""
        
        test_data = {
            "strategy": "semantic",
            "content": "Test memory storage connectivity check",
            "metadata": {
                "test_id": f"connectivity_test_{int(time.time())}",
                "test_type": "connectivity_check"
            }
        }
        
        start_time = time.time()
        
        try:
            async with self.session.post(
                f"{self.memory_endpoint}/memory/store",
                json=test_data
            ) as response:
                response_time = (time.time() - start_time) * 1000
                
                if response.status in [200, 201]:
                    storage_result = await response.json()
                    return {
                        "status": "success",
                        "response_time_ms": round(response_time, 2),
                        "memory_id": storage_result.get("memory_id"),
                        "storage_result": storage_result
                    }
                else:
                    return {
                        "status": "failed",
                        "response_time_ms": round(response_time, 2),
                        "http_status": response.status,
                        "error": await response.text()
                    }
        
        except Exception as e:
            return {
                "status": "failed",
                "response_time_ms": (time.time() - start_time) * 1000,
                "error": str(e)
            }
    
    async def test_memory_retrieval(self) -> Dict:
        """Test memory retrieval functionality"""
        
        query_data = {
            "strategy": "semantic",
            "query": "connectivity check",
            "max_results": 5
        }
        
        start_time = time.time()
        
        try:
            async with self.session.post(
                f"{self.memory_endpoint}/memory/retrieve",
                json=query_data
            ) as response:
                response_time = (time.time() - start_time) * 1000
                
                if response.status == 200:
                    retrieval_result = await response.json()
                    return {
                        "status": "success",
                        "response_time_ms": round(response_time, 2),
                        "results_count": len(retrieval_result.get("results", [])),
                        "retrieval_result": retrieval_result
                    }
                else:
                    return {
                        "status": "failed",
                        "response_time_ms": round(response_time, 2),
                        "http_status": response.status,
                        "error": await response.text()
                    }
        
        except Exception as e:
            return {
                "status": "failed",
                "response_time_ms": (time.time() - start_time) * 1000,
                "error": str(e)
            }
    
    async def test_memory_strategies(self) -> Dict:
        """Test all memory strategies"""
        
        strategies = ["semantic", "summary", "user_preference", "custom"]
        strategy_results = {}
        
        for strategy in strategies:
            test_data = {
                "strategy": strategy,
                "query": f"test {strategy} strategy connectivity
