# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-build

WORKDIR /app/pwa

COPY pwa/package.json pwa/package-lock.json ./
RUN npm ci

COPY pwa/index.html pwa/tsconfig.json pwa/vite.config.ts ./
COPY pwa/src ./src

ENV VITE_API_BASE_URL=/
RUN npm run build

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
      nginx \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

WORKDIR /app

COPY --from=python-deps /install /usr/local
COPY backend/app ./backend/app
COPY --from=frontend-build /app/pwa/dist ./pwa/dist
COPY docker/nginx/all-in-one.conf /etc/nginx/nginx.conf
COPY docker/all-in-one-entrypoint.sh /app/docker/all-in-one-entrypoint.sh

RUN mkdir -p /app/backend/data /tmp/nginx/client_body /tmp/nginx/proxy /tmp/nginx/fastcgi /tmp/nginx/uwsgi /tmp/nginx/scgi && \
    chown -R blank:blank /app /tmp/nginx

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    BLANK_ENV=development \
    BLANK_ALLOWED_HOSTS=localhost,127.0.0.1 \
    BLANK_CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080 \
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

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3).read()" || exit 1

CMD ["/app/docker/all-in-one-entrypoint.sh"]
