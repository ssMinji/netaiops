"""
=============================================================================
Lambda Function - Datadog Integration MCP Tools (Module 6)
Lambda 함수 - Datadog 연동 MCP 도구 (모듈 6)
=============================================================================

Description (설명):
    Provides MCP tools for querying Datadog metrics, events, traces, and monitors.
    Datadog 메트릭, 이벤트, 트레이스, 모니터 조회를 위한 MCP 도구를 제공합니다.

Tools (도구):
    - datadog-query-metrics: Query timeseries metrics (시계열 메트릭 조회)
    - datadog-get-events: Get events and alert history (이벤트/알림 이력 조회)
    - datadog-get-traces: Get APM traces (APM 트레이스 조회)
    - datadog-get-monitors: Get monitor statuses (모니터 상태 조회)

Environment Variables (환경변수):
    DATADOG_API_KEY: Datadog API Key (from SSM)
    DATADOG_APP_KEY: Datadog Application Key (from SSM)
    DATADOG_SITE: Datadog site (default: datadoghq.com)

Author: NetAIOps Team
Module: workshop-module-6
=============================================================================
"""

import json
import os
import urllib3
from datetime import datetime, timedelta

# =============================================================================
# Configuration (설정)
# =============================================================================
DATADOG_API_KEY = os.environ.get("DATADOG_API_KEY", "")
DATADOG_APP_KEY = os.environ.get("DATADOG_APP_KEY", "")
DATADOG_SITE = os.environ.get("DATADOG_SITE", "datadoghq.com")
BASE_URL = f"https://api.{DATADOG_SITE}/api"

http = urllib3.PoolManager()

# =============================================================================
# Tool Schema Definitions (도구 스키마 정의)
# =============================================================================
TOOL_SCHEMAS = [
    {
        "name": "datadog-query-metrics",
        "description": "Query Datadog timeseries metrics (CPU, Memory, Latency, Error Rate). 시계열 메트릭을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Datadog metrics query (e.g., 'avg:system.cpu.user{service:web-app}')"
                },
                "from_ts": {
                    "type": "integer",
                    "description": "Start timestamp (Unix epoch seconds). Default: 1 hour ago"
                },
                "to_ts": {
                    "type": "integer",
                    "description": "End timestamp (Unix epoch seconds). Default: now"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "datadog-get-events",
        "description": "Get Datadog events and alert history. 이벤트 및 알림 이력을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags to filter events (e.g., 'service:web-app,env:prod')"
                },
                "priority": {
                    "type": "string",
                    "description": "Event priority filter: 'normal' or 'low'. Default: all",
                    "enum": ["normal", "low"]
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours back to search. Default: 24"
                }
            },
            "required": []
        }
    },
    {
        "name": "datadog-get-traces",
        "description": "Get APM traces for slow or error requests. 느린 요청이나 에러 트레이스를 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name to filter traces"
                },
                "operation": {
                    "type": "string",
                    "description": "Operation name filter (optional)"
                },
                "min_duration_ms": {
                    "type": "integer",
                    "description": "Minimum trace duration in milliseconds. Default: 1000"
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours back to search. Default: 1"
                },
                "status": {
                    "type": "string",
                    "description": "Trace status filter: 'error' or 'ok'",
                    "enum": ["error", "ok"]
                }
            },
            "required": ["service"]
        }
    },
    {
        "name": "datadog-get-monitors",
        "description": "Get Datadog monitor statuses. 모니터 상태를 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "monitor_tags": {
                    "type": "string",
                    "description": "Comma-separated tags to filter monitors"
                },
                "name_filter": {
                    "type": "string",
                    "description": "Filter monitors by name substring"
                }
            },
            "required": []
        }
    }
]


# =============================================================================
# Main Handler (메인 핸들러)
# =============================================================================
def _extract_tool_info(event):
    """Extract tool name and arguments from various event formats.
    MCP Gateway sends only arguments to Lambda - tool is inferred from args."""
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
        if "query" in event and ("from_ts" in event or "to_ts" in event or not "service" in event):
            tool_name = "datadog-query-metrics"
        elif "service" in event:
            tool_name = "datadog-get-traces"
        elif "monitor_tags" in event or "name_filter" in event:
            tool_name = "datadog-get-monitors"
        else:
            tool_name = "datadog-get-events"

    if "___" in tool_name:
        tool_name = tool_name.split("___", 1)[1]

    return tool_name, arguments


def lambda_handler(event, context):
    """Lambda entry point - routes to appropriate tool handler."""
    print(f"RAW_EVENT: {json.dumps(event, default=str)[:2000]}")
    tool_name, parameters = _extract_tool_info(event)
    print(f"EXTRACTED: tool_name={tool_name}, parameters={json.dumps(parameters, default=str)[:500]}")

    if tool_name == "__list_tools__":
        return {"tools": TOOL_SCHEMAS}

    handlers = {
        "datadog-query-metrics": handle_query_metrics,
        "datadog-get-events": handle_get_events,
        "datadog-get-traces": handle_get_traces,
        "datadog-get-monitors": handle_get_monitors,
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
def handle_query_metrics(params):
    """Query timeseries metrics from Datadog. 시계열 메트릭을 조회합니다."""
    query = params["query"]
    now = int(datetime.now().timestamp())
    from_ts = params.get("from_ts", now - 3600)
    to_ts = params.get("to_ts", now)

    response = _datadog_get("/v1/query", {
        "query": query,
        "from": str(from_ts),
        "to": str(to_ts),
    })

    if "errors" in response:
        return {"error": response["errors"]}

    # Format response for agent readability (에이전트 가독성을 위한 응답 포맷)
    series_list = response.get("series", [])
    results = []
    for series in series_list:
        metric_name = series.get("metric", "unknown")
        scope = series.get("scope", "")
        pointlist = series.get("pointlist", [])

        # Get last 10 data points for readability
        recent_points = pointlist[-10:] if len(pointlist) > 10 else pointlist
        formatted_points = []
        for point in recent_points:
            ts = datetime.fromtimestamp(point[0] / 1000).strftime("%Y-%m-%d %H:%M:%S")
            value = round(point[1], 4) if point[1] is not None else None
            formatted_points.append({"timestamp": ts, "value": value})

        results.append({
            "metric": metric_name,
            "scope": scope,
            "unit": series.get("unit", [{}])[0].get("name", "") if series.get("unit") else "",
            "data_points": formatted_points,
            "total_points": len(pointlist),
        })

    return {
        "status": "success",
        "query": query,
        "time_range": {
            "from": datetime.fromtimestamp(from_ts).strftime("%Y-%m-%d %H:%M:%S"),
            "to": datetime.fromtimestamp(to_ts).strftime("%Y-%m-%d %H:%M:%S"),
        },
        "series_count": len(results),
        "results": results,
    }


def handle_get_events(params):
    """Get events and alert history. 이벤트 및 알림 이력을 조회합니다."""
    hours = params.get("hours", 24)
    now = int(datetime.now().timestamp())
    start = now - (hours * 3600)

    query_params = {"start": str(start), "end": str(now)}

    tags = params.get("tags", "")
    if tags:
        query_params["tags"] = tags

    priority = params.get("priority")
    if priority:
        query_params["priority"] = priority

    response = _datadog_get("/v1/events", query_params)

    events = response.get("events", [])
    formatted_events = []
    for evt in events[:20]:  # Limit to 20 events
        formatted_events.append({
            "id": evt.get("id"),
            "title": evt.get("title", ""),
            "text": evt.get("text", "")[:500],  # Truncate long text
            "date": datetime.fromtimestamp(evt.get("date_happened", 0)).strftime("%Y-%m-%d %H:%M:%S"),
            "priority": evt.get("priority", ""),
            "source": evt.get("source", ""),
            "tags": evt.get("tags", []),
            "alert_type": evt.get("alert_type", ""),
        })

    return {
        "status": "success",
        "total_events": len(events),
        "showing": len(formatted_events),
        "time_range_hours": hours,
        "events": formatted_events,
    }


def handle_get_traces(params):
    """Get APM traces for analysis. APM 트레이스를 조회합니다."""
    service = params["service"]
    hours = params.get("hours", 1)
    min_duration = params.get("min_duration_ms", 1000)
    operation = params.get("operation", "")
    status = params.get("status", "")

    now = int(datetime.now().timestamp())
    start = now - (hours * 3600)

    # Build search query (검색 쿼리 구성)
    query = f"service:{service}"
    if operation:
        query += f" operation_name:{operation}"
    if status:
        query += f" status:{status}"
    if min_duration:
        query += f" @duration:>{min_duration * 1000000}"  # Convert ms to ns

    body = {
        "data": {
            "type": "search_request",
            "attributes": {
                "filter": {
                    "query": query,
                    "from": f"{start}000000000",  # nanoseconds
                    "to": f"{now}000000000",
                },
                "sort": "-timestamp",
                "page": {"limit": 20},
            }
        }
    }

    response = _datadog_post("/v2/spans/events/search", body)

    spans = response.get("data", [])
    formatted_traces = []
    for span in spans:
        attrs = span.get("attributes", {})
        formatted_traces.append({
            "trace_id": attrs.get("trace_id", ""),
            "span_id": attrs.get("span_id", ""),
            "service": attrs.get("service", ""),
            "operation": attrs.get("resource_name", ""),
            "duration_ms": round(attrs.get("duration", 0) / 1000000, 2),
            "status": attrs.get("status", ""),
            "timestamp": attrs.get("timestamp", ""),
            "error_message": attrs.get("meta", {}).get("error.message", ""),
        })

    return {
        "status": "success",
        "service": service,
        "query": query,
        "total_traces": len(formatted_traces),
        "traces": formatted_traces,
    }


def handle_get_monitors(params):
    """Get monitor statuses. 모니터 상태를 조회합니다."""
    query_params = {}
    tags = params.get("monitor_tags", "")
    if tags:
        query_params["monitor_tags"] = tags
    name = params.get("name_filter", "")
    if name:
        query_params["name"] = name

    response = _datadog_get("/v1/monitor", query_params)

    # Response is a list of monitors (응답은 모니터 목록)
    monitors = response if isinstance(response, list) else []
    formatted_monitors = []
    for mon in monitors[:30]:  # Limit to 30
        formatted_monitors.append({
            "id": mon.get("id"),
            "name": mon.get("name", ""),
            "type": mon.get("type", ""),
            "overall_state": mon.get("overall_state", ""),
            "query": mon.get("query", "")[:200],
            "message": mon.get("message", "")[:300],
            "tags": mon.get("tags", []),
            "created": mon.get("created", ""),
            "modified": mon.get("modified", ""),
        })

    # Summarize states (상태 요약)
    state_summary = {}
    for mon in formatted_monitors:
        state = mon["overall_state"]
        state_summary[state] = state_summary.get(state, 0) + 1

    return {
        "status": "success",
        "total_monitors": len(monitors),
        "showing": len(formatted_monitors),
        "state_summary": state_summary,
        "monitors": formatted_monitors,
    }


# =============================================================================
# HTTP Helpers (HTTP 헬퍼)
# =============================================================================
def _datadog_get(path, params):
    """Send GET request to Datadog API. Datadog API에 GET 요청을 보냅니다."""
    url = f"{BASE_URL}{path}"
    headers = {
        "DD-API-KEY": DATADOG_API_KEY,
        "DD-APPLICATION-KEY": DATADOG_APP_KEY,
        "Content-Type": "application/json",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items()) if params else ""
    full_url = f"{url}?{query}" if query else url

    resp = http.request("GET", full_url, headers=headers, timeout=30.0)
    return json.loads(resp.data.decode("utf-8"))


def _datadog_post(path, body):
    """Send POST request to Datadog API. Datadog API에 POST 요청을 보냅니다."""
    url = f"{BASE_URL}{path}"
    headers = {
        "DD-API-KEY": DATADOG_API_KEY,
        "DD-APPLICATION-KEY": DATADOG_APP_KEY,
        "Content-Type": "application/json",
    }
    resp = http.request("POST", url, body=json.dumps(body), headers=headers, timeout=30.0)
    return json.loads(resp.data.decode("utf-8"))
