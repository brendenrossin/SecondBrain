# syntax=docker/dockerfile:1.7
# ============================================================================
# Stage 1 — Frontend build (Next.js standalone output)
# ============================================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

ARG NEXT_PUBLIC_APP_NAME="SecondBrain Demo"
ARG NEXT_PUBLIC_USER_NAME="Brett"
ARG NEXT_PUBLIC_USER_INITIAL="B"
ARG NEXT_PUBLIC_DEMO_MODE="true"
ENV NEXT_PUBLIC_APP_NAME=$NEXT_PUBLIC_APP_NAME \
    NEXT_PUBLIC_USER_NAME=$NEXT_PUBLIC_USER_NAME \
    NEXT_PUBLIC_USER_INITIAL=$NEXT_PUBLIC_USER_INITIAL \
    NEXT_PUBLIC_DEMO_MODE=$NEXT_PUBLIC_DEMO_MODE

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ============================================================================
# Stage 2 — Backend deps (CPU-only torch — saves ~1.5GB over GPU build)
# ============================================================================
FROM python:3.12-slim AS backend-builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

RUN uv sync --frozen --no-dev

# Force CPU-only torch. The default Linux wheel pulls in NVIDIA CUDA libs
# (~1.5GB) we will never use in this CPU-only container.
RUN /app/.venv/bin/pip install --no-cache-dir --upgrade \
        --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision torchaudio \
    && find /app/.venv -name "*.pyc" -delete \
    && find /app/.venv -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# ============================================================================
# Stage 3 — Runtime
# ============================================================================
FROM python:3.12-slim AS runtime
WORKDIR /app

# Minimal Node.js runtime for the standalone server. Use the nodejs apt
# package (smaller than the nodesource installer + headers).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates nodejs \
    && rm -rf /var/lib/apt/lists/*

# Backend artifacts
COPY --from=backend-builder /app/.venv /app/.venv
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Frontend artifacts — standalone bundle is self-contained: a `server.js`
# entrypoint plus a minimal node_modules tree.
COPY --from=frontend-builder /app/frontend/.next/standalone /app/frontend/
COPY --from=frontend-builder /app/frontend/.next/static /app/frontend/.next/static
COPY --from=frontend-builder /app/frontend/public /app/frontend/public

# Demo vault — baked in, read-only at runtime
COPY demo/vault /vault

COPY demo/start.sh /start.sh
RUN chmod +x /start.sh

# HF cache lives on the persistent volume so the embedding model only
# downloads once across deploys.
ENV SECONDBRAIN_VAULT_PATH=/vault \
    SECONDBRAIN_DATA_PATH=/data \
    SECONDBRAIN_DEMO_MODE=true \
    SECONDBRAIN_HOST=127.0.0.1 \
    SECONDBRAIN_PORT=8000 \
    SECONDBRAIN_EMBEDDING_PROVIDER=local \
    SECONDBRAIN_TRACING_ENABLED=false \
    SECONDBRAIN_CONTEXT_GENERATION_ENABLED=false \
    HF_HOME=/data/.huggingface \
    HOSTNAME=0.0.0.0 \
    PORT=7860 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production

EXPOSE 7860

ENTRYPOINT ["/start.sh"]
