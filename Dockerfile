# ==============================================================================
# OCI Multi-Account Telegram Monitoring Bot - Dockerfile
# Base: Python 3.11 Slim (Hardened, Non-Root Execution)
# ==============================================================================

FROM python:3.11-slim AS runtime

# Set environment optimizations
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=UTC

# Install essential system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 1000 botgroup && \
    useradd -u 1000 -g botgroup -s /bin/bash -m appuser

# Set working directory
WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY config/ ./config/
COPY src/ ./src/
COPY pytest.ini ./

# Prepare data and credentials directories with proper permissions
RUN mkdir -p /app/data /app/credentials/keys /app/config && \
    chown -R appuser:botgroup /app

# Switch to non-root user
USER appuser

# Healthcheck or default command
CMD ["python", "-m", "src.main"]
