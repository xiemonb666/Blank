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

run_step() {
  local label="$1"
  shift
  echo "==> ${label}"
  "$@"
}

run_step "backend tests" "${PYTHON_CMD[@]}" -m pytest backend/test_api.py backend/test_v2_api.py
run_step "production startup security" "${ROOT_DIR}/scripts/test-production-security.sh"
run_step "development bind security" "${ROOT_DIR}/scripts/test-dev-security.sh"
run_step "deploy template security" "${ROOT_DIR}/scripts/check-deploy-templates.sh"
run_step "supply chain checks" "${ROOT_DIR}/scripts/check-supply-chain.sh"
run_step "secret leakage scan" "${ROOT_DIR}/scripts/test-secret-scan.sh"
run_step "local deployment URL security" "${ROOT_DIR}/scripts/test-local-deployment-check.sh"
run_step "frontend deployment URL security" "${ROOT_DIR}/scripts/test-frontend-deployment-check.sh"

pushd "${ROOT_DIR}/pwa" >/dev/null
run_step "frontend security checks" npm run security:check
run_step "frontend production build" npm run build
run_step "npm dependency audit" npm audit --audit-level=moderate --registry=https://registry.npmjs.org
popd >/dev/null

echo "security audit passed"
