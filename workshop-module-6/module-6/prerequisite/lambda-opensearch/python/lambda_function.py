"""
=============================================================================
Lambda Function - OpenSearch Integration MCP Tools (Module 6)
Lambda 함수 - OpenSearch 연동 MCP 도구 (모듈 6)
=============================================================================

Description (설명):
    Provides MCP tools for searching OpenSearch logs and detecting anomalies.
    OpenSearch 로그 검색 및 이상 탐지를 위한 MCP 도구를 제공합니다.

Tools (도구):
    - opensearch-search-logs: Search logs by keyword/pattern (로그 검색)
    - opensearch-anomaly-detection: Detect anomalous log patterns (이상 패턴 탐지)
    - opensearch-get-error-summary: Get error statistics by type (에러 통계 조회)

Environment Variables (환경변수):
    OPENSEARCH_ENDPOINT: OpenSearch domain endpoint URL
    AWS_REGION: AWS region (default: us-east-1)

Author: NetAIOps Team
Module: workshop-module-6
=============================================================================
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import urllib3

# =============================================================================
# Configuration (설정)
# =============================================================================
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")
REGION = os.environ.get("TARGET_REGION", os.environ.get("AWS_REGION", "us-east-1"))
SERVICE = os.environ.get("OPENSEARCH_SERVICE", "es")  # "es" for managed, "aoss" for serverless
AUTH_MODE = os.environ.get("OPENSEARCH_AUTH_MODE", "sigv4")  # "sigv4" or "basic"
OPENSEARCH_USER = os.environ.get("OPENSEARCH_USER", "")
OPENSEARCH_PASS = os.environ.get("OPENSEARCH_PASS", "")

http = urllib3.PoolManager()
session = boto3.Session()
credentials = session.get_credentials().get_frozen_credentials()

# =============================================================================
# Tool Schema Definitions (도구 스키마 정의)
# =============================================================================
TOOL_SCHEMAS = [
    {
        "name": "opensearch-search-logs",
        "description": "Search application logs by keyword or pattern. 키워드/패턴으로 로그를 검색합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "description": "OpenSearch index name or pattern (e.g., 'app-logs-*')"
                },
                "query": {
                    "type": "string",
                    "description": "Search query string (e.g., 'error AND timeout')"
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours back to search. Default: 1"
                },
                "size": {
                    "type": "integer",
                    "description": "Maximum number of results. Default: 50"
                }
            },
            "required": ["index", "query"]
        }
    },
    {
        "name": "opensearch-anomaly-detection",
        "description": "Detect anomalous log volume patterns over time. 시간별 로그 볼륨 이상 패턴을 탐지합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "description": "OpenSearch index name or pattern"
                },
                "field": {
                    "type": "string",
                    "description": "Field to analyze for anomalies (e.g., 'level', 'status_code'). Default: 'level'"
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours back to analyze. Default: 6"
                },
                "interval": {
                    "type": "string",
                    "description": "Bucket interval (e.g., '5m', '15m', '1h'). Default: '5m'"
                }
            },
            "required": ["index"]
        }
    },
    {
        "name": "opensearch-get-error-summary",
        "description": "Get error log statistics grouped by type. 에러 유형별 통계를 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "description": "OpenSearch index name or pattern"
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours back to search. Default: 24"
                },
                "group_by": {
                    "type": "string",
                    "description": "Field to group errors by. Default: 'error_type'"
                }
            },
            "required": ["index"]
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
        if "query" in event and "index" in event:
            tool_name = "opensearch-search-logs"
        elif "group_by" in event or (not "query" in event and not "interval" in event and not "field" in event and "index" in event and "hours" in event):
            tool_name = "opensearch-get-error-summary"
        elif "index" in event:
            tool_name = "opensearch-anomaly-detection"

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
        "opensearch-search-logs": handle_search_logs,
        "opensearch-anomaly-detection": handle_anomaly_detection,
        "opensearch-get-error-summary": handle_error_summary,
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
def handle_search_logs(params):
    """Search logs by keyword/pattern. 키워드/패턴으로 로그를 검색합니다."""
    index = params["index"]
    query_string = params["query"]
    hours = params.get("hours", 1)
    size = min(params.get("size", 50), 100)  # Cap at 100

    body = {
        "query": {
            "bool": {
                "must": [{"query_string": {"query": query_string}}],
                "filter": [{"range": {"@timestamp": {"gte": f"now-{hours}h", "lte": "now"}}}],
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": size,
    }

    response = _opensearch_request("POST", f"/{index}/_search", body)
    hits = response.get("hits", {})
    total = hits.get("total", {}).get("value", 0)

    formatted_logs = []
    for hit in hits.get("hits", []):
        source = hit.get("_source", {})
        formatted_logs.append({
            "timestamp": source.get("@timestamp", ""),
            "level": source.get("level", source.get("log_level", "")),
            "message": str(source.get("message", ""))[:500],
            "service": source.get("service", source.get("application", "")),
            "host": source.get("host", {}).get("name", source.get("hostname", "")),
            "index": hit.get("_index", ""),
        })

    return {
        "status": "success",
        "query": query_string,
        "index": index,
        "total_hits": total,
        "showing": len(formatted_logs),
        "time_range_hours": hours,
        "logs": formatted_logs,
    }


def handle_anomaly_detection(params):
    """Detect anomalous log patterns. 로그 이상 패턴을 탐지합니다."""
    index = params["index"]
    field = params.get("field", "level")
    hours = params.get("hours", 6)
    interval = params.get("interval", "5m")

    body = {
        "size": 0,
        "query": {"range": {"@timestamp": {"gte": f"now-{hours}h", "lte": "now"}}},
        "aggs": {
            "log_over_time": {
                "date_histogram": {"field": "@timestamp", "fixed_interval": interval},
                "aggs": {
                    "by_field": {"terms": {"field": field, "size": 10}},
                    "doc_count_derivative": {"derivative": {"buckets_path": "_count"}}
                }
            }
        }
    }

    response = _opensearch_request("POST", f"/{index}/_search", body)
    buckets = response.get("aggregations", {}).get("log_over_time", {}).get("buckets", [])

    # Analyze for anomalies (이상치 분석)
    counts = [b.get("doc_count", 0) for b in buckets]
    if len(counts) < 3:
        return {"status": "success", "message": "Not enough data for anomaly detection", "buckets": len(counts)}

    avg_count = sum(counts) / len(counts)
    std_dev = (sum((c - avg_count) ** 2 for c in counts) / len(counts)) ** 0.5
    threshold = avg_count + (2 * std_dev)  # 2 sigma threshold

    anomalies = []
    timeline = []
    for bucket in buckets:
        ts = bucket.get("key_as_string", "")
        count = bucket.get("doc_count", 0)
        is_anomaly = count > threshold if threshold > 0 else False

        field_breakdown = {}
        for fb in bucket.get("by_field", {}).get("buckets", []):
            field_breakdown[fb["key"]] = fb["doc_count"]

        entry = {"timestamp": ts, "count": count, "is_anomaly": is_anomaly, "breakdown": field_breakdown}
        timeline.append(entry)
        if is_anomaly:
            anomalies.append(entry)

    return {
        "status": "success",
        "index": index,
        "analysis_hours": hours,
        "interval": interval,
        "statistics": {
            "average_count": round(avg_count, 2),
            "std_deviation": round(std_dev, 2),
            "anomaly_threshold": round(threshold, 2),
            "total_buckets": len(buckets),
            "anomaly_count": len(anomalies),
        },
        "anomalies": anomalies,
        "timeline": timeline[-20:],  # Last 20 entries
    }


def handle_error_summary(params):
    """Get error statistics by type. 에러 유형별 통계를 조회합니다."""
    index = params["index"]
    hours = params.get("hours", 24)
    group_by = params.get("group_by", "error_type")

    body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [{"terms": {"level": ["ERROR", "FATAL", "error", "fatal", "CRITICAL"]}}],
                "filter": [{"range": {"@timestamp": {"gte": f"now-{hours}h", "lte": "now"}}}],
            }
        },
        "aggs": {
            "error_groups": {
                "terms": {"field": group_by, "size": 20, "order": {"_count": "desc"}},
                "aggs": {
                    "first_seen": {"min": {"field": "@timestamp"}},
                    "last_seen": {"max": {"field": "@timestamp"}},
                    "sample": {"top_hits": {"size": 1, "sort": [{"@timestamp": "desc"}]}},
                }
            },
            "total_errors": {"value_count": {"field": "@timestamp"}},
            "errors_over_time": {
                "date_histogram": {"field": "@timestamp", "fixed_interval": "1h"},
            }
        }
    }

    response = _opensearch_request("POST", f"/{index}/_search", body)
    aggs = response.get("aggregations", {})

    error_groups = []
    for bucket in aggs.get("error_groups", {}).get("buckets", []):
        sample_hit = bucket.get("sample", {}).get("hits", {}).get("hits", [{}])[0]
        sample_msg = sample_hit.get("_source", {}).get("message", "")[:300]

        error_groups.append({
            "error_type": bucket["key"],
            "count": bucket["doc_count"],
            "first_seen": bucket.get("first_seen", {}).get("value_as_string", ""),
            "last_seen": bucket.get("last_seen", {}).get("value_as_string", ""),
            "sample_message": sample_msg,
        })

    hourly_trend = []
    for bucket in aggs.get("errors_over_time", {}).get("buckets", []):
        hourly_trend.append({
            "timestamp": bucket.get("key_as_string", ""),
            "count": bucket.get("doc_count", 0),
        })

    return {
        "status": "success",
        "index": index,
        "time_range_hours": hours,
        "total_errors": aggs.get("total_errors", {}).get("value", 0),
        "error_types": len(error_groups),
        "groups": error_groups,
        "hourly_trend": hourly_trend[-24:],
    }


# =============================================================================
# OpenSearch HTTP Helper (OpenSearch HTTP 헬퍼)
# =============================================================================
def _opensearch_request(method, path, body=None):
    """Send request to OpenSearch. OpenSearch에 요청을 보냅니다."""
    url = f"https://{OPENSEARCH_ENDPOINT}{path}"

    encoded_body = json.dumps(body).encode("utf-8") if body else None

    if AUTH_MODE == "basic" and OPENSEARCH_USER and OPENSEARCH_PASS:
        # HTTP Basic Auth for Fine-Grained Access Control
        import base64
        basic_token = base64.b64encode(f"{OPENSEARCH_USER}:{OPENSEARCH_PASS}".encode()).decode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {basic_token}",
        }
    else:
        # SigV4 Auth for IAM-based access
        request = AWSRequest(method=method, url=url, data=encoded_body,
                             headers={"Content-Type": "application/json", "Host": OPENSEARCH_ENDPOINT})
        SigV4Auth(credentials, SERVICE, REGION).add_auth(request)
        headers = dict(request.headers)

    # Send request (요청 전송)
    resp = http.request(
        method, url,
        body=encoded_body,
        headers=headers,
        timeout=30.0,
    )
    return json.loads(resp.data.decode("utf-8"))
