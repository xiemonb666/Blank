#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATABASE_URL="${BLANK_DATABASE_URL:-postgresql://blank:blank@127.0.0.1:5432/blank}"
YES=0

usage() {
  cat <<'EOF'
Usage: scripts/restore-postgres.sh [--yes] backup.dump

Environment:
  BLANK_DATABASE_URL  PostgreSQL connection string, default postgresql://blank:blank@127.0.0.1:5432/blank
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      YES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

SOURCE="${1:-}"
[[ -n "${SOURCE}" ]] || {
  usage >&2
  exit 2
}

command -v pg_restore >/dev/null 2>&1 || {
  echo "pg_restore is required" >&2
  exit 1
}

SOURCE_PATH="$(cd "$(dirname "${SOURCE}")" && pwd)/$(basename "${SOURCE}")"
[[ -f "${SOURCE_PATH}" ]] || {
  echo "backup not found: ${SOURCE}" >&2
  exit 1
}

if [[ "${YES}" != "1" ]]; then
  echo "This will restore ${SOURCE_PATH} into ${DATABASE_URL}." >&2
  echo "Re-run with --yes to confirm." >&2
  exit 3
fi

"${ROOT_DIR}/scripts/backup-postgres.sh" >/dev/null
pg_restore --clean --if-exists --no-owner --no-privileges --dbname="${DATABASE_URL}" "${SOURCE_PATH}"
echo "restored ${SOURCE_PATH}"
