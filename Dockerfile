FROM python:3.12-slim

# Install minimal system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install Python dependencies (cached layer)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY . .
RUN chmod +x /app/run.sh && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["/app/run.sh"]
