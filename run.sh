#!/bin/bash
set -e

echo "=========================================="
echo "  WebRoulette — Starting"
echo "=========================================="

# Set the port to 8000 as per user requirement
APP_PORT="8000"
echo "  Starting on port: $APP_PORT"

cd /app
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "$APP_PORT" --log-level info
