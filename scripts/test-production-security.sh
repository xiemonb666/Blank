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

run_import_check() {
  local output_file="$1"
  shift
  set +e
  env \
    PYTHONPATH="${ROOT_DIR}" \
    BLANK_DATABASE_URL="${BLANK_TEST_DATABASE_URL:-postgresql://blank:blank@127.0.0.1:5432/blank_test}" \
    BLANK_REDIS_URL="${BLANK_TEST_REDIS_URL:-redis://127.0.0.1:6379/15}" \
    BLANK_GRAPHRAG_ENABLED=false \
    "$@" \
    "${PYTHON_CMD[@]}" -c "import backend.app.main" >"${output_file}" 2>&1
  local status=$?
  set -e
  return "${status}"
}

expect_failure() {
  local name="$1"
  local expected="$2"
  shift 2
  local output_file
  output_file="$(mktemp)"
  if run_import_check "${output_file}" "$@"; then
    echo "expected production startup check to fail: ${name}" >&2
    rm -f "${output_file}"
    exit 1
  fi
  if ! grep -q "${expected}" "${output_file}"; then
    echo "expected failure for ${name} to mention: ${expected}" >&2
    cat "${output_file}" >&2
    rm -f "${output_file}"
    exit 1
  fi
  rm -f "${output_file}"
}

expect_success() {
  local name="$1"
  shift
  local output_file
  output_file="$(mktemp)"
  if ! run_import_check "${output_file}" "$@"; then
    echo "expected production startup check to pass: ${name}" >&2
    cat "${output_file}" >&2
    rm -f "${output_file}"
    exit 1
  fi
  rm -f "${output_file}"
}

STRONG_SECRET="prod-secret-0123456789abcdef-0123456789abcdef"
STRONG_BOOTSTRAP="bootstrap-0123456789abcdef-0123456789"

expect_failure "missing production secrets" "BLANK_SECRET_KEY" \
  BLANK_ENV=production

expect_failure "weak production secret" "弱口令" \
  BLANK_ENV=production \
  BLANK_SECRET_KEY=change-this-secret-change-this-secret \
  BLANK_ADMIN_BOOTSTRAP_KEY="${STRONG_BOOTSTRAP}" \
  BLANK_ALLOWED_HOSTS=blank.example.com \
  BLANK_CORS_ORIGINS=https://blank.example.com

expect_failure "wildcard host" "通配 Host" \
  BLANK_ENV=production \
  BLANK_SECRET_KEY="${STRONG_SECRET}" \
  BLANK_ADMIN_BOOTSTRAP_KEY="${STRONG_BOOTSTRAP}" \
  BLANK_ALLOWED_HOSTS="*" \
  BLANK_CORS_ORIGINS=https://blank.example.com

expect_failure "insecure cors" "必须使用 https" \
  BLANK_ENV=production \
  BLANK_SECRET_KEY="${STRONG_SECRET}" \
  BLANK_ADMIN_BOOTSTRAP_KEY="${STRONG_BOOTSTRAP}" \
  BLANK_ALLOWED_HOSTS=blank.example.com \
  BLANK_CORS_ORIGINS=http://blank.example.com

expect_failure "private model urls" "不能开启 BLANK_ALLOW_PRIVATE_MODEL_URLS" \
  BLANK_ENV=production \
  BLANK_SECRET_KEY="${STRONG_SECRET}" \
  BLANK_ADMIN_BOOTSTRAP_KEY="${STRONG_BOOTSTRAP}" \
  BLANK_ALLOWED_HOSTS=blank.example.com \
  BLANK_CORS_ORIGINS=https://blank.example.com \
  BLANK_ALLOW_PRIVATE_MODEL_URLS=true

expect_failure "trusted proxy without trusted list" "BLANK_TRUSTED_PROXIES" \
  BLANK_ENV=production \
  BLANK_SECRET_KEY="${STRONG_SECRET}" \
  BLANK_ADMIN_BOOTSTRAP_KEY="${STRONG_BOOTSTRAP}" \
  BLANK_ALLOWED_HOSTS=blank.example.com \
  BLANK_CORS_ORIGINS=https://blank.example.com \
  BLANK_TRUST_PROXY_HEADERS=true

expect_success "hardened production startup" \
  BLANK_ENV=production \
  BLANK_SECRET_KEY="${STRONG_SECRET}" \
  BLANK_ADMIN_BOOTSTRAP_KEY="${STRONG_BOOTSTRAP}" \
  BLANK_TOKEN_HASH_KEY="token-hash-0123456789abcdef-0123456789" \
  BLANK_ALLOWED_HOSTS=blank.example.com \
  BLANK_CORS_ORIGINS=https://blank.example.com \
  BLANK_TRUST_PROXY_HEADERS=true \
  BLANK_TRUSTED_PROXIES=127.0.0.1/32

echo "production startup security checks passed"
