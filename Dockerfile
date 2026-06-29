# syntax=docker/dockerfile:1
# Blank 后端生产/开发一体化镜像
# 包含 Python 3.13、FastAPI、PostgreSQL/Redis/Neo4j 驱动
# 用法见 compose.full.yaml 或 scripts/start-in-docker.sh

FROM python:3.13-slim

# 创建非 root 运行用户，符合生产安全最佳实践
RUN groupadd --system blank && useradd --system --gid blank --home-dir /app blank

WORKDIR /app

# 安装系统级依赖：PostgreSQL 客户端库、编译工具（部分 Python 包需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 缓存层
COPY backend/requirements.txt backend/requirements-dev.txt ./backend/

# 安装 Python 依赖（生产依赖即可；如需在容器内运行测试，可改 requirements-dev.txt）
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r backend/requirements.txt

# 复制后端源码
COPY backend/ ./backend/

# 创建数据目录并调整权限
RUN mkdir -p /app/backend/data && chown -R blank:blank /app

# 运行时环境变量默认值
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    BLANK_ENV=development \
    BLANK_BACKEND_HOST=0.0.0.0 \
    BLANK_BACKEND_PORT=8000 \
    BLANK_ALLOWED_HOSTS=localhost,127.0.0.1,backend \
    BLANK_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173 \
    BLANK_DATABASE_URL=postgresql://blank:blank@postgres:5432/blank \
    BLANK_REDIS_URL=redis://redis:6379/0 \
    BLANK_NEO4J_URI=bolt://neo4j:7687 \
    BLANK_NEO4J_USER=neo4j \
    BLANK_NEO4J_PASSWORD=change-this-password \
    BLANK_GRAPHRAG_ENABLED=true \
    BLANK_MAX_REQUEST_BYTES=1048576 \
    BLANK_ALLOW_PRIVATE_MODEL_URLS=false \
    BLANK_ALLOW_PUBLIC_REGISTRATION=false

USER blank

EXPOSE 8000

WORKDIR /app/backend

# 默认启动命令；生产环境建议通过 compose 或编排工具覆盖为更严格的参数
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
