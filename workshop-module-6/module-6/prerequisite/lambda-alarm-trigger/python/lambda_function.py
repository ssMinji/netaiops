"""
=============================================================================
Lambda Function - Alarm Trigger for Incident Agent (Module 6)
Lambda 함수 - 인시던트 에이전트 알람 트리거 (모듈 6)
=============================================================================

Description (설명):
    Receives CloudWatch Alarm notifications via SNS and auto-invokes the
    Incident Analysis Agent through AgentCore Runtime API.
    SNS를 통해 CloudWatch 알람 알림을 수신하고 AgentCore Runtime API로
    인시던트 분석 에이전트를 자동 호출합니다.

    This Lambda is NOT an MCP tool - it is an SNS event handler.
    이 Lambda는 MCP 도구가 아닌 SNS 이벤트 핸들러입니다.

Environment Variables (환경변수):
    AGENT_REGION: AgentCore region (default: us-east-1)

Author: NetAIOps Team
Module: workshop-module-6
=============================================================================
"""

import json
import os
import logging
import urllib.parse
import uuid
import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# =============================================================================
# Configuration (설정)
# =============================================================================
AGENT_REGION = os.environ.get("AGENT_REGION", "us-east-1")

ssm_client = boto3.client("ssm", region_name=AGENT_REGION)


# =============================================================================
# Helpers (헬퍼)
# =============================================================================
def _get_ssm_parameter(name):
    """Get SSM parameter value. SSM 파라미터 값을 가져옵니다."""
    try:
        resp = ssm_client.get_parameter(Name=name, WithDecryption=True)
        return resp["Parameter"]["Value"]
    except Exception as e:
        logger.error(f"Failed to get SSM parameter {name}: {e}")
        return None


def _get_m2m_token():
    """Get Cognito M2M access token. Cognito M2M 액세스 토큰을 가져옵니다."""
    prefix = "/app/incident/agentcore"
    client_id = _get_ssm_parameter(f"{prefix}/machine_client_id")
    client_secret = _get_ssm_parameter(f"{prefix}/machine_client_secret")
    token_url = _get_ssm_parameter(f"{prefix}/cognito_token_url")
    scopes = _get_ssm_parameter(f"{prefix}/cognito_auth_scope")

    if not all([client_id, client_secret, token_url]):
        logger.error("Missing Cognito M2M credentials in SSM")
        return None

    try:
        resp = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": scopes or "",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            logger.error(f"Token request failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Token request error: {e}")
    return None


def _parse_alarm_message(sns_message):
    """Parse CloudWatch Alarm SNS message into incident details.
    CloudWatch 알람 SNS 메시지를 인시던트 상세 정보로 파싱합니다."""
    try:
        alarm = json.loads(sns_message)
    except (json.JSONDecodeError, TypeError):
        return {
            "alarm_name": "Unknown",
            "description": sns_message or "No details available",
            "metric": "Unknown",
            "threshold": "Unknown",
            "current_value": "Unknown",
            "timestamp": "Unknown",
        }

    return {
        "alarm_name": alarm.get("AlarmName", "Unknown"),
        "description": alarm.get("AlarmDescription", ""),
        "metric": alarm.get("Trigger", {}).get("MetricName", "Unknown"),
        "namespace": alarm.get("Trigger", {}).get("Namespace", "Unknown"),
        "threshold": alarm.get("Trigger", {}).get("Threshold", "Unknown"),
        "comparison": alarm.get("Trigger", {}).get("ComparisonOperator", ""),
        "current_value": alarm.get("NewStateValue", "Unknown"),
        "reason": alarm.get("NewStateReason", ""),
        "timestamp": alarm.get("StateChangeTime", "Unknown"),
        "region": alarm.get("Region", "Unknown"),
    }


def _build_agent_prompt(alarm_info):
    """Build the incident analysis prompt for the agent.
    에이전트용 인시던트 분석 프롬프트를 생성합니다."""
    prompt = f"""[자동 인시던트 알림]

CloudWatch 알람이 트리거되었습니다. 인시던트 분석 워크플로우에 따라 전체 분석을 수행해주세요.

## 알람 상세 정보
- **알람 이름**: {alarm_info['alarm_name']}
- **메트릭**: {alarm_info['metric']}
- **네임스페이스**: {alarm_info.get('namespace', 'N/A')}
- **임계값**: {alarm_info.get('comparison', '')} {alarm_info['threshold']}
- **현재 상태**: {alarm_info['current_value']}
- **사유**: {alarm_info.get('reason', 'N/A')}
- **발생 시간**: {alarm_info['timestamp']}
- **리전**: {alarm_info.get('region', 'N/A')}

## 분석 지시사항
1. **GitHub Issue 생성** - 제목: "[인시던트] {alarm_info['alarm_name']} 알람 발생", 심각도 라벨 포함. 제목과 본문은 반드시 한글로 작성
2. **지표 수집** - Container Insight와 OpenSearch에서 EKS 클러스터(netaiops-eks-cluster) 관련 메트릭 수집
3. **근본 원인 분석** - 메트릭과 로그를 상관 분석하여 근본 원인 추정
4. **분석 결과 코멘트** - GitHub Issue에 분석 결과, 타임라인, 근본 원인을 한글로 코멘트 작성
5. **자동 복구 시도** - 알려진 Chaos 시나리오 감지 시 (stress-ng 파드, invalid 이미지, 0 레플리카 스케일) chaos-cleanup 도구 호출
6. **복구 결과 코멘트** - GitHub Issue에 복구 결과를 한글로 최종 코멘트 작성 후 이슈 닫기

대상 EKS 클러스터: netaiops-eks-cluster
"""
    return prompt


# =============================================================================
# Main Handler (메인 핸들러)
# =============================================================================
def lambda_handler(event, context):
    """Handle SNS notification from CloudWatch Alarm.
    CloudWatch 알람에서 SNS 알림을 처리합니다."""
    logger.info(f"Received event: {json.dumps(event)}")

    # Parse SNS records
    records = event.get("Records", [])
    if not records:
        logger.warning("No SNS records in event")
        return {"status": "no_records"}

    results = []

    for record in records:
        sns = record.get("Sns", {})
        subject = sns.get("Subject", "CloudWatch Alarm")
        message = sns.get("Message", "")

        logger.info(f"Processing alarm: {subject}")

        # Parse alarm details
        alarm_info = _parse_alarm_message(message)
        logger.info(f"Alarm info: {json.dumps(alarm_info)}")

        # Skip if alarm is returning to OK state
        if alarm_info.get("current_value") == "OK":
            logger.info(f"Alarm '{alarm_info['alarm_name']}' returned to OK, skipping agent invocation")
            results.append({
                "alarm": alarm_info["alarm_name"],
                "status": "skipped",
                "reason": "Alarm returned to OK state",
            })
            continue

        # Get agent runtime ARN
        agent_arn = _get_ssm_parameter("/app/incident/agentcore/agent_runtime_arn")
        if not agent_arn:
            logger.error("Agent runtime ARN not found in SSM")
            results.append({
                "alarm": alarm_info["alarm_name"],
                "status": "error",
                "reason": "Agent runtime ARN not configured",
            })
            continue

        # Get M2M token
        token = _get_m2m_token()
        if not token:
            logger.error("Failed to acquire M2M token")
            results.append({
                "alarm": alarm_info["alarm_name"],
                "status": "error",
                "reason": "Failed to acquire authentication token",
            })
            continue

        # Build prompt
        prompt = _build_agent_prompt(alarm_info)
        logger.info(f"Invoking agent with prompt length: {len(prompt)}")

        # Invoke AgentCore Runtime API
        escaped_arn = urllib.parse.quote(agent_arn, safe="")
        url = (
            f"https://bedrock-agentcore.{AGENT_REGION}.amazonaws.com"
            f"/runtimes/{escaped_arn}/invocations"
        )

        session_id = f"alarm-{alarm_info['alarm_name']}-{uuid.uuid4()}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
        }

        body = {
            "prompt": prompt,
            "actor_id": "alarm-trigger",
        }

        try:
            resp = requests.post(
                url,
                params={"qualifier": "DEFAULT"},
                headers=headers,
                json=body,
                timeout=300,
            )

            if resp.status_code == 200:
                logger.info(f"Agent invoked successfully for alarm: {alarm_info['alarm_name']}")
                results.append({
                    "alarm": alarm_info["alarm_name"],
                    "status": "success",
                    "message": "Agent invoked successfully",
                })
            else:
                logger.error(f"Agent invocation failed: {resp.status_code} {resp.text}")
                results.append({
                    "alarm": alarm_info["alarm_name"],
                    "status": "error",
                    "reason": f"Agent invocation failed: {resp.status_code}",
                    "details": resp.text[:500],
                })

        except requests.exceptions.Timeout:
            logger.error("Agent invocation timed out")
            results.append({
                "alarm": alarm_info["alarm_name"],
                "status": "error",
                "reason": "Agent invocation timed out (5 min)",
            })
        except Exception as e:
            logger.error(f"Agent invocation error: {e}")
            results.append({
                "alarm": alarm_info["alarm_name"],
                "status": "error",
                "reason": str(e),
            })

    return {
        "status": "processed",
        "records_count": len(records),
        "results": results,
    }
