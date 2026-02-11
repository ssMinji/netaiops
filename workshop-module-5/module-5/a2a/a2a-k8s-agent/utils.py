#!/usr/bin/env python3
"""Utility functions for agent configuration and URL generation."""

import logging
import urllib.parse
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional
import boto3
from boto3.session import Session

logger = logging.getLogger(__name__)


def _load_yaml_config(file_path: str) -> Dict[str, Any]:
    """Load YAML configuration from file."""
    logger.debug(f"Loading YAML configuration from: {file_path}")
    config_path = Path(file_path)

    if not config_path.exists():
        logger.error(f"Configuration file not found: {file_path}")
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)

    logger.debug(f"Configuration loaded successfully. Top-level keys: {list(config_data.keys())}")
    return config_data


def _build_agent_url(agent_arn: str) -> str:
    """Build agent invocation URL directly from AgentCore runtime ARN."""
    session = Session()
    region = session.region_name or "us-west-2"
    endpoint = f"https://bedrock-agentcore.{region}.amazonaws.com"
    escaped = urllib.parse.quote(agent_arn, safe="")
    logger.debug(f"Building direct runtime URL for ARN: {agent_arn}")
    return f"{endpoint}/runtimes/{escaped}/invocations?qualifier=DEFAULT"


def _get_client_secret(identity_group: str) -> str:
    """Get OAuth client secret from AWS SSM Parameter Store."""
    try:
        ssm_client = boto3.client('ssm', region_name='us-west-2')
        response = ssm_client.get_parameter(
            Name='/a2a/app/k8s/agentcore/machine_client_secret',
            WithDecryption=True
        )
        client_secret = response['Parameter']['Value']
        logger.debug(f"Retrieved machine_client_secret from SSM for identity group: {identity_group}")
        return client_secret
    except Exception as e:
        logger.error(f"Failed to retrieve machine_client_secret from SSM: {e}")
        raise Exception(f"Unable to retrieve client secret from SSM: {e}")

from urllib.parse import urlparse, urlunparse

def _normalize_cognito_token_endpoint(url: str) -> str:
    """Normalize Cognito user pool token endpoint."""
    try:
        p = urlparse(url)
        if p.netloc.startswith("cognito-idp.") and p.path.endswith("/token") and "/oauth2/" not in p.path:
            fixed_path = p.path.replace("/token", "/oauth2/token")
            return urlunparse((p.scheme, p.netloc, fixed_path, "", "", ""))
    except Exception:
        pass
    return url

import requests

def get_token(
    *,
    user_pool_id: str,
    client_id: str,
    client_secret: str,
    scope_string: str,
    region: Optional[str] = None,
    discovery_url: Optional[str] = None,
    timeout: int = 15,
) -> Dict:
    """
    Retrieve an OAuth2 access token from an Amazon Cognito user pool using the client_credentials grant.
    """
    try:
        # 1) Get token endpoint from SSM Parameter Store first
        token_endpoint: str
        try:
            ssm_client = boto3.client('ssm', region_name='us-west-2')
            response = ssm_client.get_parameter(Name='/a2a/app/k8s/agentcore/cognito_token_url')
            token_endpoint = response['Parameter']['Value']
            logger.debug(f"Retrieved token_endpoint from SSM: {token_endpoint}")
        except Exception as ssm_error:
            logger.warning(f"Failed to get token endpoint from SSM: {ssm_error}")
            if discovery_url:
                disc = requests.get(discovery_url, timeout=timeout)
                disc.raise_for_status()
                discovery_data = disc.json()
                token_endpoint = discovery_data.get("token_endpoint", "")

                if not token_endpoint:
                    return {"error": f"discovery missing token_endpoint at {discovery_url}"}

                token_endpoint = _normalize_cognito_token_endpoint(token_endpoint)
            else:
                if region is None:
                    if "_" not in user_pool_id:
                        return {"error": f"Cannot derive region from user_pool_id '{user_pool_id}'"}
                    region = user_pool_id.split("_", 1)[0]
                token_endpoint = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/oauth2/token"

        form = {
            "grant_type": "client_credentials",
            "scope": scope_string,
        }

        # 2) Try HTTP Basic client authentication (preferred)
        resp = requests.post(
            token_endpoint,
            data=form,
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
            timeout=timeout,
        )

        # 3) If Basic auth fails with invalid_client, retry with form-secret style
        if resp.status_code in (400, 401) and ("invalid_client" in resp.text.lower()):
            form_with_secret = {
                **form,
                "client_id": client_id,
                "client_secret": client_secret,
            }
            resp = requests.post(
                token_endpoint,
                data=form_with_secret,
                headers={"Accept": "application/json",
                         "Content-Type": "application/x-www-form-urlencoded"},
                timeout=timeout,
            )

        if resp.status_code >= 400:
            return {
                "error": f"{resp.status_code} {resp.text[:512]}",
                "token_endpoint": token_endpoint,
            }

        return resp.json()

    except requests.RequestException as e:
        return {"error": f"Request exception during token fetch: {str(e)}"}

def get_agent_config(config_file: str = "config.yaml") -> Dict[str, Any]:
    """Get complete agent configuration including URL and credentials."""
    config = _load_yaml_config(config_file)

    agent_card_info = config.get('agent_card_info', {})

    agent_arn = agent_card_info.get('agent_arn')
    identity_group = agent_card_info.get('identity_group')
    client_id = agent_card_info.get('client_id')
    discovery_url = agent_card_info.get('discovery_url')
    scope = agent_card_info.get('scope')

    # Validate required values
    if not agent_arn:
        raise ValueError("agent_arn not found in configuration")
    if not identity_group:
        raise ValueError("identity_group not found in configuration")
    if not client_id:
        raise ValueError("client_id not found in configuration")
    if not discovery_url:
        raise ValueError("discovery_url not found in configuration")
    if not scope:
        raise ValueError("scope not found in configuration")

    # Build the base URL from the ARN
    base_url = _build_agent_url(agent_arn)

    # Get client secret from SSM
    client_secret = _get_client_secret(identity_group)

    # Extract user pool ID from discovery URL
    import re
    user_pool_match = re.search(r'/([^/]+)/\.well-known/openid_configuration', discovery_url)
    if not user_pool_match:
        user_pool_match = re.search(r'amazonaws\.com/([^/]+)/\.well-known', discovery_url)
    if not user_pool_match:
        raise ValueError(f"Unable to extract user_pool_id from discovery_url: {discovery_url}")
    user_pool_id = user_pool_match.group(1)

    # Generate a session ID that meets the minimum 33 character requirement
    import uuid
    session_uuid = str(uuid.uuid4()).replace('-', '')[:8]
    agent_session_id = f"session-{identity_group}-{session_uuid}"

    return {
        'base_url': base_url,
        'agent_arn': agent_arn,
        'agent_session_id': agent_session_id,
        'user_pool_id': user_pool_id,
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': scope,
        'discovery_url': discovery_url,
        'identity_group': identity_group
    }
