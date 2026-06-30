#!/usr/bin/env bash
set -Eeuo pipefail

# scripts/start-in-docker.sh
# 一键通过 Docker Compose 启动 Blank Docker 环境。

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="all-in-one"
COMPOSE_FILE="${ROOT_DIR}/compose.all-in-one.yaml"

usage() {
  cat <<'EOF'
Usage: ./scripts/start-in-docker.sh [options]

Options:
  --mode <mode>  启动模式：all-in-one 或 separated，默认 all-in-one
  --all-in-one   使用前后端合并镜像
  --separated    使用前后端分离镜像
  --build        强制重新构建应用镜像
  --down         停止并删除容器与数据卷
  --logs         启动后持续跟踪应用日志
  --env <file>   指定额外的环境变量文件（默认会加载项目根目录 .env）
  -h, --help     显示本帮助

Examples:
  ./scripts/start-in-docker.sh                       # 启动合并镜像环境
  ./scripts/start-in-docker.sh --separated --build   # 启动分离镜像环境并重新构建
  ./scripts/start-in-docker.sh --down                # 清理合并镜像环境
  ./scripts/start-in-docker.sh --mode separated --down
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
    --mode)
      MODE="$2"
      shift 2
      ;;
    --all-in-one)
      MODE="all-in-one"
      shift
      ;;
    --separated)
      MODE="separated"
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

case "${MODE}" in
  all-in-one)
    COMPOSE_FILE="${ROOT_DIR}/compose.all-in-one.yaml"
    HEALTH_URL="http://127.0.0.1:8080/api/health"
    LOG_SERVICES=(app)
    ;;
  separated)
    COMPOSE_FILE="${ROOT_DIR}/compose.separated.yaml"
    HEALTH_URL="http://127.0.0.1:8000/api/health"
    LOG_SERVICES=(backend frontend)
    ;;
  *)
    echo "Unknown mode: ${MODE}" >&2
    usage >&2
    exit 2
    ;;
esac

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
  echo "[start-in-docker] 正在清理 ${MODE} 环境..."
  compose_cmd down -v
  echo "[start-in-docker] 清理完成。"
  exit 0
fi

echo "[start-in-docker] 启动 Blank ${MODE} Docker 环境..."
compose_cmd up ${BUILD_ARG} -d

echo "[start-in-docker] 等待服务就绪..."
READY=0
for i in {1..60}; do
  if curl -sf "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "[start-in-docker] 健康检查通过。"
    READY=1
    break
  fi
  sleep 1
done

if [[ "${READY}" != "1" ]]; then
  echo "[start-in-docker] 服务未在 60 秒内通过健康检查：${HEALTH_URL}" >&2
  compose_cmd logs --tail=120 "${LOG_SERVICES[@]}" >&2 || true
  exit 1
fi

echo "[start-in-docker] 服务访问地址："
if [[ "${MODE}" == "all-in-one" ]]; then
  echo "  应用入口:   http://127.0.0.1:8080"
  echo "  API 文档:   http://127.0.0.1:8080/docs"
else
  echo "  前端入口:   http://127.0.0.1:8080"
  echo "  后端 API:   http://127.0.0.1:8000"
  echo "  API 文档:   http://127.0.0.1:8000/docs"
fi
echo "  Neo4j Web:  http://127.0.0.1:7474"
echo "  PostgreSQL: 127.0.0.1:5432"
echo "  Redis:      127.0.0.1:6379"

if [[ "${SHOW_LOGS}" == "1" ]]; then
  echo "[start-in-docker] 正在跟踪应用日志（按 Ctrl+C 退出）..."
  compose_cmd logs -f "${LOG_SERVICES[@]}"
fi
