#!/bin/bash
set -e

echo "=========================================="
echo "  RandomWeb — Starting services"
echo "=========================================="

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

# Start Nginx in foreground
echo "[2/2] Starting Nginx on :7860..."
exec nginx -g 'daemon off;'
