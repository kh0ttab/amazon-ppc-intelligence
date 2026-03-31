# ── Stage 1: Build React frontend ────────────────────────────
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ .
RUN npm run build

# ── Stage 2: Python backend + serve built React ───────────────
FROM python:3.12-slim

# Non-root user (required by HuggingFace Spaces)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir \
    fastapi>=0.110.0 \
    uvicorn[standard]>=0.29.0 \
    sse-starlette>=1.6.0 \
    python-multipart>=0.0.9 \
    anthropic>=0.40.0 \
    apscheduler>=3.10.0 \
    psycopg2-binary>=2.9.0 \
    requests>=2.31.0 \
    beautifulsoup4>=4.12.0 \
    pandas>=2.0.0 \
    -r requirements.txt 2>/dev/null || true

# Copy backend source
COPY backend/ ./backend/

# Copy built React frontend into backend/static
COPY --from=frontend /build/dist ./backend/static/

# Patch main.py to serve static files
RUN python -c "
import re
path = 'backend/main.py'
code = open(path).read()
# Add static file serving if not already present
patch = '''
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os as _os
_static = _os.path.join(_os.path.dirname(__file__), 'static')
if _os.path.isdir(_static):
    app.mount('/assets', StaticFiles(directory=_os.path.join(_static,'assets')), name='assets')
    @app.get('/{full_path:path}', include_in_schema=False)
    async def spa(full_path: str):
        return FileResponse(_os.path.join(_static, 'index.html'))
'''
if 'StaticFiles' not in code:
    open(path, 'a').write(patch)
print('Static serving patched')
"

# Data directory (override with Docker volume or env var)
RUN mkdir -p /app/data && chown appuser /app/data
ENV DB_PATH=/app/data/ppc_intel.db

# HuggingFace Spaces uses port 7860
EXPOSE 7860

USER appuser

WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
