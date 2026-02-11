FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps "awslabs.eks-mcp-server>=0.1.22"

# No hardcoded AWS_REGION - the agent dynamically sets the region
# via the set_aws_region tool based on user intent

# MCP server configuration - matches official AgentCore MCP pattern
ENV EKS_MCP_ALLOW_WRITE=false
ENV EKS_MCP_ALLOW_SENSITIVE=true
ENV MCP_HOST=127.0.0.1
ENV MCP_PORT=8000

# Signal Docker container for host binding logic
ENV DOCKER_CONTAINER=1

# Create non-root user
RUN useradd -m -u 1000 mcp_server
USER mcp_server

COPY main.py main.py

EXPOSE 9000
EXPOSE 8000
EXPOSE 8080

CMD ["python", "main.py"]
