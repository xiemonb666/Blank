#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV_SCRIPT="${ROOT_DIR}/scripts/dev.sh"

env -u BLANK_BACKEND_HOST -u BLANK_FRONTEND_HOST -u BLANK_ALLOWED_HOSTS -u BLANK_CORS_ORIGINS \
  "${DEV_SCRIPT}" --check-security

if env -u BLANK_ALLOWED_HOSTS -u BLANK_CORS_ORIGINS BLANK_BACKEND_HOST=0.0.0.0 \
  "${DEV_SCRIPT}" --check-security >/tmp/blank-dev-security.out 2>&1; then
  echo "expected remote backend without Host/CORS configuration to fail" >&2
  exit 1
fi

if ! grep -q "BLANK_ALLOWED_HOSTS" /tmp/blank-dev-security.out; then
  echo "expected missing Host/CORS error to mention BLANK_ALLOWED_HOSTS" >&2
  exit 1
fi

env BLANK_BACKEND_HOST=0.0.0.0 BLANK_ALLOWED_HOSTS=blank.local BLANK_CORS_ORIGINS=https://blank.local \
  "${DEV_SCRIPT}" --check-security
