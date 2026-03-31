# ── Stage 1: Build React frontend ────────────────────────────
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ .
RUN npm run build

# ── Stage 2: Python backend ───────────────────────────────────
FROM python:3.12-slim

RUN useradd -m -u 1000 appuser

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi==0.110.0 \
    "uvicorn[standard]==0.29.0" \
    sse-starlette==1.8.2 \
    python-multipart==0.0.9 \
    anthropic==0.40.0 \
    apscheduler==3.10.4 \
    psycopg2-binary==2.9.9 \
    requests==2.31.0 \
    beautifulsoup4==4.12.3 \
    pandas==2.2.1 \
    numpy==1.26.4 \
    python-dotenv==1.0.1 \
    aiofiles==23.2.1

# Copy backend source
COPY backend/ ./backend/

# Copy built React into backend/static
COPY --from=frontend /build/dist ./backend/static/

# Data directory
RUN mkdir -p /app/data && chown appuser:appuser /app/data /app/backend

ENV DB_PATH=/app/data/ppc_intel.db

EXPOSE 7860

USER appuser

WORKDIR /app/backend

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
