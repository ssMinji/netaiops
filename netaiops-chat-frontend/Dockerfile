# =============================================================================
# NetAIOps Chat Frontend - Dockerfile
# NetAIOps 채팅 프론트엔드 - 도커파일
# =============================================================================
# Multi-stage build for optimized image size
# 최적화된 이미지 크기를 위한 멀티 스테이지 빌드
# =============================================================================

# Stage 1: Build stage (빌드 스테이지)
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies (빌드 의존성 설치)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
# 요구사항 복사 및 Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime stage (런타임 스테이지)
FROM python:3.11-slim

WORKDIR /app

# Create non-root user for security (보안을 위한 비root 사용자 생성)
RUN useradd --create-home --shell /bin/bash appuser

# Copy installed packages from builder (빌더에서 설치된 패키지 복사)
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code (애플리케이션 코드 복사)
COPY src/ ./

# Set environment variables (환경 변수 설정)
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Switch to non-root user (비root 사용자로 전환)
USER appuser

# Expose port (포트 노출)
EXPOSE 8501

# Health check (헬스체크)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run Streamlit app (Streamlit 앱 실행)
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
