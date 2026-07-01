#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_FILE="$(mktemp "${ROOT_DIR}/tmp-secret-scan.XXXXXX.js")"
OUTPUT_FILE="$(mktemp)"
NODE_BIN="${NODE_BIN:-node}"

if ! command -v "${NODE_BIN}" >/dev/null 2>&1; then
  if [[ -x "/mnt/c/Program Files/nodejs/node.exe" ]]; then
    NODE_BIN="/mnt/c/Program Files/nodejs/node.exe"
  else
    echo "node executable not found; set NODE_BIN to run secret scan" >&2
    exit 1
  fi
fi

cleanup() {
  rm -f "${TMP_FILE}" "${OUTPUT_FILE}"
}
trap cleanup EXIT

printf 'const leaked = "sk-proj-%s";\n' "$(printf 'A%.0s' $(seq 1 40))" >"${TMP_FILE}"

if (cd "${ROOT_DIR}" && "${NODE_BIN}" scripts/secret-scan.mjs) >"${OUTPUT_FILE}" 2>&1; then
  cat "${OUTPUT_FILE}" >&2
  echo "expected secret scan to reject injected OpenAI project key" >&2
  exit 1
fi

if ! grep -q "openai project key" "${OUTPUT_FILE}"; then
  cat "${OUTPUT_FILE}" >&2
  echo "expected secret scan finding to mention openai project key" >&2
  exit 1
fi

rm -f "${TMP_FILE}"
(cd "${ROOT_DIR}" && "${NODE_BIN}" scripts/secret-scan.mjs)
echo "secret scan self-test passed"
