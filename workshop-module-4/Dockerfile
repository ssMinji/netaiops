# AgentCore Evaluation Framework - Dockerfile
# Based on Python 3.12 slim image to match module-3 setup

FROM public.ecr.aws/docker/library/python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies required for Python packages
# These are needed for building some Python packages like numpy, pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libssl-dev \
    libffi-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first for better Docker caching
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy the entire module-4 directory
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/reports /app/configs

# Set AWS region environment variables (can be overridden at runtime)
ENV AWS_DEFAULT_REGION=us-east-1 \
    AWS_REGION=us-east-1

# Create non-root user for security
RUN useradd -m -u 1000 evaluation_user && \
    chown -R evaluation_user:evaluation_user /app

# Switch to non-root user
USER evaluation_user

# Expose any ports if needed (optional, adjust as needed)
# EXPOSE 8080

# Default command - can be overridden at runtime
CMD ["python", "-m", "pytest", "tests/", "-v"]
