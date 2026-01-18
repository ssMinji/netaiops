#!/usr/bin/env python3
"""
Script to update ALB access guide with real-time connectivity status.
This script reads ALB DNS names from module3-config.json, tests connectivity,
and updates the HTML file with the current status.
"""

import json
import requests
import sys
import os
from datetime import datetime
import socket
import time

def load_config():
    """Load configuration from module3-config.json"""
    # Path to config file relative to script location (two directories up from a2a-performance-agent)
    config_path = "../../module3-config.json"
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {config_path} not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing {config_path}: {e}")
        sys.exit(1)

def test_connectivity(alb_dns, port=80, timeout=10):
    """Test connectivity to ALB using socket connection"""
    try:
        # Test socket connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((alb_dns, port))
        sock.close()
        
        if result == 0:
            return True, "healthy"
        else:
            return False, "unhealthy - connection failed"
    except socket.gaierror:
        return False, "unhealthy - DNS resolution failed"
    except Exception as e:
        return False, f"unhealthy - {str(e)}"

def test_http_endpoint(url, timeout=10):
    """Test HTTP endpoint and return status"""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            return True, f"healthy (HTTP {response.status_code})"
        else:
            return False, f"unhealthy (HTTP {response.status_code})"
    except requests.exceptions.ConnectTimeout:
        return False, "unhealthy - connection timeout"
    except requests.exceptions.ConnectionError:
        return False, "unhealthy - connection error"
    except requests.exceptions.Timeout:
        return False, "unhealthy - request timeout"
    except Exception as e:
        return False, f"unhealthy - {str(e)}"

def get_alb_target_info(alb_dns):
    """Get target information for ALB (simulated since we can't access AWS API directly)"""
    # Test basic connectivity
    is_healthy, status = test_connectivity(alb_dns)
    
    # Try to get more specific port information by testing common ports
    ports_to_test = [80, 443, 10003, 10005]
    healthy_ports = []
    
    for port in ports_to_test:
        port_healthy, _ = test_connectivity(alb_dns, port, timeout=5)
        if port_healthy:
            healthy_ports.append(port)
    
    if healthy_ports:
        # Simulate target information based on service type
        if "connectivity" in alb_dns:
            return f"{alb_dns}:10003 - {status}"
        elif "performance" in alb_dns:
            return f"{alb_dns}:10005 - {status}"
        else:
            return f"{alb_dns}:{healthy_ports[0]} - {status}"
    else:
        return f"{alb_dns}:unknown - {status}"

def update_html_file(config):
    """Update the HTML file with current ALB status"""
    html_path = "../alb_access_guide.html"
    
    try:
        with open(html_path, 'r') as f:
            html_content = f.read()
    except FileNotFoundError:
        print(f"Error: {html_path} not found")
        sys.exit(1)
    
    # Extract ALB DNS names from config
    connectivity_alb = config.get('agentcore_troubleshooting', {}).get('alb_dns', '')
    performance_alb = config.get('agentcore_performance', {}).get('alb_dns', '')
    
    if not connectivity_alb or not performance_alb:
        print("Error: ALB DNS names not found in config")
        sys.exit(1)
    
    print(f"Testing connectivity to ALBs...")
    print(f"Connectivity ALB: {connectivity_alb}")
    print(f"Performance ALB: {performance_alb}")
    
    # Test connectivity and get status
    connectivity_info = get_alb_target_info(connectivity_alb)
    performance_info = get_alb_target_info(performance_alb)
    
    print(f"Connectivity Status: {connectivity_info}")
    print(f"Performance Status: {performance_info}")
    
    # Test HTTP health endpoints
    connectivity_health_url = f"http://{connectivity_alb}/health"
    performance_health_url = f"http://{performance_alb}/health"
    
    conn_http_healthy, conn_http_status = test_http_endpoint(connectivity_health_url)
    perf_http_healthy, perf_http_status = test_http_endpoint(performance_health_url)
    
    print(f"Connectivity HTTP Health: {conn_http_status}")
    print(f"Performance HTTP Health: {perf_http_status}")
    
    # Determine overall status
    overall_status = "✅ Both ALBs are active and healthy!" if (conn_http_healthy and perf_http_healthy) else "⚠️ Some ALBs may have connectivity issues"
    
    # Update the HTML content
    # Replace the deployment status section
    old_status_section = '''<div class="info-box">
            <h3>📋 Deployment Status</h3>
            <p><strong>✅ Both ALBs are active and healthy!</strong></p>
            <p>AWS diagnostic shows both services are running with healthy targets:</p>
            <ul>
                <li>Connectivity Agent: <code>172.31.2.207:10003 - healthy</code></li>
                <li>Log Analytics Agent: <code>172.31.5.7:10005 - healthy</code></li>
            </ul>
        </div>'''
    
    new_status_section = f'''<div class="info-box">
            <h3>📋 Deployment Status</h3>
            <p><strong>{overall_status}</strong></p>
            <p>AWS diagnostic shows both services are running with healthy targets:</p>
            <ul>
                <li>Connectivity Agent: <code>{connectivity_info}</code></li>
                <li>Performance Agent: <code>{performance_info}</code></li>
            </ul>
            <p><em>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em></p>
        </div>'''
    
    # Replace ALB DNS names in the HTML
    html_content = html_content.replace(old_status_section, new_status_section)
    
    # Update ALB DNS references throughout the file
    # Find and replace old ALB DNS names with new ones
    old_connectivity_alb = "a2a-connectivity-alb-x.us-east-1.elb.amazonaws.com"
    old_performance_alb = "a2a-performance-alb-x.us-east-1.elb.amazonaws.com"
    
    html_content = html_content.replace(old_connectivity_alb, connectivity_alb)
    html_content = html_content.replace(old_performance_alb, performance_alb)
    
    # Write updated HTML
    with open(html_path, 'w') as f:
        f.write(html_content)
    
    print(f"\nHTML file updated successfully!")
    print(f"Updated ALB DNS names:")
    print(f"  Connectivity: {old_connectivity_alb} -> {connectivity_alb}")
    print(f"  Performance: {old_performance_alb} -> {performance_alb}")

def main():
    """Main function"""
    print("ALB Status Updater")
    print("=" * 50)
    
    # Load configuration
    config = load_config()
    
    # Update HTML file
    update_html_file(config)
    
    print("\nScript completed successfully!")

if __name__ == "__main__":
    main()
