#!/usr/bin/env bash
# 检查 Blank 运行状态（Bash 版本）
# 数据库连接问题只作为状态项报告，不会导致脚本失败。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/compose.yaml"

BACKEND_HOST="${BLANK_BACKEND_HOST:-127.0.0.1}"
FRONTEND_HOST="${BLANK_FRONTEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

print_row() {
  printf '  %-22s %-10s %s\n' "$1" "$2" "$3"
}

print_header() {
  printf '\n[blank] %s\n' "$1"
  printf '  %-22s %-10s %s\n' "项目" "状态" "说明"
}

display_host() {
  case "$1" in
    0.0.0.0|::|\[::\]) printf '127.0.0.1' ;;
    *) printf '%s' "$1" ;;
  esac
}

url_for() {
  printf 'http://%s:%s' "$(display_host "$1")" "$2"
}

http_ok() {
  local url="$1"
  curl -fsS --max-time 2 "${url}" >/dev/null 2>&1
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${port}$"
    return $?
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  timeout 1 bash -c ":</dev/tcp/127.0.0.1/${port}" >/dev/null 2>&1
}

tcp_connect_ok() {
  local host="$1"
  local port="$2"
  timeout 1 bash -c ":</dev/tcp/${host}/${port}" >/dev/null 2>&1
}

check_service_http() {
  local name="$1"
  local url="$2"
  if http_ok "${url}"; then
    print_row "${name} HTTP" "可达" "${url}"
  else
    print_row "${name} HTTP" "不可达" "${url}"
  fi
}

check_service_port() {
  local name="$1"
  local port="$2"
  if port_in_use "${port}"; then
    print_row "${name} 端口" "监听中" "端口 ${port}"
  else
    print_row "${name} 端口" "未监听" "端口 ${port}"
  fi
}

check_docker_containers() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    local output
    output="$(docker compose -f "${COMPOSE_FILE}" ps --format json 2>/dev/null || true)"
    if [[ -n "${output}" && "${output}" != "[]" ]]; then
      print_row "Docker 容器" "运行中" "详见 docker compose -f compose.yaml ps"
    else
      print_row "Docker 容器" "未运行" "可 ./start.sh --with-infra 启动"
    fi
  elif command -v docker-compose >/dev/null 2>&1; then
    local output
    output="$(docker-compose -f "${COMPOSE_FILE}" ps 2>/dev/null || true)"
    if [[ -n "${output}" ]]; then
      print_row "Docker 容器" "运行中" "详见 docker-compose -f compose.yaml ps"
    else
      print_row "Docker 容器" "未运行" "可 ./start.sh --with-infra 启动"
    fi
  else
    print_row "Docker 容器" "未知" "未检测到 docker compose"
  fi
}

check_db_services() {
  local db_url="${BLANK_DATABASE_URL:-postgresql://blank:blank@127.0.0.1:5432/blank}"
  local redis_url="${BLANK_REDIS_URL:-redis://127.0.0.1:6379/0}"
  local neo4j_url="${BLANK_NEO4J_URI:-bolt://127.0.0.1:7687}"

  local db_host=127.0.0.1 db_port=5432
  local redis_host=127.0.0.1 redis_port=6379
  local neo4j_host=127.0.0.1 neo4j_port=7687

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
    print_row "PostgreSQL" "不可达" "${db_host}:${db_port}"
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
    BACKEND_HOST="${BLANK_BACKEND_HOST:-${BACKEND_HOST}}"
    FRONTEND_HOST="${BLANK_FRONTEND_HOST:-${FRONTEND_HOST}}"
  fi

  print_header "运行状态检查"
  check_service_http "后端" "$(url_for "${BACKEND_HOST}" "${BACKEND_PORT}")/api/health"
  check_service_port "后端" "${BACKEND_PORT}"
  check_service_http "前端" "$(url_for "${FRONTEND_HOST}" "${FRONTEND_PORT}")"
  check_service_port "前端" "${FRONTEND_PORT}"
  check_docker_containers
  check_db_services

  echo
  echo "[blank] 状态检查完成（数据库不可达不会阻止其他服务判定）"
  exit 0
}

main "$@"
