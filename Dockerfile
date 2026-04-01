FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx curl gettext-base && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user (required by HF Spaces)
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Copy Nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy startup script
COPY run.sh ./run.sh
RUN chmod +x ./run.sh

# Create Nginx temp directories writable by appuser
RUN mkdir -p /tmp/nginx-client-body /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi && \
    chown -R appuser:appuser /tmp/nginx-* && \
    chown -R appuser:appuser /var/lib/nginx && \
    chown -R appuser:appuser /var/log/nginx && \
    chown -R appuser:appuser /app && \
    touch /tmp/nginx.pid && \
    chown appuser:appuser /tmp/nginx.pid

# Switch to non-root user
USER appuser

EXPOSE 7860

CMD ["./run.sh"]
