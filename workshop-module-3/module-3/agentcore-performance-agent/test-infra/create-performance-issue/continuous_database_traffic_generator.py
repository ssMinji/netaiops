#!/usr/bin/env python3
"""
Continuous Database Traffic Generator - Dual Mode with Background Support

This script generates sustained database traffic from the reporting server directly to RDS
to test network performance and observe retransmission issues in Network Flow Monitor.

MODES:
1. SSM Mode (default): Run from your local machine, uses SSM to execute queries on reporting server
2. Local Mode (--local-mode): Run directly on the reporting server instance, executes MySQL queries locally

BACKGROUND MODE:
- Runs as a daemon process detached from terminal (use --background)
- Works with BOTH SSM mode and local mode
- Logs output to files in current directory
- Creates PID file for process management
- Can be stopped using the PID file

CRITICAL: Traffic flows directly from reporting server (where TCP settings are modified) to RDS.
TCP issues on the reporting server will cause retransmissions visible in Network Flow Monitor.

Traffic path: Reporting Server (TCP issues here) → RDS Database

Usage:
    # From local machine (SSM mode - default):
    python3 continuous_database_traffic_generator-v4.py [--stack-name STACK_NAME] [--region REGION] [--duration MINUTES]
    
    # SSM mode in background:
    python3 continuous_database_traffic_generator-v4.py --background [--stack-name STACK_NAME] [--region REGION] [--duration MINUTES]
    
    # Directly on reporting server (local mode):
    python3 continuous_database_traffic_generator-v4.py --local-mode --db-host RDS_ENDPOINT --db-password PASSWORD [--duration MINUTES]
    
    # Local mode in background:
    python3 continuous_database_traffic_generator-v4.py --local-mode --db-host RDS_ENDPOINT --db-password PASSWORD --background

Requirements:
    - SSM Mode: AWS CLI configured, boto3 library, SSM Session Manager plugin
    - Local Mode: MySQL client installed on reporting server
"""

import subprocess
import sys
import time
import json
import argparse
import random
import signal
import logging
import threading
import os
import atexit
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Optional imports for SSM mode
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

# Global variables for daemon mode
PIDFILE = 'continuous_traffic_generator.pid'
LOGFILE = 'continuous_traffic_generator.log'
ERRFILE = 'continuous_traffic_generator.err'

# Set up logging (will be reconfigured for daemon mode)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def daemonize():
    """
    Daemonize the current process using double-fork technique.
    This detaches the process from the terminal and runs it in the background.
    """
    # Get absolute paths for log files before changing directory
    global LOGFILE, ERRFILE, PIDFILE
    LOGFILE = os.path.abspath(LOGFILE)
    ERRFILE = os.path.abspath(ERRFILE)
    PIDFILE = os.path.abspath(PIDFILE)
    
    try:
        # First fork
        pid = os.fork()
        if pid > 0:
            # Exit parent process
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #1 failed: {e}\n")
        sys.exit(1)
    
    # Decouple from parent environment
    os.chdir('/')
    os.setsid()
    os.umask(0)
    
    try:
        # Second fork
        pid = os.fork()
        if pid > 0:
            # Exit second parent process
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #2 failed: {e}\n")
        sys.exit(1)
    
    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Open log files
    si = open(os.devnull, 'r')
    so = open(LOGFILE, 'a+')
    se = open(ERRFILE, 'a+')
    
    # Redirect stdin, stdout, stderr
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())
    
    # Write PID file
    atexit.register(remove_pidfile)
    pid = str(os.getpid())
    with open(PIDFILE, 'w+') as f:
        f.write(f"{pid}\n")
    
    # Reconfigure logging to use file handlers
    logger.handlers.clear()
    file_handler = logging.FileHandler(LOGFILE)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)
    
    logger.info("=" * 80)
    logger.info(f"Daemon process started with PID: {pid}")
    logger.info(f"Log file: {os.path.abspath(LOGFILE)}")
    logger.info(f"Error file: {os.path.abspath(ERRFILE)}")
    logger.info(f"PID file: {os.path.abspath(PIDFILE)}")
    logger.info("=" * 80)


def remove_pidfile():
    """Remove the PID file on exit"""
    try:
        if os.path.exists(PIDFILE):
            os.remove(PIDFILE)
            logger.info(f"Removed PID file: {PIDFILE}")
    except Exception as e:
        logger.error(f"Error removing PID file: {e}")


def check_if_running():
    """Check if another instance is already running"""
    if os.path.exists(PIDFILE):
        with open(PIDFILE, 'r') as f:
            pid = int(f.read().strip())
        
        # Check if process is actually running
        try:
            os.kill(pid, 0)
            return True, pid
        except OSError:
            # Process not running, remove stale PID file
            os.remove(PIDFILE)
            return False, None
    return False, None


class RateLimiter:
    """Rate limiter to control SSM API call frequency"""
    def __init__(self, max_calls_per_second=2):
        self.max_calls_per_second = max_calls_per_second
        self.min_interval = 1.0 / max_calls_per_second
        self.last_call_time = 0
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        """Wait if necessary to respect rate limit"""
        with self.lock:
            current_time = time.time()
            time_since_last_call = current_time - self.last_call_time
            
            if time_since_last_call < self.min_interval:
                sleep_time = self.min_interval - time_since_last_call
                time.sleep(sleep_time)
            
            self.last_call_time = time.time()


class ContinuousDatabaseTrafficGenerator:
    def __init__(self, local_mode=False, db_host=None, db_user='admin', db_password=None, 
                 db_name='image_metadata', stack_name="sample-application", region="us-east-1"):
        """
        Initialize the traffic generator.
        
        Args:
            local_mode (bool): If True, run directly on bastion without SSM
            db_host (str): Database host (required for local mode)
            db_user (str): Database username
            db_password (str): Database password (required for local mode)
            db_name (str): Database name
            stack_name (str): CloudFormation stack name (for SSM mode)
            region (str): AWS region (for SSM mode)
        """
        self.local_mode = local_mode
        self.stack_name = stack_name
        self.region = region
        self.running = True
        
        # Initialize statistics
        self.stats = {
            'successful_queries': 0,
            'failed_queries': 0,
            'connection_errors': 0,
            'timeout_errors': 0,
            'retransmission_indicators': 0,
            'buffer_overflow_errors': 0,
            'tcp_reset_errors': 0,
            'aggressive_retransmissions': 0,
            'throttling_errors': 0
        }
        
        # Infrastructure details
        self.db_host = db_host
        self.db_user = db_user
        self.db_password = db_password
        self.db_name = db_name
        self.reporting_instance_id = None
        
        if self.local_mode:
            # LOCAL MODE: Running directly on reporting server
            logger.info("🏠 LOCAL MODE: Running directly on reporting server instance")
            if not db_host or not db_password:
                logger.error("❌ Local mode requires --db-host and --db-password parameters")
                sys.exit(1)
            
            # Verify MySQL client is available
            try:
                subprocess.run(['mysql', '--version'], capture_output=True, check=True)
                logger.info("✓ MySQL client is available")
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.error("❌ MySQL client not found. Please install it first.")
                sys.exit(1)
            
            logger.info(f"🎯 TRAFFIC PATH CONFIGURATION (LOCAL MODE):")
            logger.info(f"   This Reporting Server (TCP issues here) → RDS Database ({self.db_host})")
            logger.info(f"   Database: {self.db_name}")
            logger.info(f"   User: {self.db_user}")
            logger.info(f"   ⚠️  TCP settings on THIS reporting server will affect traffic")
            
        else:
            # SSM MODE: Running from local machine
            if not BOTO3_AVAILABLE:
                logger.error("❌ boto3 not available. Install with: pip install boto3")
                sys.exit(1)
            
            logger.info("☁️  SSM MODE: Running from local machine via AWS SSM")
            
            # Initialize rate limiter for SSM API calls
            self.rate_limiter = RateLimiter(max_calls_per_second=1)
            
            try:
                # Initialize AWS clients
                self.ssm_client = boto3.client('ssm', region_name=region)
                self.cf_client = boto3.client('cloudformation', region_name=region)
                self.ec2_client = boto3.client('ec2', region_name=region)
                
                logger.info(f"✓ Initialized AWS clients for region: {region}")
                
                # Get infrastructure details
                self.setup_infrastructure_details()
                
                # Find reporting server host
                self.find_reporting_host()
                
            except NoCredentialsError:
                logger.error("✗ AWS credentials not found. Please configure AWS CLI.")
                sys.exit(1)
            except Exception as e:
                logger.error(f"✗ Error initializing AWS clients: {e}")
                sys.exit(1)
    
    def signal_handler(self, signum, frame):
        """Handle interrupt signals gracefully"""
        logger.info("Received interrupt signal. Stopping traffic generation...")
        self.running = False
    
    def setup_infrastructure_details(self):
        """Set up database connection details from CloudFormation stack and SSM Parameter Store"""
        outputs = self.get_stack_outputs()
        
        # Get RDS endpoint (direct connection from bastion)
        self.db_host = outputs.get('DatabaseEndpoint', 'localhost')
        self.db_name = 'image_metadata'
        
        # Get database credentials from SSM Parameter Store (as defined in CloudFormation)
        try:
            # Get username from SSM
            username_param = self.ssm_client.get_parameter(Name='/acme/database/username')
            self.db_user = username_param['Parameter']['Value']
            logger.info(f"✓ Retrieved database username from SSM: {self.db_user}")
        except Exception as e:
            logger.warning(f"Could not retrieve username from SSM, using default: {e}")
            self.db_user = 'admin'
        
        try:
            # Get password from SSM
            password_param = self.ssm_client.get_parameter(Name='/acme/database/password', WithDecryption=True)
            self.db_password = password_param['Parameter']['Value']
            logger.info(f"✓ Retrieved database password from SSM Parameter Store")
        except Exception as e:
            logger.warning(f"Could not retrieve password from SSM, using default: {e}")
            self.db_password = 'ReInvent2025!'  # Default password from CloudFormation template
        
        logger.info(f"🎯 TRAFFIC PATH CONFIGURATION:")
        logger.info(f"   Reporting Server (TCP issues here) → RDS Database ({self.db_host})")
        logger.info(f"   Database: {self.db_name}")
        logger.info(f"   User: {self.db_user}")
        logger.info(f"   ⚠️  TCP settings on reporting server will affect this traffic")
    
    def find_reporting_host(self):
        """Find the reporting server instance ID from CloudFormation stack outputs"""
        try:
            # Get reporting instance ID from stack outputs
            outputs = self.get_stack_outputs()
            reporting_instance_id = outputs.get('ReportingInstanceId')
            
            if not reporting_instance_id:
                raise Exception("ReportingInstanceId not found in stack outputs")
            
            # Verify the instance is running
            response = self.ec2_client.describe_instances(
                InstanceIds=[reporting_instance_id]
            )
            
            if response['Reservations']:
                instance = response['Reservations'][0]['Instances'][0]
                instance_state = instance['State']['Name']
                
                if instance_state != 'running':
                    raise Exception(f"Reporting instance {reporting_instance_id} is not running (state: {instance_state})")
                
                self.reporting_instance_id = reporting_instance_id
                logger.info(f"Found reporting server from stack: {self.reporting_instance_id}")
            else:
                raise Exception(f"Reporting instance {reporting_instance_id} not found")
                
        except Exception as e:
            logger.error(f"Error finding reporting server: {e}")
            raise Exception(f"Failed to find reporting server: {e}")
    
    def get_stack_outputs(self) -> dict:
        """Get CloudFormation stack outputs."""
        try:
            logger.info(f"📋 Getting CloudFormation stack outputs for: {self.stack_name}")
            
            response = self.cf_client.describe_stacks(StackName=self.stack_name)
            
            if not response['Stacks']:
                raise Exception(f"Stack {self.stack_name} not found")
            
            stack = response['Stacks'][0]
            outputs = {}
            
            if 'Outputs' in stack:
                for output in stack['Outputs']:
                    outputs[output['OutputKey']] = output['OutputValue']
                    logger.info(f"  {output['OutputKey']}: {output['OutputValue']}")
            else:
                logger.info("  No outputs found in stack")
            
            return outputs
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ValidationError':
                logger.error(f"✗ Stack {self.stack_name} does not exist")
            else:
                logger.error(f"✗ Error getting stack outputs: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"✗ Error getting stack outputs: {e}")
            sys.exit(1)
    
    def execute_mysql_query_local(self, query, timeout=30):
        """
        Execute a MySQL query directly on the local machine (bastion).
        
        Args:
            query (str): SQL query to execute
            timeout (int): Query timeout in seconds
            
        Returns:
            tuple: (success, execution_time, output)
        """
        start_time = time.time()
        
        try:
            logger.debug(f"🔍 EXECUTING QUERY (LOCAL): {query}")
            logger.debug(f"   Path: This Reporting Server → RDS ({self.db_host}:3306)")
            
            # Build MySQL command
            mysql_cmd = [
                'mysql',
                '-h', self.db_host,
                '-P', '3306',
                '-u', self.db_user,
                f'-p{self.db_password}',
                '-D', self.db_name,
                '-e', query,
                '-v'
            ]
            
            # Execute MySQL command
            result = subprocess.run(
                mysql_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            query_time = time.time() - start_time
            
            if result.returncode == 0:
                self.stats['successful_queries'] += 1
                logger.debug(f"✅ QUERY SUCCESS ({query_time:.2f}s)")
                return True, query_time, result.stdout
            else:
                self.stats['failed_queries'] += 1
                error_output = (result.stdout + '\n' + result.stderr).lower()
                
                logger.warning(f"❌ QUERY FAILED ({query_time:.2f}s)")
                
                # Check for connection-related errors
                if any(keyword in error_output for keyword in ['timeout', 'connection', 'lost connection', "can't connect", 'error 2003', 'error 2013']):
                    self.stats['connection_errors'] += 1
                    self.stats['retransmission_indicators'] += 1
                    logger.warning(f"🔍 Connection issue detected - TCP retransmissions likely")
                
                return False, query_time, result.stderr
                
        except subprocess.TimeoutExpired:
            query_time = time.time() - start_time
            self.stats['timeout_errors'] += 1
            self.stats['retransmission_indicators'] += 1
            logger.warning(f"⏰ QUERY TIMEOUT ({query_time:.2f}s)")
            return False, query_time, f"Query timed out after {timeout}s"
            
        except Exception as e:
            query_time = time.time() - start_time
            self.stats['failed_queries'] += 1
            logger.error(f"💥 UNEXPECTED ERROR ({query_time:.2f}s): {e}")
            return False, query_time, str(e)
    
    def execute_mysql_query_ssm(self, query, timeout=30):
        """
        Execute a MySQL query via SSM on the reporting server.
        
        Args:
            query (str): SQL query to execute
            timeout (int): Query timeout in seconds
            
        Returns:
            tuple: (success, execution_time, output)
        """
        start_time = time.time()
        
        if not self.reporting_instance_id:
            logger.error("No reporting server available")
            return False, 0, "No reporting server available"
        
        # Implement exponential backoff for throttling
        max_retries = 5
        base_delay = 1
        
        for attempt in range(max_retries):
            try:
                # Wait for rate limiter before making SSM API call
                self.rate_limiter.wait_if_needed()
                
                # Escape the query for shell execution
                escaped_query = query.replace("'", "'\"'\"'")
                
                # Build MySQL command
                mysql_command = f"""
mysql -h {self.db_host} -P 3306 -u {self.db_user} -p'{self.db_password}' -D {self.db_name} -e '{escaped_query}' -v 2>&1
exit $?
"""
                
                logger.info(f"🔍 EXECUTING QUERY (SSM): {query[:100]}...")
                logger.info(f"   Target: Reporting Server ({self.reporting_instance_id}) → RDS ({self.db_host})")
                if attempt > 0:
                    logger.info(f"   Retry attempt: {attempt + 1}/{max_retries}")
                
                # Execute command via SSM
                response = self.ssm_client.send_command(
                    InstanceIds=[self.reporting_instance_id],
                    DocumentName='AWS-RunShellScript',
                    Parameters={
                        'commands': [mysql_command],
                        'executionTimeout': [str(timeout)]
                    },
                    TimeoutSeconds=max(30, timeout + 10)
                )
                
                command_id = response['Command']['CommandId']
                break
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'ThrottlingException':
                    self.stats['throttling_errors'] += 1
                    
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(f"⚠️  SSM API throttled, retrying in {delay:.2f}s...")
                        time.sleep(delay)
                        continue
                    else:
                        query_time = time.time() - start_time
                        self.stats['failed_queries'] += 1
                        return False, query_time, "SSM API throttling - max retries exceeded"
                else:
                    raise e
            
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"⚠️  Error submitting command, retrying in {delay:.2f}s...")
                    time.sleep(delay)
                    continue
                else:
                    self.stats['failed_queries'] += 1
                    query_time = time.time() - start_time
                    return False, query_time, str(e)
        
        # Wait for command to complete
        max_wait_time = timeout + 15
        wait_time = 0
        while wait_time < max_wait_time:
            try:
                result = self.ssm_client.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=self.reporting_instance_id
                )
                
                status = result['Status']
                if status in ['Success', 'Failed', 'Cancelled', 'TimedOut']:
                    break
                    
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvocationDoesNotExist':
                    time.sleep(2)
                    wait_time += 2
                    continue
                else:
                    raise e
            
            time.sleep(2)
            wait_time += 2
        
        query_time = time.time() - start_time
        
        # Get final result
        try:
            result = self.ssm_client.get_command_invocation(
                CommandId=command_id,
                InstanceId=self.reporting_instance_id
            )
            
            if result['Status'] == 'Success':
                self.stats['successful_queries'] += 1
                output = result.get('StandardOutputContent', '')
                logger.debug(f"✅ QUERY SUCCESS ({query_time:.2f}s)")
                return True, query_time, output
            else:
                self.stats['failed_queries'] += 1
                stdout_content = result.get('StandardOutputContent', '')
                stderr_content = result.get('StandardErrorContent', '')
                full_error = f"STDOUT:\n{stdout_content}\n\nSTDERR:\n{stderr_content}"
                error_output = (stdout_content + '\n' + stderr_content).lower()
                
                logger.warning(f"❌ QUERY FAILED ({query_time:.2f}s)")
                logger.warning(f"   Query: {query[:100]}...")
                logger.warning(f"   Error: {stderr_content[:200]}")
                
                # Check for connection-related errors
                if any(keyword in error_output for keyword in ['timeout', 'connection', 'lost connection', "can't connect", 'error 2003', 'error 2013']):
                    self.stats['connection_errors'] += 1
                    self.stats['retransmission_indicators'] += 1
                    logger.warning(f"🔍 Connection issue detected - TCP retransmissions likely")
                
                return False, query_time, full_error
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvocationDoesNotExist':
                self.stats['timeout_errors'] += 1
                logger.warning(f"⏰ QUERY TIMEOUT ({query_time:.2f}s)")
                return False, query_time, "Command timeout"
            else:
                raise e
    
    def execute_mysql_query(self, query, timeout=30):
        """Execute MySQL query using the appropriate method based on mode."""
        if self.local_mode:
            return self.execute_mysql_query_local(query, timeout)
        else:
            return self.execute_mysql_query_ssm(query, timeout)
    
    def test_basic_connectivity(self):
        """Test basic connectivity to database"""
        logger.info("=== Testing Basic Connectivity ===")
        
        success, query_time, output = self.execute_mysql_query("SELECT 1 as test;")
        if success:
            logger.info(f"✅ Database connectivity test successful ({query_time:.2f}s)")
        else:
            logger.warning(f"⚠️ Database connectivity test failed")
            logger.info(f"Error: {output[:200]}")
    
    def generate_aggressive_retransmission_traffic(self, worker_id, duration_seconds):
        """Generate aggressive traffic patterns designed to cause retransmissions"""
        logger.info(f"Aggressive Worker {worker_id} starting for {duration_seconds}s")
        
        # Queries designed to stress TCP buffers
        aggressive_queries = [
            "SELECT REPEAT('RETRANSMISSION_TEST_DATA_', 100) as large_data FROM images LIMIT 50;",
            "SELECT CONCAT(title, ' - ', description, ' - ', REPEAT('BUFFER_FILL_', 50)) as large_text FROM images LIMIT 30;",
            "SELECT * FROM images i CROSS JOIN (SELECT 1 as dummy UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5) d LIMIT 100;",
            "SELECT SLEEP(2) as delay, COUNT(*) as count FROM images;",
            "SELECT SLEEP(1) as delay, id, title FROM images ORDER BY RAND() LIMIT 20;",
            "SELECT i.*, ii.*, REPEAT('STRESS_TEST_', 20) as padding FROM images i LEFT JOIN image_interactions ii ON i.id = ii.image_id LIMIT 75;",
            "SELECT REPEAT('A', 500) as col1, REPEAT('B', 500) as col2, REPEAT('C', 500) as col3 FROM images LIMIT 25;",
            "SELECT CONCAT(REPEAT('RETRANS_', 100), id) as stress_data FROM images;",
        ]
        
        start_time = time.time()
        worker_queries = 0
        retransmissions_generated = 0
        
        while self.running and (time.time() - start_time) < duration_seconds:
            try:
                query = random.choice(aggressive_queries)
                logger.info(f"Worker {worker_id}: Executing query #{worker_queries + 1}")
                success, query_time, output = self.execute_mysql_query(query, timeout=8)
                worker_queries += 1
                
                if success:
                    logger.info(f"✅ Worker {worker_id}: Query #{worker_queries} succeeded ({query_time:.2f}s)")
                else:
                    retransmissions_generated += 1
                    logger.warning(f"❌ Worker {worker_id}: Query #{worker_queries} failed ({query_time:.2f}s)")
                    if retransmissions_generated % 10 == 0:
                        logger.info(f"🔥 Worker {worker_id}: Retransmission #{retransmissions_generated} (Query {worker_queries})")
                
                time.sleep(random.uniform(0.5, 1.0))
                
            except Exception as e:
                logger.error(f"Worker {worker_id}: Error: {e}")
                retransmissions_generated += 1
                time.sleep(0.5)
        
        logger.info(f"🔥 Worker {worker_id} completed: {worker_queries} queries, {retransmissions_generated} retransmissions")
        return retransmissions_generated
    
    def print_statistics(self):
        """Print current statistics"""
        total_queries = self.stats['successful_queries'] + self.stats['failed_queries']
        success_rate = (self.stats['successful_queries'] / total_queries * 100) if total_queries > 0 else 0
            
        logger.info("=== Traffic Generation Statistics ===")
        logger.info(f"Total queries: {total_queries}")
        logger.info(f"Successful queries: {self.stats['successful_queries']}")
        logger.info(f"Failed queries: {self.stats['failed_queries']}")
        logger.info(f"Success rate: {success_rate:.1f}%")
        logger.info(f"Connection errors: {self.stats['connection_errors']}")
        logger.info(f"Timeout errors: {self.stats['timeout_errors']}")
        logger.info(f"Retransmission indicators: {self.stats['retransmission_indicators']}")
        
        if self.stats['timeout_errors'] > 0 or self.stats['connection_errors'] > 0:
            logger.info("🔍 Network issues detected - check Network Flow Monitor!")
    
    def run_continuous_traffic(self, duration_minutes=10, num_workers=6):
        """Run continuous database traffic generation"""
        mode_str = "LOCAL MODE" if self.local_mode else "SSM MODE"
        logger.info(f"=== Starting AGGRESSIVE Retransmission Traffic Generation ({mode_str}) ===")
        logger.info(f"Duration: {duration_minutes} minutes")
        logger.info(f"Workers: {num_workers}")
        logger.info(f"Traffic Path: Reporting Server → RDS ({self.db_host}:3306)")
        logger.info("🔥 AGGRESSIVE MODE: Designed to generate 100+ retransmissions")
        logger.info("")
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Test basic connectivity first
        self.test_basic_connectivity()
        logger.info("")
        
        # Start aggressive worker threads
        duration_seconds = duration_minutes * 60
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = []
            for worker_id in range(num_workers):
                future = executor.submit(
                    self.generate_aggressive_retransmission_traffic,
                    worker_id,
                    duration_seconds
                )
                futures.append(future)
            
            # Monitor progress
            start_time = time.time()
            last_stats_time = start_time
            
            try:
                while self.running and (time.time() - start_time) < duration_seconds:
                    time.sleep(15)
                    
                    if time.time() - last_stats_time >= 30:
                        self.print_statistics()
                        elapsed_time = time.time() - start_time
                        remaining_time = duration_seconds - elapsed_time
                        logger.info(f"⏱️  Time remaining: {remaining_time:.0f}s")
                        last_stats_time = time.time()
                        logger.info("")
                
                logger.info("Waiting for workers to complete...")
                for future in as_completed(futures, timeout=60):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"Worker error: {e}")
                        
            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                self.running = False
        
        # Final statistics
        logger.info("")
        logger.info("=== FINAL STATISTICS ===")
        self.print_statistics()
        
        total_issues = self.stats['retransmission_indicators'] + self.stats['connection_errors'] + self.stats['timeout_errors']
        logger.info(f"🎯 TOTAL RETRANSMISSION ISSUES: {total_issues}")
        
        if total_issues >= 100:
            logger.info("✅ SUCCESS: Generated 100+ retransmission issues!")
        else:
            logger.warning(f"⚠️  Generated {total_issues} issues (target: 100+)")


def main():
    parser = argparse.ArgumentParser(
        description='Generate continuous database traffic - Dual Mode with Background Support',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  # Run from local machine via SSM (default):
  python3 %(prog)s --duration 15 --workers 6
  
  # Run SSM mode in background:
  python3 %(prog)s --background --duration 15 --workers 6
  
  # Run directly on reporting server (local mode):
  python3 %(prog)s --local-mode --db-host sample-app-image-metadata-db.xxx.rds.amazonaws.com --db-password ReInvent2025! --duration 15
  
  # Run local mode in background:
  python3 %(prog)s --local-mode --db-host RDS_ENDPOINT --db-password PASSWORD --background

Background Mode:
  Logs: {LOGFILE}
  Errors: {ERRFILE}
  PID: {PIDFILE}
  
  To stop: kill $(cat {PIDFILE})
  To check status: ps -p $(cat {PIDFILE})
        """
    )
    
    # Mode selection
    parser.add_argument('--local-mode', action='store_true', 
                       help='Run directly on reporting server (no SSM). Requires --db-host and --db-password')
    parser.add_argument('--background', action='store_true',
                       help='Run in background as daemon process (works with both SSM and local modes)')
    
    # Common parameters
    parser.add_argument('--duration', type=int, default=15, 
                       help='Duration in minutes (default: 15)')
    parser.add_argument('--workers', type=int, default=6, 
                       help='Number of worker threads (default: 6)')
    
    # Local mode parameters
    parser.add_argument('--db-host', 
                       help='Database host (required for --local-mode)')
    parser.add_argument('--db-user', default='admin', 
                       help='Database username (default: admin)')
    parser.add_argument('--db-password', 
                       help='Database password (required for --local-mode)')
    parser.add_argument('--db-name', default='image_metadata', 
                       help='Database name (default: image_metadata)')
    
    # SSM mode parameters
    parser.add_argument('--region', default='us-east-1', 
                       help='AWS region for SSM mode (default: us-east-1)')
    parser.add_argument('--stack-name', default='sample-application', 
                       help='CloudFormation stack name for SSM mode (default: sample-application)')
    
    args = parser.parse_args()
    
    # Check if already running
    is_running, existing_pid = check_if_running()
    if is_running:
        print(f"✗ Another instance is already running with PID: {existing_pid}")
        print(f"  To stop it: kill {existing_pid}")
        print(f"  Or remove stale PID file: rm {PIDFILE}")
        sys.exit(1)
    
    print("🔥 AGGRESSIVE RETRANSMISSION GENERATOR")
    print("=" * 50)
    
    if args.local_mode:
        print("🏠 MODE: LOCAL (Running directly on reporting server)")
        print(f"Database: {args.db_host}")
        print(f"Duration: {args.duration} minutes")
        print(f"Workers: {args.workers}")
        print("")
        
        if not args.db_host or not args.db_password:
            print("❌ ERROR: --local-mode requires --db-host and --db-password")
            sys.exit(1)
    else:
        print("☁️  MODE: SSM (Running from local machine)")
        print(f"Stack: {args.stack_name}")
        print(f"Region: {args.region}")
        print(f"Duration: {args.duration} minutes")
        print(f"Workers: {args.workers}")
        print("")
    
    if args.background:
        print("🚀 Starting in BACKGROUND mode...")
        print(f"   Log file: {os.path.abspath(LOGFILE)}")
        print(f"   Error file: {os.path.abspath(ERRFILE)}")
        print(f"   PID file: {os.path.abspath(PIDFILE)}")
        print("")
        print("To monitor progress:")
        print(f"   tail -f {LOGFILE}")
        print("")
        print("To stop the process:")
        print(f"   kill $(cat {PIDFILE})")
        print("")
        
        # Daemonize the process
        daemonize()
    else:
        print("Running in FOREGROUND mode (Ctrl+C to stop)")
        print("")
    
    try:
        generator = ContinuousDatabaseTrafficGenerator(
            local_mode=args.local_mode,
            db_host=args.db_host,
            db_user=args.db_user,
            db_password=args.db_password,
            db_name=args.db_name,
            stack_name=args.stack_name,
            region=args.region
        )
        
        generator.run_continuous_traffic(
            duration_minutes=args.duration,
            num_workers=args.workers
        )
        
        logger.info("Traffic generation completed successfully")
        if args.background:
            logger.info(f"Check logs at: {os.path.abspath(LOGFILE)}")
        
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
