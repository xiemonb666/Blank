# syntax=docker/dockerfile:1

FROM python:3.13-slim AS python-deps

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r backend/requirements.txt

FROM python:3.13-slim AS runtime

RUN groupadd --system blank && \
    useradd --system --gid blank --home-dir /app --create-home blank && \
    apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 \
      libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=python-deps /install /usr/local
COPY backend/app ./backend/app

RUN mkdir -p /app/backend/data && chown -R blank:blank /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    BLANK_ENV=development \
    BLANK_BACKEND_HOST=0.0.0.0 \
    BLANK_BACKEND_PORT=8000 \
    BLANK_ALLOWED_HOSTS=localhost,127.0.0.1,backend \
    BLANK_CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173 \
    BLANK_DATABASE_URL=postgresql://blank:blank@postgres:5432/blank \
    BLANK_REDIS_URL=redis://redis:6379/0 \
    BLANK_NEO4J_URI=bolt://neo4j:7687 \
    BLANK_NEO4J_USER=neo4j \
    BLANK_NEO4J_PASSWORD=change-this-password \
    BLANK_GRAPHRAG_ENABLED=true \
    BLANK_RAG_BACKEND=sag \
    BLANK_DB_POOL_MIN_CONN=1 \
    BLANK_DB_POOL_MAX_CONN=20 \
    BLANK_OCR_ENABLED=false \
    BLANK_UNLIMITED_OCR_PATH=/ocr \
    BLANK_MAX_REQUEST_BYTES=1048576 \
    BLANK_ALLOW_PRIVATE_MODEL_URLS=false \
    BLANK_ALLOW_PUBLIC_REGISTRATION=false

USER blank
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
