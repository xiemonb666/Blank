#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: scripts/check-deployment-url.sh [--allow-local-http] https://blank.example.com
       scripts/check-deployment-url.sh --api-only --allow-local-http http://127.0.0.1:8000

Checks a deployed Blank backend URL for production-facing security basics:
HTTPS, security headers, disabled API docs, health endpoint behavior, and basic
Host header rejection. Full deployment checks also verify the frontend root page
HTTP security headers.
EOF
}

ALLOW_LOCAL_HTTP=0
API_ONLY=0
while [[ "${1:-}" == "--allow-local-http" || "${1:-}" == "--api-only" ]]; do
  case "${1:-}" in
    --allow-local-http)
      ALLOW_LOCAL_HTTP=1
      ;;
    --api-only)
      API_ONLY=1
      ;;
  esac
  shift
done

BASE_URL="${1:-}"
if [[ "${BASE_URL}" == "-h" || "${BASE_URL}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -z "${BASE_URL}" ]]; then
  usage
  exit 2
fi

case "${BASE_URL}" in
  https://*)
    ;;
  http://localhost:*|http://127.0.0.1:*|http://[::1]:*)
    if [[ "${ALLOW_LOCAL_HTTP}" != "1" ]]; then
      echo "refusing HTTP URL unless --allow-local-http is set for local checks" >&2
      exit 1
    fi
    ;;
  *)
    echo "production deployment must use HTTPS; local HTTP requires --allow-local-http" >&2
    exit 1
    ;;
esac

command -v curl >/dev/null 2>&1 || {
  echo "curl is required" >&2
  exit 1
}

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

BASE_URL="${BASE_URL%/}"
HEALTH_HEADERS="${TMP_DIR}/health.headers"
HEALTH_BODY="${TMP_DIR}/health.body"
FRONTEND_HEADERS="${TMP_DIR}/frontend.headers"
FRONTEND_BODY="${TMP_DIR}/frontend.body"
DOC_HEADERS="${TMP_DIR}/docs.headers"
HOST_HEADERS="${TMP_DIR}/host.headers"
CORS_HEADERS="${TMP_DIR}/cors.headers"

curl -fsS --max-time 10 --dump-header "${HEALTH_HEADERS}" --output "${HEALTH_BODY}" "${BASE_URL}/api/health" >/dev/null
if [[ "${API_ONLY}" != "1" ]]; then
  curl -fsS --max-time 10 --dump-header "${FRONTEND_HEADERS}" --output "${FRONTEND_BODY}" "${BASE_URL}/" >/dev/null
fi

require_header() {
  local header_file="$1"
  local name="$2"
  local pattern="$3"
  local target="$4"
  if ! grep -Eiq "^${name}:[[:space:]]*${pattern}" "${header_file}"; then
    echo "missing or weak header on ${target}: ${name}: ${pattern}" >&2
    cat "${header_file}" >&2
    exit 1
  fi
}

require_header "${HEALTH_HEADERS}" "cache-control" ".*no-store" "/api/health"
require_header "${HEALTH_HEADERS}" "x-content-type-options" "nosniff" "/api/health"
require_header "${HEALTH_HEADERS}" "x-frame-options" "DENY" "/api/health"
require_header "${HEALTH_HEADERS}" "referrer-policy" "no-referrer" "/api/health"
require_header "${HEALTH_HEADERS}" "permissions-policy" ".+" "/api/health"
require_header "${HEALTH_HEADERS}" "content-security-policy" ".*default-src 'none'.*frame-ancestors 'none'" "/api/health"
require_header "${HEALTH_HEADERS}" "cross-origin-opener-policy" "same-origin" "/api/health"
require_header "${HEALTH_HEADERS}" "cross-origin-resource-policy" "same-site" "/api/health"

if [[ "${API_ONLY}" != "1" ]]; then
  require_header "${FRONTEND_HEADERS}" "cache-control" ".*no-store" "/"
  require_header "${FRONTEND_HEADERS}" "x-content-type-options" "nosniff" "/"
  require_header "${FRONTEND_HEADERS}" "x-frame-options" "DENY" "/"
  require_header "${FRONTEND_HEADERS}" "referrer-policy" "no-referrer" "/"
  require_header "${FRONTEND_HEADERS}" "permissions-policy" ".+" "/"
  require_header "${FRONTEND_HEADERS}" "content-security-policy" ".*default-src 'self'.*frame-ancestors 'none'.*connect-src 'self'.*script-src 'self'" "/"
  require_header "${FRONTEND_HEADERS}" "cross-origin-opener-policy" "same-origin" "/"
  require_header "${FRONTEND_HEADERS}" "cross-origin-resource-policy" "same-site" "/"
fi

if [[ "${BASE_URL}" == https://* ]]; then
  require_header "${HEALTH_HEADERS}" "strict-transport-security" ".*max-age=" "/api/health"
  if [[ "${API_ONLY}" != "1" ]]; then
    require_header "${FRONTEND_HEADERS}" "strict-transport-security" ".*max-age=" "/"
  fi
fi

SERVER_HEADER_FILES=("${HEALTH_HEADERS}")
if [[ "${API_ONLY}" != "1" ]]; then
  SERVER_HEADER_FILES+=("${FRONTEND_HEADERS}")
fi

if grep -Eiq "^server:" "${SERVER_HEADER_FILES[@]}"; then
  echo "Server header is exposed; hide backend and proxy implementation details" >&2
  cat "${HEALTH_HEADERS}" >&2
  cat "${FRONTEND_HEADERS}" >&2
  exit 1
fi

if grep -Eiq "^x-powered-by:" "${SERVER_HEADER_FILES[@]}"; then
  echo "X-Powered-By header is exposed; hide implementation details" >&2
  cat "${HEALTH_HEADERS}" >&2
  cat "${FRONTEND_HEADERS}" >&2
  exit 1
fi

if ! grep -q '"ok"[[:space:]]*:[[:space:]]*true' "${HEALTH_BODY}"; then
  echo "health endpoint did not return expected ok response" >&2
  cat "${HEALTH_BODY}" >&2
  exit 1
fi

if [[ "${API_ONLY}" != "1" ]]; then
  if ! grep -q 'id="root"' "${FRONTEND_BODY}"; then
    echo "frontend root page did not look like the Blank app shell" >&2
    cat "${FRONTEND_BODY}" >&2
    exit 1
  fi
fi

curl -fsS --max-time 10 --dump-header "${CORS_HEADERS}" --output /dev/null \
  -H "Origin: https://attacker.invalid" "${BASE_URL}/api/health" >/dev/null
if grep -Eiq "^access-control-allow-origin:[[:space:]]*https://attacker\\.invalid" "${CORS_HEADERS}"; then
  echo "unexpected Origin was allowed by CORS" >&2
  cat "${CORS_HEADERS}" >&2
  exit 1
fi

DOC_STATUS="$(curl -sS --max-time 10 --output /dev/null --write-out '%{http_code}' --dump-header "${DOC_HEADERS}" "${BASE_URL}/docs")"
if [[ "${DOC_STATUS}" != "404" && "${DOC_STATUS}" != "403" ]]; then
  echo "production API docs should not be public; /docs returned ${DOC_STATUS}" >&2
  cat "${DOC_HEADERS}" >&2
  exit 1
fi

OPENAPI_STATUS="$(curl -sS --max-time 10 --output /dev/null --write-out '%{http_code}' "${BASE_URL}/openapi.json")"
if [[ "${OPENAPI_STATUS}" != "404" && "${OPENAPI_STATUS}" != "403" ]]; then
  echo "production OpenAPI schema should not be public; /openapi.json returned ${OPENAPI_STATUS}" >&2
  exit 1
fi

HOST_STATUS="$(curl -sS --max-time 10 --output /dev/null --write-out '%{http_code}' --dump-header "${HOST_HEADERS}" -H "Host: attacker.invalid" "${BASE_URL}/api/health" || true)"
if [[ "${HOST_STATUS}" != "400" && "${HOST_STATUS}" != "403" && "${HOST_STATUS}" != "421" ]]; then
  echo "unexpected Host header was not rejected; got HTTP ${HOST_STATUS}" >&2
  cat "${HOST_HEADERS}" >&2
  exit 1
fi

echo "deployment URL security checks passed"
