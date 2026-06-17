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

check_requirements_file() {
  local file="$1"
  local rel="${file#${ROOT_DIR}/}"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    local trimmed
    trimmed="$(printf '%s' "${line}" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
    [[ -z "${trimmed}" || "${trimmed}" == \#* ]] && continue
    if [[ "${trimmed}" == -r\ * ]]; then
      local include="${trimmed#-r }"
      [[ -f "${ROOT_DIR}/backend/${include}" || -f "$(dirname "${file}")/${include}" ]] || {
        echo "requirements include target missing in ${rel}: ${trimmed}" >&2
        exit 1
      }
      continue
    fi
    if [[ "${trimmed}" =~ (git\+|https?://|ssh://|file://|@) ]]; then
      echo "remote or direct URL dependency is not allowed in ${rel}: ${trimmed}" >&2
      exit 1
    fi
    if [[ ! "${trimmed}" =~ ^[A-Za-z0-9_.-]+(\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.!+~-]+$ ]]; then
      echo "python dependency must be exactly pinned with == in ${rel}: ${trimmed}" >&2
      exit 1
    fi
  done <"${file}"
}

check_requirements_file "${ROOT_DIR}/backend/requirements.txt"
check_requirements_file "${ROOT_DIR}/backend/requirements-dev.txt"

node --input-type=module <<'NODE'
import { readFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync("pwa/package.json", "utf8"));
const lock = JSON.parse(readFileSync("pwa/package-lock.json", "utf8"));

if (lock.lockfileVersion < 3) {
  throw new Error("package-lock.json must use npm lockfileVersion >= 3");
}

const allDeps = { ...(pkg.dependencies ?? {}), ...(pkg.devDependencies ?? {}) };
for (const name of Object.keys(allDeps)) {
  const lockEntry = lock.packages?.[`node_modules/${name}`];
  if (!lockEntry?.version || !lockEntry?.resolved || !lockEntry?.integrity) {
    throw new Error(`dependency is missing locked version/resolved/integrity: ${name}`);
  }
  if (!String(lockEntry.resolved).startsWith("https://registry.npmjs.org/")) {
    throw new Error(`dependency must resolve from npmjs registry: ${name}`);
  }
}

const scripts = pkg.scripts ?? {};
for (const [name, command] of Object.entries(scripts)) {
  if (/curl|wget|bash\s+-c|sh\s+-c|powershell|Invoke-WebRequest|eval|npx\s+[^&|;]+https?:/i.test(String(command))) {
    throw new Error(`package script contains unsafe network/shell pattern: ${name}`);
  }
}

for (const [path, entry] of Object.entries(lock.packages ?? {})) {
  if (!path) continue;
  if (entry.resolved && !String(entry.resolved).startsWith("https://registry.npmjs.org/")) {
    throw new Error(`lockfile package must resolve from npmjs registry: ${path}`);
  }
  if (entry.resolved && !entry.integrity) {
    throw new Error(`lockfile package is missing integrity: ${path}`);
  }
}
NODE

"${PYTHON_CMD[@]}" -m pip show pip-audit >/dev/null 2>&1 || {
  echo "pip-audit is required for supply chain checks; install backend/requirements-dev.txt" >&2
  exit 1
}
"${PYTHON_CMD[@]}" -m pip_audit -r "${ROOT_DIR}/backend/requirements-dev.txt"

echo "supply chain checks passed"
