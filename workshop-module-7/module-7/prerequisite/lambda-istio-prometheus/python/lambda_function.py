"""
=============================================================================
Lambda Function - Istio Prometheus MCP Tools (Module 7)
Lambda 함수 - Istio Prometheus MCP 도구 (모듈 7)
=============================================================================

Description (설명):
    Provides MCP tools for querying Istio service mesh metrics from
    Amazon Managed Prometheus (AMP).
    AMP에서 Istio 서비스 메시 메트릭을 조회하는 MCP 도구를 제공합니다.

Tools (도구):
    - istio-query-workload-metrics: RED metrics per workload (워크로드별 RED 메트릭)
    - istio-query-service-topology: Service dependency map (서비스 토폴로지)
    - istio-query-tcp-metrics: TCP connection metrics (TCP 연결 메트릭)
    - istio-query-control-plane-health: istiod health (컨트롤 플레인 상태)
    - istio-query-proxy-resource-usage: Envoy sidecar resources (Envoy 리소스)

Environment Variables (환경변수):
    AMP_QUERY_ENDPOINT: AMP query endpoint URL
    AWS_REGION: AWS region (default: us-east-1)

Author: NetAIOps Team
Module: workshop-module-7
=============================================================================
"""

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

# =============================================================================
# Configuration (설정)
# =============================================================================
REGION = os.environ.get("AWS_REGION", "us-east-1")

# AMP endpoint from environment or SSM
AMP_QUERY_ENDPOINT = os.environ.get("AMP_QUERY_ENDPOINT", "")
if not AMP_QUERY_ENDPOINT:
    try:
        ssm = boto3.client("ssm", region_name=REGION)
        resp = ssm.get_parameter(Name="/app/istio/agentcore/amp_query_endpoint")
        AMP_QUERY_ENDPOINT = resp["Parameter"]["Value"]
    except Exception:
        AMP_QUERY_ENDPOINT = ""

# Get AWS credentials for SigV4
session = boto3.Session()
credentials = session.get_credentials()
if credentials:
    credentials = credentials.get_frozen_credentials()

# =============================================================================
# Tool Schema Definitions (도구 스키마 정의)
# =============================================================================
TOOL_SCHEMAS = [
    {
        "name": "istio-query-workload-metrics",
        "description": "Query Istio RED (Rate, Error, Duration) metrics per workload. 워크로드별 Istio RED 메트릭을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace filter (optional, default: all)"
                },
                "workload": {
                    "type": "string",
                    "description": "Specific workload name filter (optional)"
                },
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes back to query. Default: 15"
                },
                "step": {
                    "type": "string",
                    "description": "Query step/resolution (e.g., '1m', '5m'). Default: '1m'"
                }
            },
            "required": []
        }
    },
    {
        "name": "istio-query-service-topology",
        "description": "Query Istio service-to-service traffic topology showing request rates and error codes between services. 서비스 간 트래픽 토폴로지를 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace filter (optional)"
                },
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes back to query. Default: 15"
                }
            },
            "required": []
        }
    },
    {
        "name": "istio-query-tcp-metrics",
        "description": "Query Istio TCP connection metrics (connections opened/closed, bytes sent/received). TCP 연결 메트릭을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace filter (optional)"
                },
                "workload": {
                    "type": "string",
                    "description": "Specific workload name filter (optional)"
                },
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes back to query. Default: 15"
                }
            },
            "required": []
        }
    },
    {
        "name": "istio-query-control-plane-health",
        "description": "Query Istio control plane (istiod) health metrics including xDS push latency, errors, and config conflicts. 컨트롤 플레인(istiod) 상태를 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes back to query. Default: 30"
                }
            },
            "required": []
        }
    },
    {
        "name": "istio-query-proxy-resource-usage",
        "description": "Query Envoy sidecar proxy resource usage (CPU, memory) across workloads. Envoy 사이드카 리소스 사용량을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace filter (optional)"
                },
                "minutes": {
                    "type": "integer",
                    "description": "How many minutes back to query. Default: 15"
                }
            },
            "required": []
        }
    }
]


# =============================================================================
# AMP Query Helper (AMP 쿼리 헬퍼)
# =============================================================================
def _amp_query(query: str, start: datetime, end: datetime, step: str = "1m") -> dict:
    """Execute a PromQL query_range against AMP with SigV4 auth.
    SigV4 인증을 사용하여 AMP에 PromQL query_range를 실행합니다."""
    if not AMP_QUERY_ENDPOINT:
        return {"error": "AMP_QUERY_ENDPOINT not configured"}

    url = f"{AMP_QUERY_ENDPOINT}/query_range"
    params = {
        "query": query,
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step": step,
    }

    query_string = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
    full_url = f"{url}?{query_string}"

    try:
        request = AWSRequest(
            method="GET",
            url=full_url,
            headers={"Host": urllib.request.urlparse(full_url).hostname},
        )
        SigV4Auth(credentials, "aps", REGION).add_auth(request)

        req = urllib.request.Request(
            full_url,
            headers=dict(request.headers),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": f"AMP query failed: {str(e)}", "query": query}


def _amp_instant_query(query: str) -> dict:
    """Execute an instant PromQL query against AMP.
    AMP에 즉시 PromQL 쿼리를 실행합니다."""
    if not AMP_QUERY_ENDPOINT:
        return {"error": "AMP_QUERY_ENDPOINT not configured"}

    url = f"{AMP_QUERY_ENDPOINT}/query"
    params = {"query": query}

    query_string = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
    full_url = f"{url}?{query_string}"

    try:
        request = AWSRequest(
            method="GET",
            url=full_url,
            headers={"Host": urllib.request.urlparse(full_url).hostname},
        )
        SigV4Auth(credentials, "aps", REGION).add_auth(request)

        req = urllib.request.Request(
            full_url,
            headers=dict(request.headers),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": f"AMP query failed: {str(e)}", "query": query}


def _format_series(result: dict, max_points: int = 10) -> list:
    """Format Prometheus query result into readable data.
    Prometheus 쿼리 결과를 읽기 쉬운 형태로 변환합니다."""
    formatted = []
    data = result.get("data", {})
    results = data.get("result", [])

    for series in results:
        metric = series.get("metric", {})
        values = series.get("values", [])
        # For instant queries
        if not values and "value" in series:
            values = [series["value"]]

        label_parts = []
        for k, v in metric.items():
            if k != "__name__":
                label_parts.append(f"{k}={v}")

        data_points = []
        for val in values[-max_points:]:
            if isinstance(val, list) and len(val) == 2:
                ts = datetime.fromtimestamp(val[0], tz=timezone.utc).strftime("%H:%M:%S")
                data_points.append({"time": ts, "value": round(float(val[1]), 4)})

        formatted.append({
            "labels": ", ".join(label_parts) if label_parts else metric.get("__name__", "unknown"),
            "data_points": data_points,
            "latest": data_points[-1]["value"] if data_points else None,
        })

    return formatted


# =============================================================================
# Main Handler (메인 핸들러)
# =============================================================================
def _extract_tool_info(event):
    """Extract tool name and arguments from various event formats.
    다양한 이벤트 형식에서 도구 이름과 인자를 추출합니다."""
    tool_name = ""
    arguments = {}

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
        arguments = event
        # Infer tool from argument patterns
        if "workload" in event and "namespace" in event:
            tool_name = "istio-query-workload-metrics"
        elif "workload" in event:
            tool_name = "istio-query-workload-metrics"
        else:
            tool_name = "istio-query-workload-metrics"

    if "___" in tool_name:
        tool_name = tool_name.split("___", 1)[1]

    return tool_name, arguments


def lambda_handler(event, context):
    """Lambda entry point. Lambda 진입점."""
    print(f"RAW_EVENT: {json.dumps(event, default=str)[:2000]}")
    tool_name, parameters = _extract_tool_info(event)
    print(f"EXTRACTED: tool_name={tool_name}, parameters={json.dumps(parameters, default=str)[:500]}")

    if tool_name == "__list_tools__":
        return {"tools": TOOL_SCHEMAS}

    handlers = {
        "istio-query-workload-metrics": handle_workload_metrics,
        "istio-query-service-topology": handle_service_topology,
        "istio-query-tcp-metrics": handle_tcp_metrics,
        "istio-query-control-plane-health": handle_control_plane_health,
        "istio-query-proxy-resource-usage": handle_proxy_resource_usage,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {
            "error": f"Unknown tool: {tool_name}",
            "available_tools": list(handlers.keys()),
            "raw_event_keys": list(event.keys()),
        }

    try:
        return handler(parameters)
    except Exception as e:
        return {"error": f"Tool execution failed: {str(e)}", "tool": tool_name}


# =============================================================================
# Tool Handlers (도구 핸들러)
# =============================================================================
def handle_workload_metrics(params):
    """Query Istio RED metrics per workload. 워크로드별 RED 메트릭을 조회합니다."""
    namespace = params.get("namespace", "")
    workload = params.get("workload", "")
    minutes = params.get("minutes", 15)
    step = params.get("step", "1m")

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    # Build label filter
    label_filter = ""
    if namespace:
        label_filter += f', destination_workload_namespace="{namespace}"'
    if workload:
        label_filter += f', destination_workload="{workload}"'

    results = {}

    # Request Rate (요청 비율)
    rate_query = f'sum(rate(istio_requests_total{{{label_filter.lstrip(", ")}}}[5m])) by (destination_workload, destination_workload_namespace, response_code)'
    rate_result = _amp_query(rate_query, start, end, step)
    if "error" not in rate_result:
        results["request_rate"] = {
            "description": "Requests per second by workload and response code",
            "query": rate_query,
            "series": _format_series(rate_result),
        }

    # Error Rate (에러 비율)
    error_query = f'sum(rate(istio_requests_total{{response_code=~"5.."{label_filter}}}[5m])) by (destination_workload, destination_workload_namespace) / sum(rate(istio_requests_total{{{label_filter.lstrip(", ")}}}[5m])) by (destination_workload, destination_workload_namespace)'
    error_result = _amp_query(error_query, start, end, step)
    if "error" not in error_result:
        results["error_rate"] = {
            "description": "5xx error rate ratio (0-1) by workload",
            "query": error_query,
            "series": _format_series(error_result),
        }

    # P50 Latency (P50 지연)
    p50_query = f'histogram_quantile(0.50, sum(rate(istio_request_duration_milliseconds_bucket{{{label_filter.lstrip(", ")}}}[5m])) by (le, destination_workload, destination_workload_namespace))'
    p50_result = _amp_query(p50_query, start, end, step)
    if "error" not in p50_result:
        results["p50_latency_ms"] = {
            "description": "P50 request duration in milliseconds",
            "query": p50_query,
            "series": _format_series(p50_result),
        }

    # P99 Latency (P99 지연)
    p99_query = f'histogram_quantile(0.99, sum(rate(istio_request_duration_milliseconds_bucket{{{label_filter.lstrip(", ")}}}[5m])) by (le, destination_workload, destination_workload_namespace))'
    p99_result = _amp_query(p99_query, start, end, step)
    if "error" not in p99_result:
        results["p99_latency_ms"] = {
            "description": "P99 request duration in milliseconds",
            "query": p99_query,
            "series": _format_series(p99_result),
        }

    return {
        "status": "success",
        "namespace": namespace or "all",
        "workload": workload or "all",
        "time_range_minutes": minutes,
        "metrics": results,
    }


def handle_service_topology(params):
    """Query service-to-service traffic topology. 서비스 간 트래픽 토폴로지를 조회합니다."""
    namespace = params.get("namespace", "")
    minutes = params.get("minutes", 15)

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    label_filter = ""
    if namespace:
        label_filter = f'source_workload_namespace="{namespace}"'

    # Service topology with request rates and response codes
    topo_query = f'sum(rate(istio_requests_total{{{label_filter}}}[5m])) by (source_workload, source_workload_namespace, destination_workload, destination_workload_namespace, response_code)'
    topo_result = _amp_query(topo_query, start, end, "5m")

    edges = []
    if "error" not in topo_result:
        for series in topo_result.get("data", {}).get("result", []):
            metric = series.get("metric", {})
            values = series.get("values", [])
            latest_value = float(values[-1][1]) if values else 0

            edges.append({
                "source": f"{metric.get('source_workload_namespace', 'unknown')}/{metric.get('source_workload', 'unknown')}",
                "destination": f"{metric.get('destination_workload_namespace', 'unknown')}/{metric.get('destination_workload', 'unknown')}",
                "response_code": metric.get("response_code", "unknown"),
                "request_rate": round(latest_value, 4),
            })

    # Sort by request rate descending
    edges.sort(key=lambda x: x["request_rate"], reverse=True)

    return {
        "status": "success",
        "namespace": namespace or "all",
        "time_range_minutes": minutes,
        "topology_edges": edges[:50],
        "total_edges": len(edges),
    }


def handle_tcp_metrics(params):
    """Query TCP connection metrics. TCP 연결 메트릭을 조회합니다."""
    namespace = params.get("namespace", "")
    workload = params.get("workload", "")
    minutes = params.get("minutes", 15)

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    label_filter = ""
    if namespace:
        label_filter += f'destination_workload_namespace="{namespace}"'
    if workload:
        if label_filter:
            label_filter += ", "
        label_filter += f'destination_workload="{workload}"'

    results = {}

    # TCP connections opened
    conn_open_query = f'sum(rate(istio_tcp_connections_opened_total{{{label_filter}}}[5m])) by (destination_workload, destination_workload_namespace)'
    conn_open_result = _amp_query(conn_open_query, start, end, "1m")
    if "error" not in conn_open_result:
        results["connections_opened_per_sec"] = {
            "description": "TCP connections opened per second",
            "series": _format_series(conn_open_result),
        }

    # TCP connections closed
    conn_close_query = f'sum(rate(istio_tcp_connections_closed_total{{{label_filter}}}[5m])) by (destination_workload, destination_workload_namespace)'
    conn_close_result = _amp_query(conn_close_query, start, end, "1m")
    if "error" not in conn_close_result:
        results["connections_closed_per_sec"] = {
            "description": "TCP connections closed per second",
            "series": _format_series(conn_close_result),
        }

    # TCP bytes sent
    bytes_sent_query = f'sum(rate(istio_tcp_sent_bytes_total{{{label_filter}}}[5m])) by (destination_workload, destination_workload_namespace)'
    bytes_sent_result = _amp_query(bytes_sent_query, start, end, "1m")
    if "error" not in bytes_sent_result:
        results["bytes_sent_per_sec"] = {
            "description": "TCP bytes sent per second",
            "series": _format_series(bytes_sent_result),
        }

    # TCP bytes received
    bytes_recv_query = f'sum(rate(istio_tcp_received_bytes_total{{{label_filter}}}[5m])) by (destination_workload, destination_workload_namespace)'
    bytes_recv_result = _amp_query(bytes_recv_query, start, end, "1m")
    if "error" not in bytes_recv_result:
        results["bytes_received_per_sec"] = {
            "description": "TCP bytes received per second",
            "series": _format_series(bytes_recv_result),
        }

    return {
        "status": "success",
        "namespace": namespace or "all",
        "workload": workload or "all",
        "time_range_minutes": minutes,
        "metrics": results,
    }


def handle_control_plane_health(params):
    """Query istiod control plane health. istiod 컨트롤 플레인 상태를 조회합니다."""
    minutes = params.get("minutes", 30)

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    results = {}

    # xDS push latency (P99)
    push_latency_query = 'histogram_quantile(0.99, sum(rate(pilot_proxy_convergence_time_bucket[5m])) by (le))'
    push_result = _amp_query(push_latency_query, start, end, "1m")
    if "error" not in push_result:
        results["xds_push_latency_p99_sec"] = {
            "description": "P99 xDS proxy convergence time in seconds",
            "series": _format_series(push_result),
        }

    # xDS push errors
    push_error_query = 'sum(rate(pilot_xds_push_errors[5m])) by (type)'
    push_error_result = _amp_query(push_error_query, start, end, "1m")
    if "error" not in push_error_result:
        results["xds_push_errors_per_sec"] = {
            "description": "xDS push errors per second by type",
            "series": _format_series(push_error_result),
        }

    # Pilot conflicts
    conflict_queries = {
        "listener_conflicts": "pilot_conflict_inbound_listener",
        "route_conflicts": "pilot_conflict_outbound_listener_http_over_current_tcp",
    }
    for metric_name, query_metric in conflict_queries.items():
        conflict_result = _amp_instant_query(query_metric)
        if "error" not in conflict_result:
            series = conflict_result.get("data", {}).get("result", [])
            total = sum(float(s.get("value", [0, 0])[1]) for s in series) if series else 0
            results[metric_name] = {
                "description": f"Current {metric_name.replace('_', ' ')} count",
                "value": total,
            }

    # Connected proxies
    proxy_query = 'sum(pilot_xds) by (pod)'
    proxy_result = _amp_instant_query(proxy_query)
    if "error" not in proxy_result:
        series = proxy_result.get("data", {}).get("result", [])
        total_proxies = sum(float(s.get("value", [0, 0])[1]) for s in series) if series else 0
        results["connected_proxies"] = {
            "description": "Total connected Envoy proxies",
            "value": total_proxies,
        }

    # Pilot CPU and memory
    pilot_cpu_query = 'rate(process_cpu_seconds_total{app="istiod"}[5m])'
    pilot_cpu_result = _amp_query(pilot_cpu_query, start, end, "1m")
    if "error" not in pilot_cpu_result:
        results["istiod_cpu_usage"] = {
            "description": "istiod CPU usage (cores)",
            "series": _format_series(pilot_cpu_result),
        }

    return {
        "status": "success",
        "time_range_minutes": minutes,
        "control_plane": results,
    }


def handle_proxy_resource_usage(params):
    """Query Envoy sidecar resource usage. Envoy 사이드카 리소스 사용량을 조회합니다."""
    namespace = params.get("namespace", "")
    minutes = params.get("minutes", 15)

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    ns_filter = f', namespace="{namespace}"' if namespace else ""

    results = {}

    # Envoy proxy memory
    mem_query = f'sum(container_memory_working_set_bytes{{container="istio-proxy"{ns_filter}}}) by (pod, namespace)'
    mem_result = _amp_query(mem_query, start, end, "1m")
    if "error" not in mem_result:
        results["proxy_memory_bytes"] = {
            "description": "Envoy proxy memory working set (bytes) per pod",
            "series": _format_series(mem_result),
        }

    # Envoy proxy CPU
    cpu_query = f'sum(rate(container_cpu_usage_seconds_total{{container="istio-proxy"{ns_filter}}}[5m])) by (pod, namespace)'
    cpu_result = _amp_query(cpu_query, start, end, "1m")
    if "error" not in cpu_result:
        results["proxy_cpu_cores"] = {
            "description": "Envoy proxy CPU usage (cores) per pod",
            "series": _format_series(cpu_result),
        }

    # Top consumers (aggregate by namespace)
    top_mem_query = f'topk(10, sum(container_memory_working_set_bytes{{container="istio-proxy"{ns_filter}}}) by (namespace))'
    top_mem_result = _amp_instant_query(top_mem_query)
    if "error" not in top_mem_result:
        top_consumers = []
        for series in top_mem_result.get("data", {}).get("result", []):
            metric = series.get("metric", {})
            value = series.get("value", [0, 0])
            top_consumers.append({
                "namespace": metric.get("namespace", "unknown"),
                "memory_bytes": round(float(value[1]), 0),
                "memory_mb": round(float(value[1]) / 1024 / 1024, 2),
            })
        results["top_memory_consumers"] = {
            "description": "Top 10 namespaces by Envoy proxy memory",
            "consumers": top_consumers,
        }

    return {
        "status": "success",
        "namespace": namespace or "all",
        "time_range_minutes": minutes,
        "proxy_resources": results,
    }
