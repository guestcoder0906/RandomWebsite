#!/bin/bash
set -e

echo "=========================================="
echo "  WebRoulette — Starting"
echo "=========================================="

# Use Railway's PORT env var, or fall back to 7860 (HF Spaces)
APP_PORT="${PORT:-7860}"
echo "  Starting on port: $APP_PORT"

cd /app
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "$APP_PORT" --log-level info
