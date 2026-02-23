"""
=============================================================================
Lambda Function - GitHub Integration MCP Tools (Module 6)
Lambda 함수 - GitHub 연동 MCP 도구 (모듈 6)
=============================================================================

Description (설명):
    Provides MCP tools for creating GitHub issues and adding comments for incident reports.
    인시던트 리포트를 위한 GitHub 이슈 생성 및 코멘트 추가 MCP 도구를 제공합니다.

Tools (도구):
    - github-create-issue: Create a new GitHub issue for an incident (인시던트 이슈 생성)
    - github-add-comment: Add a comment to an existing GitHub issue (이슈 코멘트 추가)
    - github-list-issues: List recent incident issues (인시던트 이슈 목록 조회)

Environment Variables (환경변수):
    GITHUB_PAT_SSM_PARAM: SSM parameter name for GitHub PAT (default: /app/incident/github/pat)
    GITHUB_REPO_SSM_PARAM: SSM parameter name for repo (default: /app/incident/github/repo)
    AWS_REGION: AWS region (default: us-east-1)

Author: NetAIOps Team
Module: workshop-module-6
=============================================================================
"""

import json
import os
import urllib3
import boto3

# =============================================================================
# Configuration (설정)
# =============================================================================
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
GITHUB_PAT_SSM_PARAM = os.environ.get("GITHUB_PAT_SSM_PARAM", "/app/incident/github/pat")
GITHUB_REPO_SSM_PARAM = os.environ.get("GITHUB_REPO_SSM_PARAM", "/app/incident/github/repo")
GITHUB_API_BASE = "https://api.github.com"

# Module-level cache for SSM parameters (Lambda cold start optimization)
# SSM 파라미터를 위한 모듈 레벨 캐시 (Lambda 콜드 스타트 최적화)
_github_pat = None
_github_repo = None

http = urllib3.PoolManager()

# =============================================================================
# Tool Schema Definitions (도구 스키마 정의)
# =============================================================================
TOOL_SCHEMAS = [
    {
        "name": "github-create-issue",
        "description": "Create a new GitHub issue for an incident. 인시던트를 위한 새 GitHub 이슈를 생성합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Issue title (e.g., '[Incident] CPU 급증 - netaiops-eks-cluster')"
                },
                "body": {
                    "type": "string",
                    "description": "Issue body in markdown format (analysis report)"
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to add (default: ['incident', 'auto-analysis'])"
                }
            },
            "required": ["title", "body"]
        }
    },
    {
        "name": "github-add-comment",
        "description": "Add a comment to an existing GitHub issue. 기존 GitHub 이슈에 코멘트를 추가합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_number": {
                    "type": "integer",
                    "description": "Issue number to comment on"
                },
                "body": {
                    "type": "string",
                    "description": "Comment body in markdown"
                }
            },
            "required": ["issue_number", "body"]
        }
    },
    {
        "name": "github-list-issues",
        "description": "List recent incident issues. 최근 인시던트 이슈 목록을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "description": "Issue state: 'open' or 'closed' (default: 'open')",
                    "enum": ["open", "closed", "all"]
                },
                "labels": {
                    "type": "string",
                    "description": "Comma-separated labels to filter (default: 'incident')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max issues to return (default: 10)"
                }
            },
            "required": []
        }
    }
]


# =============================================================================
# SSM Helper (SSM 헬퍼)
# =============================================================================
def _load_github_config():
    """Load GitHub PAT and repo from SSM on cold start (with caching).
    콜드 스타트 시 SSM에서 GitHub PAT와 repo를 로드합니다 (캐싱 적용)."""
    global _github_pat, _github_repo

    if _github_pat and _github_repo:
        return  # Already loaded (이미 로드됨)

    ssm_client = boto3.client("ssm", region_name=AWS_REGION)

    try:
        # Get GitHub PAT with decryption (GitHub PAT를 복호화하여 가져오기)
        pat_response = ssm_client.get_parameter(
            Name=GITHUB_PAT_SSM_PARAM,
            WithDecryption=True
        )
        _github_pat = pat_response["Parameter"]["Value"]

        # Get GitHub repo (GitHub repo 가져오기)
        repo_response = ssm_client.get_parameter(Name=GITHUB_REPO_SSM_PARAM)
        _github_repo = repo_response["Parameter"]["Value"]

        print(f"Loaded GitHub config: repo={_github_repo}, pat_length={len(_github_pat)}")
    except Exception as e:
        print(f"Failed to load GitHub config from SSM: {str(e)}")
        raise


# =============================================================================
# GitHub API Helpers (GitHub API 헬퍼)
# =============================================================================
def _github_request(method, path, body=None, params=None):
    """Make a GitHub API request using urllib3.
    urllib3을 사용하여 GitHub API 요청을 수행합니다.

    Args:
        method: HTTP method (GET, POST)
        path: API path (e.g., '/repos/owner/repo/issues')
        body: Request body dict (will be JSON encoded)
        params: Query parameters dict

    Returns:
        Response dict or raises exception
    """
    _load_github_config()  # Ensure config is loaded (설정이 로드되었는지 확인)

    url = f"{GITHUB_API_BASE}{path}"

    headers = {
        "Authorization": f"Bearer {_github_pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }

    # Build query string (쿼리 문자열 생성)
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query_string}"

    # Encode body if present (본문이 있으면 인코딩)
    encoded_body = None
    if body:
        encoded_body = json.dumps(body).encode("utf-8")

    # Make request (요청 수행)
    response = http.request(
        method,
        url,
        body=encoded_body,
        headers=headers,
        timeout=30.0
    )

    # Parse response (응답 파싱)
    response_data = json.loads(response.data.decode("utf-8"))

    if response.status >= 400:
        raise Exception(f"GitHub API error {response.status}: {response_data.get('message', 'Unknown error')}")

    return response_data


# =============================================================================
# Main Handler (메인 핸들러)
# =============================================================================
def _extract_tool_info(event):
    """Extract tool name and arguments from various event formats.
    다양한 이벤트 형식에서 도구 이름과 인자를 추출합니다.

    MCP Gateway sends only arguments to Lambda - we must infer tool from args.
    MCP 게이트웨이는 인자만 Lambda에 전송하므로 인자에서 도구를 추론해야 합니다."""
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
    # Direct invocation: {"tool_name": "...", "parameters": {...}}
    elif "tool_name" in event:
        tool_name = event["tool_name"]
        arguments = event.get("parameters", {})
    # Simplified: {"name": "...", "arguments": {...}}
    elif "name" in event and "arguments" in event:
        tool_name = event["name"]
        arguments = event.get("arguments", {})
    # Legacy: {"action": "list_tools"}
    elif event.get("action") == "list_tools":
        return "__list_tools__", {}
    else:
        # MCP Gateway Lambda integration: event IS the arguments directly
        # Infer tool from arguments structure
        # MCP 게이트웨이 Lambda 통합: 이벤트가 직접 인자입니다
        # 인자 구조에서 도구를 추론합니다
        arguments = event

        # Tool inference logic (도구 추론 로직):
        # - If title and body present and no issue_number → github-create-issue
        # - If issue_number and body present and no title → github-add-comment
        # - If state or labels present (without title and issue_number) → github-list-issues
        # - Default (empty args) → github-list-issues

        if "title" in arguments and "body" in arguments and "issue_number" not in arguments:
            tool_name = "github-create-issue"
        elif "issue_number" in arguments and "body" in arguments and "title" not in arguments:
            tool_name = "github-add-comment"
        elif "state" in arguments or "labels" in arguments:
            tool_name = "github-list-issues"
        elif not arguments or len(arguments) == 0:
            tool_name = "github-list-issues"
        else:
            # Cannot infer tool (도구를 추론할 수 없음)
            tool_name = ""

    # Strip MCP Gateway target prefix (TargetName___tool-name → tool-name)
    if "___" in tool_name:
        tool_name = tool_name.split("___", 1)[1]

    return tool_name, arguments


def lambda_handler(event, context):
    """Main Lambda handler. 메인 Lambda 핸들러."""
    print(f"RAW_EVENT: {json.dumps(event, default=str)[:2000]}")
    tool_name, parameters = _extract_tool_info(event)
    print(f"EXTRACTED: tool_name={tool_name}, parameters={json.dumps(parameters, default=str)[:500]}")

    if tool_name == "__list_tools__":
        return {"tools": TOOL_SCHEMAS}

    handlers = {
        "github-create-issue": handle_create_issue,
        "github-add-comment": handle_add_comment,
        "github-list-issues": handle_list_issues,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {
            "error": f"Unknown tool: {tool_name}. Could not infer tool from arguments.",
            "available_tools": list(handlers.keys()),
            "hint": "Use payload format: {\"name\": \"github-create-issue\", \"arguments\": {...}}",
            "received_keys": list(event.keys())
        }

    try:
        return handler(parameters)
    except Exception as e:
        print(f"Tool execution failed: {str(e)}")
        return {"error": f"Tool execution failed: {str(e)}", "tool": tool_name}


# =============================================================================
# Tool Handlers (도구 핸들러)
# =============================================================================
def handle_create_issue(params):
    """Create a new GitHub issue for an incident.
    인시던트를 위한 새 GitHub 이슈를 생성합니다."""
    title = params["title"]
    body = params["body"]
    labels = params.get("labels", ["incident", "auto-analysis"])

    payload = {
        "title": title,
        "body": body,
        "labels": labels
    }

    path = f"/repos/{_github_repo}/issues"
    result = _github_request("POST", path, body=payload)

    return {
        "status": "success",
        "issue_number": result["number"],
        "issue_url": result["html_url"],
        "title": result["title"],
        "state": result["state"],
        "labels": [label["name"] for label in result.get("labels", [])],
        "repo": _github_repo
    }


def handle_add_comment(params):
    """Add a comment to an existing GitHub issue.
    기존 GitHub 이슈에 코멘트를 추가합니다."""
    issue_number = params["issue_number"]
    body = params["body"]

    payload = {"body": body}

    path = f"/repos/{_github_repo}/issues/{issue_number}/comments"
    result = _github_request("POST", path, body=payload)

    return {
        "status": "success",
        "issue_number": issue_number,
        "comment_url": result["html_url"],
        "comment_id": result["id"],
        "repo": _github_repo
    }


def handle_list_issues(params):
    """List recent incident issues.
    최근 인시던트 이슈 목록을 조회합니다."""
    state = params.get("state", "open")
    labels = params.get("labels", "incident")
    limit = params.get("limit", 10)

    query_params = {
        "state": state,
        "labels": labels,
        "per_page": str(min(limit, 100)),
        "sort": "created",
        "direction": "desc"
    }

    path = f"/repos/{_github_repo}/issues"
    issues = _github_request("GET", path, params=query_params)

    # Filter out pull requests (PRs are also returned by /issues endpoint)
    # Pull Request를 필터링 (PR도 /issues 엔드포인트에서 반환됨)
    filtered_issues = [
        {
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "created_at": issue["created_at"],
            "updated_at": issue["updated_at"],
            "url": issue["html_url"],
            "labels": [label["name"] for label in issue.get("labels", [])],
            "comments_count": issue.get("comments", 0)
        }
        for issue in issues
        if "pull_request" not in issue
    ]

    return {
        "status": "success",
        "total": len(filtered_issues),
        "state": state,
        "labels": labels,
        "repo": _github_repo,
        "issues": filtered_issues
    }
