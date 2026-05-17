#!/usr/bin/env bash
# Demo container entrypoint.
#
# - Indexes the baked-in vault on first boot (when /data is empty)
# - Starts the FastAPI backend on 127.0.0.1:8000 (internal only)
# - Starts the Next.js standalone server on 0.0.0.0:7860 (public)

set -euo pipefail

DATA_DIR="${SECONDBRAIN_DATA_PATH:-/data}"
BACKEND_PORT="${SECONDBRAIN_PORT:-8000}"
BACKEND_HOST="${SECONDBRAIN_HOST:-127.0.0.1}"

mkdir -p "$DATA_DIR" "${HF_HOME:-$DATA_DIR/.huggingface}"

# Initial indexing on a fresh/partial volume. Use the .sync_completed marker
# (written only after a successful indexing run) rather than the chroma dir's
# mere existence — we got burned by an OOM mid-index that left a partial
# chroma dir, which caused this guard to skip re-indexing on restart.
if [ ! -f "$DATA_DIR/.sync_completed" ]; then
    echo "[demo] No completed-index marker at $DATA_DIR/.sync_completed — running initial index of /vault..."
    /app/.venv/bin/python -m secondbrain.scripts.daily_sync index \
        || echo "[demo] WARNING: initial index failed; backend will report degraded health"
else
    echo "[demo] Found completed-index marker at $DATA_DIR/.sync_completed — skipping reindex."
fi

# Start backend
echo "[demo] Starting backend on $BACKEND_HOST:$BACKEND_PORT..."
/app/.venv/bin/uvicorn secondbrain.main:app \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" &
BACKEND_PID=$!

trap 'kill -TERM $BACKEND_PID 2>/dev/null || true; exit 0' TERM INT

echo "[demo] Waiting for backend health..."
for _ in $(seq 1 60); do
    if curl -fsS "http://${BACKEND_HOST}:${BACKEND_PORT}/health" >/dev/null 2>&1; then
        echo "[demo] Backend healthy."
        break
    fi
    sleep 1
done

# Start Next.js standalone server. PORT/HOSTNAME are read from env.
echo "[demo] Starting frontend on 0.0.0.0:${PORT:-7860}..."
cd /app/frontend
exec node server.js
