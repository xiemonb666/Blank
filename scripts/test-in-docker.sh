#!/usr/bin/env bash
set -Eeuo pipefail

# scripts/test-in-docker.sh
# 在 Docker 中一键启动 PostgreSQL + Redis (+ Neo4j) 并运行 Blank 后端测试。
# 设计用于 WSL2 Ubuntu 26.04 等已安装 Docker 的环境。

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/compose.test.yaml"
COMPOSE_FILE_MINIMAL="${ROOT_DIR}/compose.test.minimal.yaml"

usage() {
  cat <<'EOF'
Usage: ./scripts/test-in-docker.sh [options]

Options:
  --build        强制重新构建 backend-test 镜像（默认仅在 Dockerfile/依赖变化时构建）
  --minimal      使用精简环境（PostgreSQL + Redis，不含 Neo4j），适合网络受限或快速验证
  --down         测试结束后停止并删除容器与卷
  --logs         测试结束后保留容器并输出日志
  -h, --help     显示本帮助

Examples:
  ./scripts/test-in-docker.sh              # 运行全部后端测试（含 Neo4j 完整环境）
  ./scripts/test-in-docker.sh --minimal    # 使用精简环境运行测试
  ./scripts/test-in-docker.sh --build      # 强制重新构建后运行
  ./scripts/test-in-docker.sh --down       # 清理测试环境
EOF
}

BUILD_ARG=""
DOWN_AFTER=0
SHOW_LOGS=0
MINIMAL=0

for arg in "$@"; do
  case "${arg}" in
    --build)
      BUILD_ARG="--build"
      ;;
    --minimal)
      MINIMAL=1
      ;;
    --down)
      DOWN_AFTER=1
      ;;
    --logs)
      SHOW_LOGS=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: ${arg}" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${MINIMAL}" == "1" ]]; then
  COMPOSE_FILE="${COMPOSE_FILE_MINIMAL}"
fi

cd "${ROOT_DIR}"

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -f "${COMPOSE_FILE}" "$@"
  elif docker-compose version >/dev/null 2>&1; then
    docker-compose -f "${COMPOSE_FILE}" "$@"
  else
    echo "需要安装 Docker Compose 插件或 docker-compose。" >&2
    exit 1
  fi
}

if [[ "${DOWN_AFTER}" == "1" ]]; then
  echo "[test-in-docker] 正在清理测试环境..."
  compose_cmd down -v
  exit 0
fi

# 确保测试数据库存在：在 backend-test 启动前由 compose healthcheck 保证 postgres 已就绪，
# 但测试数据库 blank_test 需要额外创建。
echo "[test-in-docker] 启动基础设施并等待就绪..."
if [[ "${MINIMAL}" == "1" ]]; then
  compose_cmd up -d postgres redis
else
  compose_cmd up -d postgres redis neo4j
fi

# 等待 PostgreSQL 可连接并创建测试库
for i in {1..60}; do
  if compose_cmd exec -T postgres pg_isready -U blank -d blank >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

compose_cmd exec -T postgres psql -U blank -d postgres -tc \
  "select 1 from pg_database where datname = 'blank_test'" 2>/dev/null \
  | grep -q 1 \
  || compose_cmd exec -T postgres createdb -U blank blank_test

echo "[test-in-docker] 运行后端测试..."
set +e
compose_cmd up ${BUILD_ARG} --abort-on-container-exit backend-test
TEST_EXIT=$?
set -e

if [[ "${SHOW_LOGS}" == "1" ]]; then
  echo "[test-in-docker] 容器日志："
  compose_cmd logs --tail=200 backend-test || true
fi

if [[ "${DOWN_AFTER}" == "1" ]]; then
  compose_cmd down -v
fi

if [[ ${TEST_EXIT} -eq 0 ]]; then
  echo "[test-in-docker] 全部测试通过。"
else
  echo "[test-in-docker] 测试失败，退出码：${TEST_EXIT}" >&2
fi

exit ${TEST_EXIT}
