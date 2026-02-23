# ===========================================================================
# NetAIOps Agent Hub – Multi-stage build
# Stage 1: Build React frontend
# Stage 2: Serve with FastAPI (uvicorn)
# ===========================================================================

# --- Stage 1: Frontend build ---
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

# --- Stage 2: Backend + static files ---
FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ .

# Copy built frontend into static/
COPY --from=frontend-build /build/dist ./static

# Runtime config
ENV AGENT_REGION=us-east-1

# Non-root user
RUN useradd -m -u 1000 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/config')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
