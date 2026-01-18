#!/usr/bin/env python3
"""
Debug JWT Token - Decode and inspect the actual token claims
"""

import base64
import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.utils import get_ssm_parameter, get_aws_region
import requests
from urllib.parse import urlencode
import click
import base64
import hashlib

def generate_pkce_pair():
    """Generate PKCE code verifier and challenge for OAuth2"""
    code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode("utf-8").rstrip("=")
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode("utf-8")
        .rstrip("=")
    )
    return code_verifier, code_challenge

def decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without verifying signature"""
    try:
        # Split token into header, payload, signature
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")
        
        # Decode payload (add padding if needed)
        payload = parts[1]
        # Add padding to make length multiple of 4
        payload += '=' * (4 - len(payload) % 4)
        
        decoded_bytes = base64.urlsafe_b64decode(payload)
        payload_dict = json.loads(decoded_bytes)
        
        return payload_dict
    except Exception as e:
        print(f"❌ Error decoding JWT: {e}")
        return {}

def get_access_token_for_debug() -> str:
    """Get access token using OAuth2 flow for debugging"""
    print("🔍 Getting access token for JWT analysis...")
    
    code_verifier, code_challenge = generate_pkce_pair()
    import uuid
    state = str(uuid.uuid4())

    client_id = get_ssm_parameter("/app/netops/agentcore/web_client_id")
    cognito_domain = get_ssm_parameter("/app/netops/agentcore/cognito_domain")
    cognito_auth_scope = get_ssm_parameter("/app/netops/agentcore/cognito_auth_scope")
    redirect_uri = "https://example.com/auth/callback"

    login_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": f"openid email profile {cognito_auth_scope}",
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
        "state": state,
    }

    login_url = f"{cognito_domain}/oauth2/authorize?{urlencode(login_params)}"

    print("🔐 Open the following URL in a browser to authenticate:")
    print(login_url)

    auth_code_input = input("📥 Paste the full redirected URL or just the code: ").strip()
    
    # Parse the code from the input
    if "code=" in auth_code_input:
        from urllib.parse import parse_qs, urlparse
        if auth_code_input.startswith("http"):
            parsed_url = urlparse(auth_code_input)
            params = parse_qs(parsed_url.query)
            auth_code = params.get('code', [None])[0]
        else:
            params = parse_qs(auth_code_input)
            auth_code = params.get('code', [None])[0]
        
        if not auth_code:
            print("❌ Could not extract code from URL")
            sys.exit(1)
    else:
        auth_code = auth_code_input

    token_url = get_ssm_parameter("/app/netops/agentcore/cognito_token_url")
    response = requests.post(
        token_url,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30  # Add timeout to prevent indefinite hanging requests
    )

    if response.status_code != 200:
        print(f"❌ Failed to exchange code: {response.text}")
        sys.exit(1)

    token_response = response.json()
    access_token = token_response["access_token"]
    
    return access_token

@click.command()
def main():
    """Debug JWT token to see actual claims"""
    
    print("🔍 JWT Token Debugger")
    print("=" * 50)
    
    # Get the access token
    access_token = get_access_token_for_debug()
    print("✅ Access token acquired.")
    print()
    
    # Decode the JWT
    print("🔍 Decoding JWT payload...")
    payload = decode_jwt_payload(access_token)
    
    if not payload:
        print("❌ Could not decode JWT payload")
        sys.exit(1)
    
    # Show the full payload
    print("📋 Full JWT Payload:")
    print(json.dumps(payload, indent=2, default=str))
    print()
    
    # Focus on key claims
    print("🎯 Key Claims Analysis:")
    print("-" * 30)
    
    aud_claim = payload.get('aud', 'NOT FOUND')
    client_id_claim = payload.get('client_id', 'NOT FOUND') 
    scope_claim = payload.get('scope', 'NOT FOUND')
    iss_claim = payload.get('iss', 'NOT FOUND')
    
    print(f"📍 aud (audience):  {aud_claim}")
    print(f"📍 client_id:       {client_id_claim}")
    print(f"📍 scope:           {scope_claim}")
    print(f"📍 iss (issuer):    {iss_claim}")
    print()
    
    # Compare with runtime configuration
    print("🔧 Runtime Configuration Comparison:")
    print("-" * 40)
    
    try:
        expected_audience = "netops-resource-server-efb4df20"  # Current setting
        expected_client_id = get_ssm_parameter("/app/netops/agentcore/web_client_id")
        
        print(f"🎯 Runtime expects audience: {expected_audience}")
        print(f"🎯 JWT contains audience:    {aud_claim}")
        print()
        
        if aud_claim == expected_audience:
            print("✅ AUDIENCE MATCH! This should work!")
        else:
            print("❌ AUDIENCE MISMATCH! This is the problem!")
            print()
            print("🔧 Possible Solutions:")
            if isinstance(aud_claim, list):
                for i, aud_val in enumerate(aud_claim):
                    print(f"   Option {i+1}: Use audience '{aud_val}'")
            elif aud_claim and aud_claim != 'NOT FOUND':
                print(f"   Solution: Use audience '{aud_claim}' in runtime config")
            
            if client_id_claim and client_id_claim != 'NOT FOUND':
                print(f"   Alternative: Try client_id '{client_id_claim}' as audience")
    
    except Exception as e:
        print(f"❌ Error comparing with runtime config: {e}")

if __name__ == "__main__":
    main()
