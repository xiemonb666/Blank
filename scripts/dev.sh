#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PYTHON="${ROOT_DIR}/backend/.venv/bin/python"

if [[ "${CONDA_DEFAULT_ENV:-}" == "blank-learning" && -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
  PYTHON_CMD=("${CONDA_PREFIX}/bin/python")
elif command -v conda >/dev/null 2>&1 && conda env list | awk '{print $1}' | grep -qx "blank-learning"; then
  PYTHON_CMD=(conda run -n blank-learning python)
elif [[ -x "${BACKEND_PYTHON}" ]]; then
  PYTHON_CMD=("${BACKEND_PYTHON}")
else
  PYTHON_CMD=(python3)
fi

cleanup() {
  jobs -p | xargs -r kill
}
trap cleanup EXIT

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
    echo "拒绝启动：${service_name} 正在监听 ${host}，必须先显式设置 BLANK_ALLOWED_HOSTS 和 BLANK_CORS_ORIGINS。" >&2
    return 1
  fi
}

cd "${ROOT_DIR}"
BACKEND_HOST="${BLANK_BACKEND_HOST:-127.0.0.1}"
FRONTEND_HOST="${BLANK_FRONTEND_HOST:-127.0.0.1}"

require_explicit_remote_security "后端" "${BACKEND_HOST}"
require_explicit_remote_security "前端" "${FRONTEND_HOST}"

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
  [[ -n "${host}" && "${port}" != "0" ]] || {
    echo "${name} URL 无效：${url}" >&2
    exit 1
  }
  tcp_connect_ok "${host}" "${port}" || {
    echo "${name} 是默认依赖，但 ${host}:${port} 不可达。请先启动服务或修改环境变量。" >&2
    exit 1
  }
}

if [[ "${1:-}" == "--check-security" ]]; then
  exit 0
fi

require_tcp_service "PostgreSQL" "${BLANK_DATABASE_URL:-postgresql://blank:blank@127.0.0.1:5432/blank}"
require_tcp_service "Redis" "${BLANK_REDIS_URL:-redis://127.0.0.1:6379/0}"
if [[ "${BLANK_GRAPHRAG_ENABLED:-true}" != "false" && "${BLANK_GRAPHRAG_ENABLED:-true}" != "0" && "${BLANK_GRAPHRAG_ENABLED:-true}" != "off" ]]; then
  require_tcp_service "Neo4j" "${BLANK_NEO4J_URI:-bolt://127.0.0.1:7687}"
fi

"${PYTHON_CMD[@]}" -m uvicorn backend.app.main:app --host "${BACKEND_HOST}" --port 8000 --reload --no-server-header &

cd "${ROOT_DIR}/pwa"
npm run dev -- --host "${FRONTEND_HOST}" --port 5173
