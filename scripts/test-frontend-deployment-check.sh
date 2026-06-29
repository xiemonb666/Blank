#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
SERVER_PID=""

cleanup() {
  if [[ -n "${SERVER_PID}" ]]; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

SERVER_SCRIPT="${TMP_DIR}/frontend_probe_server.py"
cat >"${SERVER_SCRIPT}" <<'PY'
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


API_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(self), geolocation=(), payment=()",
    "Content-Security-Policy": "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'; connect-src 'none'",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
}

FRONTEND_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(self), geolocation=(), payment=()",
    "Content-Security-Policy": "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; manifest-src 'self'",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
}


class Handler(BaseHTTPRequestHandler):
    def send_response(self, code, message=None):
        self.log_request(code)
        self.send_response_only(code, message)

    def log_message(self, format, *args):
        return

    def reject_bad_host(self):
        host = self.headers.get("Host", "")
        if host.startswith("attacker.invalid"):
            self.send_response(421)
            self.end_headers()
            return True
        return False

    def write_response(self, status, headers, body, content_type):
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.reject_bad_host():
            return
        if self.path == "/api/health":
            self.write_response(200, API_HEADERS, b'{"ok":true,"service":"blank-api"}', "application/json")
            return
        if self.path in {"/docs", "/openapi.json"}:
            self.write_response(404, API_HEADERS, b"not found", "text/plain")
            return
        if self.path == "/":
            body = b'<!doctype html><html><body><div id="root"></div></body></html>'
            self.write_response(200, FRONTEND_HEADERS, body, "text/html; charset=utf-8")
            return
        self.write_response(404, API_HEADERS, b"not found", "text/plain")


ThreadingHTTPServer(("127.0.0.1", 18081), Handler).serve_forever()
PY

python3 "${SERVER_SCRIPT}" >"${TMP_DIR}/server.log" 2>&1 &
SERVER_PID="$!"

for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:18081/api/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -fsS http://127.0.0.1:18081/api/health >/dev/null 2>&1; then
  echo "frontend deployment probe server did not become ready" >&2
  cat "${TMP_DIR}/server.log" >&2
  exit 1
fi

"${ROOT_DIR}/scripts/check-deployment-url.sh" --allow-local-http http://127.0.0.1:18081
