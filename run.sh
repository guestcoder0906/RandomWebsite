#!/bin/bash
set -e

echo "=========================================="
echo "  WebRoulette — Starting services"
echo "=========================================="

# Determine the port (Railway uses PORT env var, HF Spaces uses 7860)
export NGINX_PORT="${PORT:-7860}"
echo "  Listening on port: $NGINX_PORT"

# Substitute the port into nginx config
envsubst '${NGINX_PORT}' < /etc/nginx/nginx.conf > /tmp/nginx-runtime.conf

# Start FastAPI backend in background
echo "[1/2] Starting FastAPI backend on :8000..."
cd /app
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info &

# Wait for backend to be ready
echo "  Waiting for backend..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
        echo "  Backend ready!"
        break
    fi
    sleep 1
done

# Start Nginx in foreground with the runtime config
echo "[2/2] Starting Nginx on :$NGINX_PORT..."
exec nginx -c /tmp/nginx-runtime.conf -g 'daemon off;'
