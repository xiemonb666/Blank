#!/usr/bin/env sh
set -eu

BACKEND_PORT="${BLANK_INTERNAL_BACKEND_PORT:-8000}"

stop_children() {
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
  if [ -n "${NGINX_PID:-}" ]; then
    kill "${NGINX_PID}" >/dev/null 2>&1 || true
  fi
}

trap 'stop_children; exit 143' INT TERM

cd /app/backend
python -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port "${BACKEND_PORT}" \
  --no-server-header &
BACKEND_PID="$!"

nginx -c /etc/nginx/nginx.conf -g 'daemon off;' &
NGINX_PID="$!"

while :; do
  if ! kill -0 "${BACKEND_PID}" >/dev/null 2>&1; then
    wait "${BACKEND_PID}" || exit $?
    exit 1
  fi
  if ! kill -0 "${NGINX_PID}" >/dev/null 2>&1; then
    wait "${NGINX_PID}" || exit $?
    exit 1
  fi
  sleep 1
done
