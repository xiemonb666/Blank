#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${1:-${BLANK_BACKUP_DIR:-${ROOT_DIR}/backups}}"
DATABASE_URL="${BLANK_DATABASE_URL:-postgresql://blank:blank@127.0.0.1:5432/blank}"

usage() {
  cat <<'EOF'
Usage: scripts/backup-postgres.sh [backup-dir]

Environment:
  BLANK_DATABASE_URL  PostgreSQL connection string, default postgresql://blank:blank@127.0.0.1:5432/blank
  BLANK_BACKUP_DIR    Backup directory when no positional backup-dir is given.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

command -v pg_dump >/dev/null 2>&1 || {
  echo "pg_dump is required" >&2
  exit 1
}

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}" 2>/dev/null || true

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_PATH="${BACKUP_DIR}/blank-${STAMP}.dump"

pg_dump --format=custom --no-owner --no-privileges --file="${BACKUP_PATH}" "${DATABASE_URL}"
chmod 600 "${BACKUP_PATH}" 2>/dev/null || true

echo "${BACKUP_PATH}"
