#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NGINX_CONF="${ROOT_DIR}/deploy/nginx.blank.conf"
SYSTEMD_SERVICE="${ROOT_DIR}/deploy/blank-api.service"
ENV_EXAMPLE="${ROOT_DIR}/deploy/blank.env.example"
BACKUP_SERVICE="${ROOT_DIR}/deploy/blank-backup.service"
BACKUP_TIMER="${ROOT_DIR}/deploy/blank-backup.timer"
LOGROTATE_CONF="${ROOT_DIR}/deploy/logrotate.blank"
FAIL2BAN_FILTER="${ROOT_DIR}/deploy/fail2ban.blank-auth.conf"
FAIL2BAN_JAIL="${ROOT_DIR}/deploy/fail2ban.blank-jail.local"
COMPOSE_FILE="${ROOT_DIR}/compose.yaml"
INFRA_SCRIPT="${ROOT_DIR}/scripts/infra.sh"

require_file() {
  local file="$1"
  if [[ ! -f "${file}" ]]; then
    echo "missing deploy template: ${file}" >&2
    exit 1
  fi
}

require_pattern() {
  local file="$1"
  local pattern="$2"
  local description="$3"
  if ! grep -Eq -- "${pattern}" "${file}"; then
    echo "deploy template check failed: ${description}" >&2
    echo "file: ${file}" >&2
    exit 1
  fi
}

reject_pattern() {
  local file="$1"
  local pattern="$2"
  local description="$3"
  if grep -Eq -- "${pattern}" "${file}"; then
    echo "deploy template contains unsafe setting: ${description}" >&2
    echo "file: ${file}" >&2
    exit 1
  fi
}

require_file "${NGINX_CONF}"
require_file "${SYSTEMD_SERVICE}"
require_file "${ENV_EXAMPLE}"
require_file "${BACKUP_SERVICE}"
require_file "${BACKUP_TIMER}"
require_file "${LOGROTATE_CONF}"
require_file "${FAIL2BAN_FILTER}"
require_file "${FAIL2BAN_JAIL}"
require_file "${COMPOSE_FILE}"
require_file "${INFRA_SCRIPT}"

require_pattern "${NGINX_CONF}" "listen[[:space:]]+443[[:space:]]+ssl" "nginx must terminate HTTPS"
require_pattern "${NGINX_CONF}" "ssl_protocols[[:space:]]+TLSv1\\.2[[:space:]]+TLSv1\\.3" "nginx must disable old TLS versions"
require_pattern "${NGINX_CONF}" "Strict-Transport-Security.*max-age=63072000" "nginx must send HSTS"
require_pattern "${NGINX_CONF}" "Content-Security-Policy.*default-src 'self'.*frame-ancestors 'none'.*connect-src 'self'.*script-src 'self'" "nginx must send strict frontend CSP"
require_pattern "${NGINX_CONF}" "Cross-Origin-Opener-Policy.*same-origin" "nginx must send COOP"
require_pattern "${NGINX_CONF}" "Cross-Origin-Resource-Policy.*same-site" "nginx must send CORP"
require_pattern "${NGINX_CONF}" "server_tokens[[:space:]]+off" "nginx must hide version tokens"
require_pattern "${NGINX_CONF}" "proxy_hide_header[[:space:]]+Server" "nginx must hide upstream Server header"
require_pattern "${NGINX_CONF}" "proxy_hide_header[[:space:]]+X-Powered-By" "nginx must hide upstream X-Powered-By header"
require_pattern "${NGINX_CONF}" 'proxy_set_header[[:space:]]+Host[[:space:]]+\$host' "nginx must preserve Host for backend Host allowlist"
require_pattern "${NGINX_CONF}" "proxy_set_header[[:space:]]+X-Forwarded-Proto[[:space:]]+https" "nginx must forward HTTPS scheme"
require_pattern "${NGINX_CONF}" "proxy_pass[[:space:]]+http://127\\.0\\.0\\.1:8000" "nginx must proxy to loopback backend"
reject_pattern "${NGINX_CONF}" "proxy_pass[[:space:]]+http://0\\.0\\.0\\.0" "nginx must not proxy to wildcard bind"
reject_pattern "${NGINX_CONF}" "connect-src[^;]*(localhost|127\\.0\\.0\\.1|http://)" "production CSP must not allow development API origins"

require_pattern "${SYSTEMD_SERVICE}" "^User=blank$" "systemd service must use dedicated unprivileged user"
require_pattern "${SYSTEMD_SERVICE}" "--host[[:space:]]+127\\.0\\.0\\.1" "backend must bind to loopback behind proxy"
require_pattern "${SYSTEMD_SERVICE}" "--no-server-header" "uvicorn must not expose Server header"
require_pattern "${SYSTEMD_SERVICE}" "NoNewPrivileges=true" "systemd must block privilege escalation"
require_pattern "${SYSTEMD_SERVICE}" "ProtectSystem=strict" "systemd must protect filesystem"
require_pattern "${SYSTEMD_SERVICE}" "PrivateTmp=true" "systemd must isolate tmp"
require_pattern "${SYSTEMD_SERVICE}" "UMask=0077" "systemd must create private files"
require_pattern "${SYSTEMD_SERVICE}" "ReadWritePaths=/var/lib/blank /var/log/blank" "systemd write paths must be explicit"
require_pattern "${SYSTEMD_SERVICE}" "CapabilityBoundingSet=$" "systemd must drop Linux capabilities"
reject_pattern "${SYSTEMD_SERVICE}" "--host[[:space:]]+0\\.0\\.0\\.0" "backend must not bind publicly"

require_pattern "${ENV_EXAMPLE}" "^BLANK_ENV=production$" "production env must set BLANK_ENV"
require_pattern "${ENV_EXAMPLE}" "^BLANK_ALLOWED_HOSTS=blank\\.example\\.com$" "production env must pin allowed hosts"
require_pattern "${ENV_EXAMPLE}" "^BLANK_CORS_ORIGINS=https://blank\\.example\\.com$" "production env must pin HTTPS CORS origin"
require_pattern "${ENV_EXAMPLE}" "^BLANK_DATABASE_URL=postgresql://blank:replace-password@127\\.0\\.0\\.1:5432/blank$" "production env must configure PostgreSQL"
require_pattern "${ENV_EXAMPLE}" "^BLANK_REDIS_URL=redis://127\\.0\\.0\\.1:6379/0$" "production env must configure Redis"
require_pattern "${ENV_EXAMPLE}" "^BLANK_GRAPHRAG_ENABLED=true$" "production env must enable GraphRAG by default"
require_pattern "${ENV_EXAMPLE}" "^BLANK_NEO4J_PASSWORD=replace-with-strong-neo4j-password$" "production env must document Neo4j credentials"
require_pattern "${ENV_EXAMPLE}" "^BLANK_SECURITY_LOG_PATH=/var/log/blank/security\\.log$" "production env must write security events to managed log path"
require_pattern "${ENV_EXAMPLE}" "^BLANK_ALLOW_PRIVATE_MODEL_URLS=false$" "production env must block private model URLs"
require_pattern "${ENV_EXAMPLE}" "^BLANK_TRUSTED_PROXIES=127\\.0\\.0\\.1/32$" "production env must pin trusted proxy"
require_pattern "${ENV_EXAMPLE}" "^BLANK_COOKIE_SECURE=true$" "production env must force Secure cookies"
require_pattern "${ENV_EXAMPLE}" "^BLANK_COOKIE_SAMESITE=strict$" "production env must force strict SameSite"
reject_pattern "${ENV_EXAMPLE}" "localhost|127\\.0\\.0\\.1:5173|http://" "production env must not use dev origins"

require_pattern "${BACKUP_SERVICE}" "^User=blank$" "backup service must use dedicated unprivileged user"
require_pattern "${BACKUP_SERVICE}" "ExecStart=/opt/blank/scripts/backup-postgres\\.sh" "backup service must use repository backup script"
require_pattern "${BACKUP_SERVICE}" "BLANK_DATABASE_URL=postgresql://blank:replace-password@127\\.0\\.0\\.1:5432/blank" "backup service must use production PostgreSQL URL"
require_pattern "${BACKUP_SERVICE}" "BLANK_BACKUP_DIR=/var/backups/blank" "backup service must write to managed backup directory"
require_pattern "${BACKUP_SERVICE}" "UMask=0077" "backup service must create private backups"
require_pattern "${BACKUP_SERVICE}" "NoNewPrivileges=true" "backup service must block privilege escalation"
require_pattern "${BACKUP_SERVICE}" "ProtectSystem=strict" "backup service must protect filesystem"
require_pattern "${BACKUP_SERVICE}" "ReadWritePaths=/var/lib/blank /var/backups/blank" "backup service write paths must be explicit"

require_pattern "${BACKUP_TIMER}" "OnCalendar=\\*-\\*-\\* 00,06,12,18:15:00" "backup timer must run at least every 6 hours"
require_pattern "${BACKUP_TIMER}" "Persistent=true" "backup timer must catch up after downtime"
require_pattern "${BACKUP_TIMER}" "RandomizedDelaySec=10m" "backup timer must avoid thundering herd"

require_pattern "${LOGROTATE_CONF}" "/var/log/blank/\\*\\.log" "logrotate must cover Blank security logs"
require_pattern "${LOGROTATE_CONF}" "/var/log/nginx/blank\\.\\*\\.log" "logrotate must cover nginx Blank logs"
require_pattern "${LOGROTATE_CONF}" "rotate[[:space:]]+30" "logrotate must retain enough history"
require_pattern "${LOGROTATE_CONF}" "compress" "logrotate must compress old logs"
require_pattern "${LOGROTATE_CONF}" "create[[:space:]]+0600[[:space:]]+blank[[:space:]]+adm" "logrotate must create private logs"

require_pattern "${FAIL2BAN_FILTER}" "event=auth\\\\\\.login\\\\\\.failed[[:space:]]+ip=<HOST>" "fail2ban filter must match login failures"
require_pattern "${FAIL2BAN_FILTER}" "event=auth\\\\\\.reauth\\\\\\.failed[[:space:]]+ip=<HOST>" "fail2ban filter must match reauth failures"
require_pattern "${FAIL2BAN_JAIL}" "^\\[blank-auth\\]$" "fail2ban jail must define blank-auth"
require_pattern "${FAIL2BAN_JAIL}" "enabled[[:space:]]*=[[:space:]]*true" "fail2ban jail must be enabled"
require_pattern "${FAIL2BAN_JAIL}" "logpath[[:space:]]*=[[:space:]]*/var/log/blank/security\\.log" "fail2ban jail must watch security log"
require_pattern "${FAIL2BAN_JAIL}" "maxretry[[:space:]]*=[[:space:]]*8" "fail2ban jail must cap repeated failures"
require_pattern "${FAIL2BAN_JAIL}" "bantime[[:space:]]*=[[:space:]]*1h" "fail2ban jail must ban attackers"

require_pattern "${COMPOSE_FILE}" "image: pgvector/pgvector:pg16" "development compose must provide PostgreSQL with pgvector"
require_pattern "${COMPOSE_FILE}" "image: redis:7-alpine" "development compose must provide Redis"
require_pattern "${COMPOSE_FILE}" "image: neo4j:5\\.26-community" "development compose must provide Neo4j"
require_pattern "${COMPOSE_FILE}" "\"127\\.0\\.0\\.1:5432:5432\"" "PostgreSQL development port must bind to loopback"
require_pattern "${COMPOSE_FILE}" "\"127\\.0\\.0\\.1:6379:6379\"" "Redis development port must bind to loopback"
require_pattern "${COMPOSE_FILE}" "\"127\\.0\\.0\\.1:7687:7687\"" "Neo4j development port must bind to loopback"
reject_pattern "${COMPOSE_FILE}" "0\\.0\\.0\\.0:5432|0\\.0\\.0\\.0:6379|0\\.0\\.0\\.0:7687" "development databases must not bind publicly"
require_pattern "${INFRA_SCRIPT}" "blank_test" "infra script must create PostgreSQL test database"
require_pattern "${INFRA_SCRIPT}" "BLANK_TEST_DATABASE_URL=postgresql://blank:blank@127\\.0\\.0\\.1:5432/blank_test" "infra script must print test database URL"

echo "deploy template security checks passed"
