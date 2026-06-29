#!/usr/bin/env bash
set -Eeuo pipefail

# scripts/start-in-docker.sh
# 一键通过 Docker Compose 启动 Blank 后端 + PostgreSQL + Redis + Neo4j 完整环境。

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/compose.full.yaml"

usage() {
  cat <<'EOF'
Usage: ./scripts/start-in-docker.sh [options]

Options:
  --build        强制重新构建 backend 镜像
  --down         停止并删除容器与数据卷
  --logs         启动后持续跟踪后端日志
  --env <file>   指定额外的环境变量文件（默认会加载项目根目录 .env）
  -h, --help     显示本帮助

Examples:
  ./scripts/start-in-docker.sh              # 启动完整环境
  ./scripts/start-in-docker.sh --build      # 重新构建镜像后启动
  ./scripts/start-in-docker.sh --down       # 清理环境
  ./scripts/start-in-docker.sh --logs       # 启动并查看后端日志
EOF
}

BUILD_ARG=""
DOWN_AFTER=0
SHOW_LOGS=0
ENV_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)
      BUILD_ARG="--build"
      shift
      ;;
    --down)
      DOWN_AFTER=1
      shift
      ;;
    --logs)
      SHOW_LOGS=1
      shift
      ;;
    --env)
      ENV_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "${ROOT_DIR}"

compose_cmd() {
  local env_args=()
  if [[ -n "${ENV_FILE}" ]]; then
    env_args+=("--env-file" "${ENV_FILE}")
  elif [[ -f "${ROOT_DIR}/.env" ]]; then
    env_args+=("--env-file" "${ROOT_DIR}/.env")
  fi

  if docker compose version >/dev/null 2>&1; then
    docker compose -f "${COMPOSE_FILE}" "${env_args[@]}" "$@"
  elif docker-compose version >/dev/null 2>&1; then
    docker-compose -f "${COMPOSE_FILE}" "${env_args[@]}" "$@"
  else
    echo "需要安装 Docker Compose 插件或 docker-compose。" >&2
    exit 1
  fi
}

if [[ "${DOWN_AFTER}" == "1" ]]; then
  echo "[start-in-docker] 正在清理完整环境..."
  compose_cmd down -v
  echo "[start-in-docker] 清理完成。"
  exit 0
fi

echo "[start-in-docker] 启动 Blank 后端 + PostgreSQL + Redis + Neo4j..."
compose_cmd up ${BUILD_ARG} -d

echo "[start-in-docker] 等待后端服务就绪..."
for i in {1..60}; do
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "[start-in-docker] 后端健康检查通过。"
    break
  fi
  sleep 1
done

echo "[start-in-docker] 服务访问地址："
echo "  后端 API:   http://127.0.0.1:8000"
echo "  API 文档:   http://127.0.0.1:8000/docs"
echo "  Neo4j Web:  http://127.0.0.1:7474"
echo "  PostgreSQL: 127.0.0.1:5432"
echo "  Redis:      127.0.0.1:6379"

if [[ "${SHOW_LOGS}" == "1" ]]; then
  echo "[start-in-docker] 正在跟踪后端日志（按 Ctrl+C 退出）..."
  compose_cmd logs -f backend
fi
