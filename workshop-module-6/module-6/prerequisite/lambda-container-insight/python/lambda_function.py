"""
=============================================================================
Lambda Function - Container Insight MCP Tools (Module 6)
Lambda 함수 - Container Insight MCP 도구 (모듈 6)
=============================================================================

Description (설명):
    Provides MCP tools for querying EKS Container Insights metrics from CloudWatch.
    CloudWatch에서 EKS Container Insights 메트릭을 조회하는 MCP 도구를 제공합니다.

Tools (도구):
    - container-insight-pod-metrics: EKS pod metrics (파드 메트릭)
    - container-insight-node-metrics: EKS node metrics (노드 메트릭)
    - container-insight-cluster-overview: Cluster health overview (클러스터 상태 개요)

Environment Variables (환경변수):
    AWS_REGION: AWS region (default: us-east-1)

Author: NetAIOps Team
Module: workshop-module-6
=============================================================================
"""

import json
import os
import boto3
from datetime import datetime, timedelta

# =============================================================================
# Configuration (설정)
# =============================================================================
REGION = os.environ.get("TARGET_REGION", os.environ.get("AWS_REGION", "us-east-1"))
cw_client = boto3.client("cloudwatch", region_name=REGION)

# Container Insights namespace (Container Insights 네임스페이스)
CI_NAMESPACE = "ContainerInsights"

# =============================================================================
# Tool Schema Definitions (도구 스키마 정의)
# =============================================================================
TOOL_SCHEMAS = [
    {
        "name": "container-insight-pod-metrics",
        "description": "Get EKS pod CPU, Memory, Network metrics. EKS 파드 메트릭을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_name": {"type": "string", "description": "EKS cluster name"},
                "namespace": {"type": "string", "description": "Kubernetes namespace. Default: all namespaces"},
                "pod_name": {"type": "string", "description": "Specific pod name filter (optional)"},
                "minutes": {"type": "integer", "description": "How many minutes back. Default: 60"},
                "period": {"type": "integer", "description": "Metric period in seconds. Default: 300"}
            },
            "required": ["cluster_name"]
        }
    },
    {
        "name": "container-insight-node-metrics",
        "description": "Get EKS node resource utilization. EKS 노드 리소스 사용률을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_name": {"type": "string", "description": "EKS cluster name"},
                "node_name": {"type": "string", "description": "Specific node name (optional)"},
                "minutes": {"type": "integer", "description": "How many minutes back. Default: 60"},
                "period": {"type": "integer", "description": "Metric period in seconds. Default: 300"}
            },
            "required": ["cluster_name"]
        }
    },
    {
        "name": "container-insight-cluster-overview",
        "description": "Get cluster-wide health overview including node/pod counts and resource usage. 클러스터 전체 상태를 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_name": {"type": "string", "description": "EKS cluster name"},
                "minutes": {"type": "integer", "description": "How many minutes back. Default: 30"},
                "period": {"type": "integer", "description": "Metric period in seconds. Default: 300"}
            },
            "required": ["cluster_name"]
        }
    }
]


# =============================================================================
# Main Handler (메인 핸들러)
# =============================================================================
def _extract_tool_info(event):
    """Extract tool name and arguments from various event formats.
    다양한 이벤트 형식에서 도구 이름과 인자를 추출합니다.
    MCP Gateway sends only arguments to Lambda - tool is inferred from args."""
    tool_name = ""
    arguments = {}

    # MCP protocol format: {"method": "tools/call", "params": {"name": "...", "arguments": {...}}}
    method = event.get("method", "")
    if method == "tools/list":
        return "__list_tools__", {}
    if method == "tools/call":
        params = event.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
    elif "tool_name" in event:
        tool_name = event["tool_name"]
        arguments = event.get("parameters", {})
    elif "name" in event and "arguments" in event:
        tool_name = event["name"]
        arguments = event.get("arguments", {})
    elif event.get("action") == "list_tools":
        return "__list_tools__", {}
    else:
        # MCP Gateway Lambda integration: event IS the arguments directly
        # Infer tool from argument patterns
        arguments = event
        if "pod_name" in event or "namespace" in event:
            tool_name = "container-insight-pod-metrics"
        elif "node_name" in event:
            tool_name = "container-insight-node-metrics"
        elif "cluster_name" in event:
            tool_name = "container-insight-cluster-overview"

    if "___" in tool_name:
        tool_name = tool_name.split("___", 1)[1]

    return tool_name, arguments


def lambda_handler(event, context):
    print(f"RAW_EVENT: {json.dumps(event, default=str)[:2000]}")
    tool_name, parameters = _extract_tool_info(event)
    print(f"EXTRACTED: tool_name={tool_name}, parameters={json.dumps(parameters, default=str)[:500]}")

    if tool_name == "__list_tools__":
        return {"tools": TOOL_SCHEMAS}

    handlers = {
        "container-insight-pod-metrics": handle_pod_metrics,
        "container-insight-node-metrics": handle_node_metrics,
        "container-insight-cluster-overview": handle_cluster_overview,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}", "available_tools": list(handlers.keys()), "raw_event_keys": list(event.keys())}

    try:
        return handler(parameters)
    except Exception as e:
        return {"error": f"Tool execution failed: {str(e)}", "tool": tool_name}


# =============================================================================
# Tool Handlers (도구 핸들러)
# =============================================================================
def handle_pod_metrics(params):
    """Get pod-level metrics. 파드 레벨 메트릭을 조회합니다."""
    cluster = params["cluster_name"]
    namespace = params.get("namespace")
    pod_name = params.get("pod_name")
    minutes = params.get("minutes", 60)
    period = params.get("period", 300)

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=minutes)

    # Build dimensions (디멘전 구성)
    base_dimensions = [{"Name": "ClusterName", "Value": cluster}]
    if namespace:
        base_dimensions.append({"Name": "Namespace", "Value": namespace})
    if pod_name:
        base_dimensions.append({"Name": "PodName", "Value": pod_name})

    # Pod metrics to query (조회할 파드 메트릭)
    pod_metrics = [
        ("pod_cpu_utilization", "Percent", "CPU utilization"),
        ("pod_memory_utilization", "Percent", "Memory utilization"),
        ("pod_cpu_usage_total", "Millicore", "CPU usage (millicores)"),
        ("pod_memory_working_set", "Bytes", "Memory working set"),
        ("pod_network_rx_bytes", "Bytes/Second", "Network receive"),
        ("pod_network_tx_bytes", "Bytes/Second", "Network transmit"),
        ("pod_number_of_container_restarts", "Count", "Container restarts"),
    ]

    results = {}
    for metric_name, unit, description in pod_metrics:
        data = _get_metric_data(
            namespace=CI_NAMESPACE,
            metric_name=metric_name,
            dimensions=base_dimensions,
            start_time=start_time,
            end_time=end_time,
            period=period,
            stat="Average",
        )
        if data:
            results[metric_name] = {
                "description": description,
                "unit": unit,
                "data_points": data,
            }

    return {
        "status": "success",
        "cluster": cluster,
        "namespace": namespace or "all",
        "pod": pod_name or "all",
        "time_range_minutes": minutes,
        "metrics": results,
    }


def handle_node_metrics(params):
    """Get node-level metrics. 노드 레벨 메트릭을 조회합니다."""
    cluster = params["cluster_name"]
    node_name = params.get("node_name")
    minutes = params.get("minutes", 60)
    period = params.get("period", 300)

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=minutes)

    base_dimensions = [{"Name": "ClusterName", "Value": cluster}]
    if node_name:
        base_dimensions.append({"Name": "NodeName", "Value": node_name})

    # Node metrics to query (조회할 노드 메트릭)
    node_metrics = [
        ("node_cpu_utilization", "Percent", "CPU utilization"),
        ("node_memory_utilization", "Percent", "Memory utilization"),
        ("node_cpu_usage_total", "Millicore", "CPU usage (millicores)"),
        ("node_memory_working_set", "Bytes", "Memory working set"),
        ("node_filesystem_utilization", "Percent", "Filesystem utilization"),
        ("node_network_total_bytes", "Bytes/Second", "Total network I/O"),
        ("node_number_of_running_pods", "Count", "Running pods on node"),
    ]

    results = {}
    for metric_name, unit, description in node_metrics:
        data = _get_metric_data(
            namespace=CI_NAMESPACE,
            metric_name=metric_name,
            dimensions=base_dimensions,
            start_time=start_time,
            end_time=end_time,
            period=period,
            stat="Average",
        )
        if data:
            results[metric_name] = {
                "description": description,
                "unit": unit,
                "data_points": data,
            }

    return {
        "status": "success",
        "cluster": cluster,
        "node": node_name or "all",
        "time_range_minutes": minutes,
        "metrics": results,
    }


def handle_cluster_overview(params):
    """Get cluster-wide overview. 클러스터 전체 상태를 조회합니다."""
    cluster = params["cluster_name"]
    minutes = params.get("minutes", 30)
    period = params.get("period", 300)

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=minutes)

    base_dimensions = [{"Name": "ClusterName", "Value": cluster}]

    # Cluster-level metrics (클러스터 레벨 메트릭)
    cluster_metrics = [
        ("cluster_node_count", "Count", "Total nodes"),
        ("cluster_failed_node_count", "Count", "Failed nodes"),
        ("node_cpu_utilization", "Percent", "Avg node CPU"),
        ("node_memory_utilization", "Percent", "Avg node memory"),
        ("pod_cpu_utilization", "Percent", "Avg pod CPU"),
        ("pod_memory_utilization", "Percent", "Avg pod memory"),
        ("cluster_number_of_running_pods", "Count", "Running pods"),
    ]

    results = {}
    for metric_name, unit, description in cluster_metrics:
        data = _get_metric_data(
            namespace=CI_NAMESPACE,
            metric_name=metric_name,
            dimensions=base_dimensions,
            start_time=start_time,
            end_time=end_time,
            period=period,
            stat="Average",
        )
        if data:
            latest = data[-1] if data else None
            results[metric_name] = {
                "description": description,
                "unit": unit,
                "latest_value": latest.get("value") if latest else None,
                "latest_timestamp": latest.get("timestamp") if latest else None,
                "data_points": data,
            }

    return {
        "status": "success",
        "cluster": cluster,
        "time_range_minutes": minutes,
        "overview": results,
    }


# =============================================================================
# CloudWatch Helper (CloudWatch 헬퍼)
# =============================================================================
def _get_metric_data(namespace, metric_name, dimensions, start_time, end_time, period=300, stat="Average"):
    """Get CloudWatch metric data. CloudWatch 메트릭 데이터를 조회합니다."""
    try:
        response = cw_client.get_metric_data(
            MetricDataQueries=[
                {
                    "Id": "m1",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": namespace,
                            "MetricName": metric_name,
                            "Dimensions": dimensions,
                        },
                        "Period": period,
                        "Stat": stat,
                    },
                    "ReturnData": True,
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            ScanBy="TimestampAscending",
        )

        results = response.get("MetricDataResults", [])
        if not results or not results[0].get("Values"):
            return []

        timestamps = results[0]["Timestamps"]
        values = results[0]["Values"]

        data_points = []
        for ts, val in zip(timestamps, values):
            data_points.append({
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "value": round(val, 4),
            })

        # Sort by timestamp ascending
        data_points.sort(key=lambda x: x["timestamp"])
        return data_points

    except Exception as e:
        return [{"error": str(e)}]
