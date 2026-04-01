#!/bin/bash
set -e

echo "=========================================="
echo "  WebRoulette — Starting"
echo "=========================================="

# Railway and HF Spaces both respect the EXPOSE 7860 instruction in the Dockerfile
# So we must listen exactly on 7860, otherwise Railway routes to the wrong port.
APP_PORT="7860"
echo "  Starting on port: $APP_PORT"

cd /app
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "$APP_PORT" --log-level info
