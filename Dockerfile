FROM python:3.12-slim

# Install system dependencies & Clear cache in one layer to save space
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx curl gettext-base && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Install Python dependencies separately for better caching
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY . .

# Copy Nginx config to the expected location
COPY nginx.conf /etc/nginx/nginx.conf

# Setup Nginx temp directories & permissions (Single Layer)
RUN mkdir -p /tmp/nginx-client-body /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi /var/log/nginx /var/lib/nginx && \
    chown -R appuser:appuser /tmp/nginx-* /var/lib/nginx /var/log/nginx /app && \
    chmod +x /app/run.sh && \
    touch /tmp/nginx.pid && \
    chown appuser:appuser /tmp/nginx.pid

# Switch to non-root user
USER appuser

EXPOSE 7860

CMD ["/app/run.sh"]
