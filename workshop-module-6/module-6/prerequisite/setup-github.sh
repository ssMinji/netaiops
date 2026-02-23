#!/bin/bash

# =============================================================================
# GitHub Integration Setup for Incident Automation Pipeline
# 인시던트 자동화 파이프라인용 GitHub 통합 설정
# =============================================================================
# Stores GitHub PAT and repo name in SSM Parameter Store.
#
# Prerequisites:
#   - GitHub Personal Access Token with 'repo' scope
#   - GitHub repository for incident tracking (e.g., netaiops-incidents)
#
# Usage: ./setup-github.sh
# =============================================================================

set -e

PROFILE="netaiops-deploy"
REGION="us-east-1"

echo "==========================================="
echo " GitHub Integration Setup"
echo "==========================================="
echo ""
echo "This script stores GitHub credentials in SSM Parameter Store"
echo "for the Incident Analysis Agent's GitHub Issues integration."
echo ""

# -----------------------------------------------
# 1. Collect GitHub PAT
# -----------------------------------------------
echo "A GitHub Personal Access Token (PAT) with 'repo' scope is required."
echo "Create one at: https://github.com/settings/tokens/new"
echo ""
read -sp "Enter GitHub PAT: " GITHUB_PAT
echo ""

if [ -z "$GITHUB_PAT" ]; then
    echo "ERROR: GitHub PAT cannot be empty"
    exit 1
fi

# -----------------------------------------------
# 2. Collect GitHub Repo
# -----------------------------------------------
echo ""
echo "Enter the GitHub repository for incident tracking (format: owner/repo-name)"
echo "Example: myuser/netaiops-incidents"
echo ""
read -p "Enter GitHub repo: " GITHUB_REPO

if [ -z "$GITHUB_REPO" ]; then
    echo "ERROR: GitHub repo cannot be empty"
    exit 1
fi

# Validate format
if [[ ! "$GITHUB_REPO" =~ ^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$ ]]; then
    echo "ERROR: Invalid repo format. Expected: owner/repo-name"
    exit 1
fi

# -----------------------------------------------
# 3. Validate GitHub API Access
# -----------------------------------------------
echo ""
echo "Validating GitHub API access..."

HTTP_STATUS=$(curl -s -o /tmp/github_validate.json -w "%{http_code}" \
    -H "Authorization: Bearer ${GITHUB_PAT}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${GITHUB_REPO}")

if [ "$HTTP_STATUS" = "200" ]; then
    REPO_FULL_NAME=$(cat /tmp/github_validate.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('full_name',''))" 2>/dev/null || echo "")
    echo "Validated: Repository '${REPO_FULL_NAME}' is accessible"
elif [ "$HTTP_STATUS" = "404" ]; then
    echo "WARNING: Repository '${GITHUB_REPO}' not found."
    echo "  The repository may be private or may not exist yet."
    read -p "  Continue anyway? (y/N): " CONTINUE
    if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
        echo "Aborted."
        exit 1
    fi
elif [ "$HTTP_STATUS" = "401" ]; then
    echo "ERROR: GitHub PAT is invalid or expired"
    exit 1
else
    echo "WARNING: Unexpected HTTP status ${HTTP_STATUS}. Continuing..."
fi

rm -f /tmp/github_validate.json

# -----------------------------------------------
# 4. Store in SSM Parameter Store
# -----------------------------------------------
echo ""
echo "Storing credentials in SSM Parameter Store..."

# Store PAT (SecureString)
aws ssm put-parameter \
    --name "/app/incident/github/pat" \
    --value "$GITHUB_PAT" \
    --type "SecureString" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}
echo "Stored: /app/incident/github/pat (SecureString)"

# Store repo name (String)
aws ssm put-parameter \
    --name "/app/incident/github/repo" \
    --value "$GITHUB_REPO" \
    --type "String" \
    --overwrite \
    --region ${REGION} \
    --profile ${PROFILE}
echo "Stored: /app/incident/github/repo"

# -----------------------------------------------
# 5. Summary
# -----------------------------------------------
echo ""
echo "==========================================="
echo " GitHub Integration Setup Complete!"
echo "==========================================="
echo ""
echo "SSM Parameters:"
echo "  /app/incident/github/pat   → (SecureString) GitHub PAT"
echo "  /app/incident/github/repo  → ${GITHUB_REPO}"
echo ""
echo "The Incident Analysis Agent will use these to create"
echo "GitHub Issues for automated incident tracking."
echo ""
echo "To test manually:"
echo "  aws lambda invoke --function-name incident-github-tools \\"
echo "    --payload '{\"name\":\"github-create-issue\",\"arguments\":{\"title\":\"Test Issue\",\"body\":\"Testing GitHub integration\"}}' \\"
echo "    --region ${REGION} --profile ${PROFILE} /dev/stdout"
echo ""
