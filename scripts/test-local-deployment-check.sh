#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PYTHON="${ROOT_DIR}/backend/.venv/bin/python"

if [[ "${CONDA_DEFAULT_ENV:-}" == "blank-learning" && -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
  PYTHON_CMD=("${CONDA_PREFIX}/bin/python")
elif command -v conda >/dev/null 2>&1 && conda env list | awk '{print $1}' | grep -qx "blank-learning"; then
  PYTHON_CMD=(conda run --no-capture-output -n blank-learning python)
elif [[ -x "${BACKEND_PYTHON}" ]]; then
  PYTHON_CMD=("${BACKEND_PYTHON}")
else
  PYTHON_CMD=(python3)
fi

TMP_DIR="$(mktemp -d)"
SERVER_PID=""
cleanup() {
  if [[ -n "${SERVER_PID}" ]]; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

cd "${ROOT_DIR}"
env \
  BLANK_ENV=production \
  BLANK_SECRET_KEY=prod-secret-0123456789abcdef-0123456789abcdef \
  BLANK_ADMIN_BOOTSTRAP_KEY=bootstrap-0123456789abcdef-0123456789 \
  BLANK_TOKEN_HASH_KEY=token-hash-0123456789abcdef-0123456789 \
  BLANK_ALLOWED_HOSTS=127.0.0.1 \
  BLANK_CORS_ORIGINS=https://blank.example.com \
  BLANK_DATABASE_URL="${BLANK_TEST_DATABASE_URL:-postgresql://blank:blank@127.0.0.1:5432/blank_test}" \
  BLANK_REDIS_URL="${BLANK_TEST_REDIS_URL:-redis://127.0.0.1:6379/15}" \
  BLANK_GRAPHRAG_ENABLED=false \
  "${PYTHON_CMD[@]}" -m uvicorn backend.app.main:app \
    --host 127.0.0.1 \
    --port 18080 \
    --no-server-header \
    --no-date-header \
    >"${TMP_DIR}/server.log" 2>&1 &
SERVER_PID="$!"

for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:18080/api/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -fsS http://127.0.0.1:18080/api/health >/dev/null 2>&1; then
  echo "local production server did not become ready" >&2
  cat "${TMP_DIR}/server.log" >&2
  exit 1
fi

"${ROOT_DIR}/scripts/check-deployment-url.sh" --api-only --allow-local-http http://127.0.0.1:18080
