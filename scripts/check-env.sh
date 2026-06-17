#!/usr/bin/env bash
# 检查 Blank 运行环境是否就绪（Bash 版本）
# 数据库连接问题只作为状态项报告，不会导致脚本失败。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
PWA_DIR="${ROOT_DIR}/pwa"

# 退出码：只要核心环境（Python/Node/依赖）就绪就返回 0；数据库类问题不影响
CORE_OK=1

print_row() {
  printf '  %-22s %-10s %s\n' "$1" "$2" "$3"
}

print_header() {
  printf '\n[blank] %s\n' "$1"
  printf '  %-22s %-10s %s\n' "项目" "状态" "说明"
}

check_python() {
  local py=""
  for candidate in python python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      local ver
      ver="$(${candidate} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)"
      if [[ -n "${ver}" ]]; then
        py="${candidate}"
        break
      fi
    fi
  done
  if [[ -z "${py}" ]]; then
    print_row "Python" "缺失" "未找到可用的 python/python3"
    CORE_OK=0
    return
  fi
  local ver
  ver="$(${py} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)"
  local major minor
  major="${ver%%.*}"
  minor="${ver#*.}"
  if (( major > 3 || (major == 3 && minor >= 13) )); then
    print_row "Python" "就绪" "${ver}"
  else
    print_row "Python" "版本过低" "${ver}（需要 ≥3.13）"
    CORE_OK=0
  fi
}

check_node() {
  if ! command -v node >/dev/null 2>&1; then
    print_row "Node.js" "缺失" "未找到 node"
    CORE_OK=0
    return
  fi
  local ver
  ver="$(node --version 2>/dev/null | sed 's/^v//')"
  local major
  major="${ver%%.*}"
  if [[ -n "${major}" && "${major}" -ge 22 ]]; then
    print_row "Node.js" "就绪" "${ver}"
  else
    print_row "Node.js" "版本过低" "${ver}（需要 ≥22）"
    CORE_OK=0
  fi
}

check_conda_env() {
  if ! command -v conda >/dev/null 2>&1; then
    return 1
  fi
  conda env list 2>/dev/null | awk '{print $1}' | grep -qx "blank-learning"
}

check_python_env() {
  if check_conda_env; then
    print_row "Python 环境" "就绪" "blank-learning conda 环境"
    return
  fi
  if [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    print_row "Python 环境" "就绪" "backend/.venv"
    return
  fi
  print_row "Python 环境" "缺失" "无 blank-learning conda 环境或 backend/.venv"
  CORE_OK=0
}

check_backend_imports() {
  local py=""
  for candidate in python python3; do
    if command -v "${candidate}" >/dev/null 2>&1 && "${candidate}" -c 'import sys' 2>/dev/null; then
      py="${candidate}"
      break
    fi
  done
  if [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    py="${BACKEND_DIR}/.venv/bin/python"
  elif command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | awk '{print $1}' | grep -qx "blank-learning"; then
    py=(conda run -n blank-learning python)
  fi
  if [[ -z "${py}" ]]; then
    print_row "Backend 依赖" "缺失" "未找到可用的 Python"
    CORE_OK=0
    return
  fi
  if "${py[@]}" - <<'PY' >/dev/null 2>&1; then
import fastapi, uvicorn, pydantic, multipart, pypdf, cryptography
PY
    print_row "Backend 依赖" "就绪" "关键包可导入"
  else
    print_row "Backend 依赖" "缺失" "请运行 ./start.sh --install-only"
    CORE_OK=0
  fi
}

check_node_modules() {
  if [[ -d "${PWA_DIR}/node_modules" ]]; then
    print_row "Frontend 依赖" "就绪" "node_modules 已存在"
  else
    print_row "Frontend 依赖" "缺失" "请运行 ./start.sh --install-only"
    CORE_OK=0
  fi
}

check_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    print_row "Docker" "就绪" "docker compose 可用"
  elif command -v docker-compose >/dev/null 2>&1; then
    print_row "Docker" "就绪" "docker-compose 可用"
  else
    print_row "Docker" "缺失" "Linux 下可用 --with-infra 自动安装"
  fi
}

tcp_connect_ok() {
  local host="$1"
  local port="$2"
  timeout 1 bash -c ":</dev/tcp/${host}/${port}" >/dev/null 2>&1
}

check_services() {
  local db_url="${BLANK_DATABASE_URL:-postgresql://blank:blank@127.0.0.1:5432/blank}"
  local redis_url="${BLANK_REDIS_URL:-redis://127.0.0.1:6379/0}"
  local neo4j_url="${BLANK_NEO4J_URI:-bolt://127.0.0.1:7687}"

  # 简单解析 host:port
  local db_host db_port redis_host redis_port neo4j_host neo4j_port
  db_host="127.0.0.1"; db_port=5432
  redis_host="127.0.0.1"; redis_port=6379
  neo4j_host="127.0.0.1"; neo4j_port=7687

  if [[ "${db_url}" =~ postgresql://[^@]+@([^:/]+)(:([0-9]+))? ]]; then
    db_host="${BASH_REMATCH[1]}"
    db_port="${BASH_REMATCH[3]:-5432}"
  fi
  if [[ "${redis_url}" =~ redis://([^:/]+)(:([0-9]+))? ]]; then
    redis_host="${BASH_REMATCH[1]}"
    redis_port="${BASH_REMATCH[3]:-6379}"
  fi
  if [[ "${neo4j_url}" =~ bolt://([^:/]+)(:([0-9]+))? ]]; then
    neo4j_host="${BASH_REMATCH[1]}"
    neo4j_port="${BASH_REMATCH[3]:-7687}"
  fi

  if tcp_connect_ok "${db_host}" "${db_port}"; then
    print_row "PostgreSQL" "可达" "${db_host}:${db_port}"
  else
    print_row "PostgreSQL" "不可达" "${db_host}:${db_port}（可 ./start.sh --with-infra 启动）"
  fi

  if tcp_connect_ok "${redis_host}" "${redis_port}"; then
    print_row "Redis" "可达" "${redis_host}:${redis_port}"
  else
    print_row "Redis" "不可达" "${redis_host}:${redis_port}"
  fi

  if [[ "${BLANK_GRAPHRAG_ENABLED:-true}" == "false" || "${BLANK_GRAPHRAG_ENABLED:-true}" == "0" ]]; then
    print_row "Neo4j" "已禁用" "BLANK_GRAPHRAG_ENABLED=false"
  elif tcp_connect_ok "${neo4j_host}" "${neo4j_port}"; then
    print_row "Neo4j" "可达" "${neo4j_host}:${neo4j_port}"
  else
    print_row "Neo4j" "不可达" "${neo4j_host}:${neo4j_port}"
  fi
}

main() {
  cd "${ROOT_DIR}"
  if [[ -f "${ROOT_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT_DIR}/.env"
    set +a
  fi

  print_header "环境检查"
  check_python python3
  check_node
  check_python_env
  check_backend_imports
  check_node_modules
  check_docker
  check_services

  echo
  if [[ "${CORE_OK}" == "1" ]]; then
    echo "[blank] 核心环境已就绪，可直接运行 ./start.sh"
    exit 0
  else
    echo "[blank] 核心环境有缺失，建议运行 ./start.sh --install-only 或 ./start.sh --with-infra"
    exit 1
  fi
}

main "$@"
