#!/bin/bash
# ============================================================
# Start backend on a single HPC GPU node
# Qdrant runs embedded inside Python (no separate server needed)
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Detect host IP ──
NODE_IP="${NODE_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
NODE_IP="${NODE_IP:-$(hostname -i 2>/dev/null | awk '{print $1}')}"
NODE_IP="${NODE_IP:-0.0.0.0}"

# ── Configuration (all overridable via env) ──
export HF_TOKEN="${HF_TOKEN:-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}"
export HUGGINGFACEHUB_API_TOKEN="$HF_TOKEN"

# Local model storage — models downloaded here on first run
export MODELS_DIR="${MODELS_DIR:-$SCRIPT_DIR/models}"
mkdir -p "$MODELS_DIR"

# Qdrant runs embedded — storage path on disk (persistent)
export QDRANT_STORAGE_PATH="${QDRANT_STORAGE_PATH:-$SCRIPT_DIR/qdrant_data}"
export QDRANT_COLLECTION="${QDRANT_COLLECTION:-crm_aggregated}"

# Unset remote Qdrant vars so it uses embedded mode
unset QDRANT_URL QDRANT_HOST

export RAG_WORKERS="${RAG_WORKERS:-4}"
# Single uvicorn process — avoids Qdrant lock conflicts, GPU memory duplication,
# and model import races. Concurrency via async + thread pools (RAG_WORKERS threads).
export UVICORN_WORKERS=1

# Use all available GPUs
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-all}"

# Python path — speech_analysis_qa lives at repo root
export PYTHONPATH="${SCRIPT_DIR}:${SCRIPT_DIR}/noted-backend:${PYTHONPATH:-}"

# Backend config
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./noted.db}"
export DEBUG="${DEBUG:-false}"

BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_LOG="$SCRIPT_DIR/logs/backend.log"

mkdir -p "$SCRIPT_DIR/logs" "$QDRANT_STORAGE_PATH"

# ── Start Backend ──
echo "Starting backend on port $BACKEND_PORT with $UVICORN_WORKERS workers..."
echo "Qdrant: embedded mode (storage: $QDRANT_STORAGE_PATH)"
cd "$SCRIPT_DIR/noted-backend"

python3 -m uvicorn main:app \
    --host 0.0.0.0 \
    --port "$BACKEND_PORT" \
    --workers "$UVICORN_WORKERS" \
    --log-level info \
    2>&1 | tee "$BACKEND_LOG" &
BACKEND_PID=$!

echo ""
echo "═══════════════════════════════════════════════"
echo "  Node IP:      $NODE_IP"
echo "  Backend:      http://${NODE_IP}:${BACKEND_PORT}"
echo "  Qdrant:       embedded (${QDRANT_STORAGE_PATH})"
echo "  GPU:          ${CUDA_VISIBLE_DEVICES}"
echo "  Workers:      ${UVICORN_WORKERS} uvicorn + ${RAG_WORKERS} RAG threads"
echo "  Logs:         $SCRIPT_DIR/logs/"
echo "═══════════════════════════════════════════════"
echo ""

cleanup() {
    echo "Shutting down..."
    kill $BACKEND_PID 2>/dev/null || true
    wait
    echo "Done."
}
trap cleanup EXIT INT TERM

wait $BACKEND_PID
