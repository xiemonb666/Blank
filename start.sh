#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
PWA_DIR="${ROOT_DIR}/pwa"
VENV_PYTHON="${BACKEND_DIR}/.venv/bin/python"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_HOST="${BLANK_BACKEND_HOST:-127.0.0.1}"
FRONTEND_HOST="${BLANK_FRONTEND_HOST:-127.0.0.1}"
INSTALL_DEPS=1
WITH_INFRA=0

usage() {
  cat <<'EOF'
Usage: ./start.sh [options]

Options:
  --no-install         Skip automatic dependency installation.
  --install-only       Install dependencies and exit.
  --with-infra         Start local PostgreSQL, Redis and Neo4j via scripts/infra.sh before app services.
  --no-install-docker  With --with-infra, skip automatic Docker installation on Linux.
  --check              Check environment readiness and exit.
  --status             Check runtime status and exit.
  --backend-port N     Backend port, default 8000.
  --frontend-port N    Frontend port, default 5173.
  -h, --help           Show this help.

Environment:
  BLANK_BACKEND_HOST   Backend bind host, default 127.0.0.1.
  BLANK_FRONTEND_HOST  Frontend bind host, default 127.0.0.1.
  BACKEND_PORT         Backend port, default 8000.
  FRONTEND_PORT        Frontend port, default 5173.
EOF
}

INSTALL_ONLY=0
CHECK_ENV=0
CHECK_STATUS=0
NO_INSTALL_DOCKER=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-install)
      INSTALL_DEPS=0
      shift
      ;;
    --install-only)
      INSTALL_ONLY=1
      shift
      ;;
    --with-infra)
      WITH_INFRA=1
      shift
      ;;
    --no-install-docker)
      NO_INSTALL_DOCKER=1
      shift
      ;;
    --check)
      CHECK_ENV=1
      shift
      ;;
    --status)
      CHECK_STATUS=1
      shift
      ;;
    --backend-port)
      BACKEND_PORT="${2:?missing backend port}"
      shift 2
      ;;
    --frontend-port)
      FRONTEND_PORT="${2:?missing frontend port}"
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

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
  BACKEND_HOST="${BLANK_BACKEND_HOST:-${BACKEND_HOST}}"
  FRONTEND_HOST="${BLANK_FRONTEND_HOST:-${FRONTEND_HOST}}"
fi

log() {
  printf '[blank] %s\n' "$*"
}

fail() {
  printf '[blank] %s\n' "$*" >&2
  exit 1
}

is_loopback_host() {
  case "$1" in
    127.0.0.1|localhost|::1|\[::1\])
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

require_explicit_remote_security() {
  local service_name="$1"
  local host="$2"
  if is_loopback_host "${host}"; then
    return 0
  fi
  if [[ -z "${BLANK_ALLOWED_HOSTS:-}" || -z "${BLANK_CORS_ORIGINS:-}" ]]; then
    fail "Refusing to start: ${service_name} binds ${host}; set BLANK_ALLOWED_HOSTS and BLANK_CORS_ORIGINS first."
  fi
}

display_host() {
  case "$1" in
    0.0.0.0|::|\[::\])
      printf '127.0.0.1'
      ;;
    *)
      printf '%s' "$1"
      ;;
  esac
}

url_for() {
  local host="$1"
  local port="$2"
  printf 'http://%s:%s' "$(display_host "${host}")" "${port}"
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn | awk '{print $4}' | grep -Eq "[:.]${port}$"
    return $?
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  return 1
}

tcp_connect_ok() {
  local host="$1"
  local port="$2"
  timeout 1 bash -c ":</dev/tcp/${host}/${port}" >/dev/null 2>&1
}

service_endpoint_from_url() {
  local url="$1"
  "${PYTHON_CMD[@]}" - "${url}" <<'PY'
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
host = parsed.hostname or ""
port = parsed.port
if port is None:
    port = {"postgresql": 5432, "postgres": 5432, "redis": 6379, "bolt": 7687}.get(parsed.scheme, 0)
print(f"{host} {port}")
PY
}

require_tcp_service() {
  local name="$1"
  local url="$2"
  local endpoint
  endpoint="$(service_endpoint_from_url "${url}")"
  local host="${endpoint% *}"
  local port="${endpoint##* }"
  [[ -n "${host}" && "${port}" != "0" ]] || fail "${name} URL is invalid: ${url}"
  tcp_connect_ok "${host}" "${port}" || fail "${name} is required but not reachable at ${host}:${port}. Start the service or update its environment URL."
}

check_required_services() {
  require_tcp_service "PostgreSQL" "${BLANK_DATABASE_URL:-postgresql://blank:blank@127.0.0.1:5432/blank}"
  require_tcp_service "Redis" "${BLANK_REDIS_URL:-redis://127.0.0.1:6379/0}"
  if [[ "${BLANK_GRAPHRAG_ENABLED:-true}" != "false" && "${BLANK_GRAPHRAG_ENABLED:-true}" != "0" && "${BLANK_GRAPHRAG_ENABLED:-true}" != "off" ]]; then
    require_tcp_service "Neo4j" "${BLANK_NEO4J_URI:-bolt://127.0.0.1:7687}"
  fi
}

start_local_infra() {
  if [[ "${WITH_INFRA}" != "1" ]]; then
    return
  fi
  log "Starting local PostgreSQL/Redis/Neo4j infrastructure"
  local infra_args=(up)
  if [[ "${NO_INSTALL_DOCKER}" == "1" ]]; then
    infra_args+=(--no-install-docker)
  fi
  "${ROOT_DIR}/scripts/infra.sh" "${infra_args[@]}" || fail "Local infrastructure startup failed. Start PostgreSQL/Redis/Neo4j manually or fix Docker Compose access."
}

http_ok() {
  local url="$1"
  curl -fsS --max-time 2 "${url}" >/dev/null 2>&1
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local attempts="${3:-60}"
  local index=1
  while (( index <= attempts )); do
    if http_ok "${url}"; then
      return 0
    fi
    sleep 0.5
    index=$((index + 1))
  done
  fail "${name} did not become ready: ${url}"
}

resolve_python() {
  if [[ "${CONDA_DEFAULT_ENV:-}" == "blank-learning" && -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
    PYTHON_CMD=("${CONDA_PREFIX}/bin/python")
    return
  fi
  if command -v conda >/dev/null 2>&1 && conda env list | awk '{print $1}' | grep -qx "blank-learning"; then
    PYTHON_CMD=(conda run -n blank-learning python)
    return
  fi
  if [[ -x "${VENV_PYTHON}" ]]; then
    PYTHON_CMD=("${VENV_PYTHON}")
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    log "Creating backend virtual environment at backend/.venv"
    python3 -m venv "${BACKEND_DIR}/.venv" || fail "Could not create backend/.venv. Install python3-venv or use conda env create -f environment.yml."
    PYTHON_CMD=("${VENV_PYTHON}")
    return
  fi
  fail "Python is not available. Install Python 3 or create the conda environment from environment.yml."
}

backend_imports_ok() {
  "${PYTHON_CMD[@]}" - <<'PY' >/dev/null 2>&1
import fastapi
import uvicorn
import pydantic
import multipart
import pypdf
import cryptography
PY
}

install_backend_deps() {
  if backend_imports_ok; then
    return
  fi
  [[ "${INSTALL_DEPS}" == "1" ]] || fail "Backend dependencies are missing. Run without --no-install or install backend/requirements.txt."
  log "Installing backend dependencies"
  "${PYTHON_CMD[@]}" -m pip install -r "${BACKEND_DIR}/requirements.txt"
}

install_frontend_deps() {
  local node_exec npm_exec
  node_exec="${NODE_CMD[0]:-node}"
  npm_exec="${NPM_CMD[0]:-npm}"
  command -v "${node_exec}" >/dev/null 2>&1 || fail "Node.js is not available. Use conda env create -f environment.yml or install Node 22."
  command -v "${npm_exec}" >/dev/null 2>&1 || fail "npm is not available."
  if [[ -d "${PWA_DIR}/node_modules" ]]; then
    return
  fi
  [[ "${INSTALL_DEPS}" == "1" ]] || fail "Frontend dependencies are missing. Run without --no-install or run npm install in pwa/."
  log "Installing frontend dependencies"
  if [[ ${#NPM_CMD[@]} -gt 0 ]]; then
    (cd "${PWA_DIR}" && "${NPM_CMD[@]}" install)
  else
    (cd "${PWA_DIR}" && npm install)
  fi
}

already_running() {
  http_ok "$(url_for "${BACKEND_HOST}" "${BACKEND_PORT}")/api/health" && http_ok "$(url_for "${FRONTEND_HOST}" "${FRONTEND_PORT}")"
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
  fi
  wait >/dev/null 2>&1 || true
  exit "${status}"
}

main() {
  cd "${ROOT_DIR}"

  if [[ "${CHECK_ENV}" == "1" ]]; then
    exec "${ROOT_DIR}/scripts/check-env.sh"
  fi
  if [[ "${CHECK_STATUS}" == "1" ]]; then
    exec "${ROOT_DIR}/scripts/status.sh"
  fi

  require_explicit_remote_security "backend" "${BACKEND_HOST}"
  require_explicit_remote_security "frontend" "${FRONTEND_HOST}"

  # 自动联网补齐环境（会设置 PYTHON_CMD / NODE_CMD / NPM_CMD）
  source "${ROOT_DIR}/scripts/bootstrap-env.sh"
  bootstrap_env

  if [[ ${#PYTHON_CMD[@]} -eq 0 ]]; then
    resolve_python
  fi
  install_backend_deps
  install_frontend_deps

  if [[ "${INSTALL_ONLY}" == "1" ]]; then
    log "Dependencies are ready."
    exit 0
  fi

  start_local_infra
  check_required_services

  local backend_url
  local frontend_url
  backend_url="$(url_for "${BACKEND_HOST}" "${BACKEND_PORT}")"
  frontend_url="$(url_for "${FRONTEND_HOST}" "${FRONTEND_PORT}")"

  if already_running; then
    log "Services are already running."
    log "Frontend: ${frontend_url}/"
    log "Backend:  ${backend_url}/docs"
    exit 0
  fi

  if port_in_use "${BACKEND_PORT}"; then
    fail "Backend port ${BACKEND_PORT} is already in use."
  fi
  if port_in_use "${FRONTEND_PORT}"; then
    fail "Frontend port ${FRONTEND_PORT} is already in use."
  fi

  trap cleanup EXIT INT TERM

  log "Starting backend on ${backend_url}"
  "${PYTHON_CMD[@]}" -m uvicorn backend.app.main:app \
    --host "${BACKEND_HOST}" \
    --port "${BACKEND_PORT}" \
    --reload \
    --no-server-header &
  BACKEND_PID=$!
  wait_for_http "Backend" "${backend_url}/api/health" 80

  log "Starting frontend on ${frontend_url}"
  (
    cd "${PWA_DIR}"
    VITE_API_BASE_URL="${VITE_API_BASE_URL:-${backend_url}}" npm run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}"
  ) &
  FRONTEND_PID=$!
  wait_for_http "Frontend" "${frontend_url}" 80

  log "Ready."
  log "Frontend: ${frontend_url}/"
  log "Backend:  ${backend_url}/docs"
  log "Press Ctrl+C to stop both services."

  wait -n "${BACKEND_PID}" "${FRONTEND_PID}"
}

main "$@"
