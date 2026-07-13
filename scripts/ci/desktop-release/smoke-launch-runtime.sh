#!/usr/bin/env bash
# Post-build runtime smoke: start bundled Python + Next standalone and probe /health.
# Modes:
#   --bundle-app <MyrmAgent.app>  Release CI after `tauri build`
#   --dev                         Monorepo paths (maintainer / pre-release local)
set -euo pipefail

API_PORT="${API_PORT:-8080}"
WEBUI_PORT="${WEBUI_PORT:-3000}"
HOST="${HOST:-127.0.0.1}"
POLL_INTERVAL_SEC="${POLL_INTERVAL_SEC:-0.5}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-120}"
MIN_BINARY_BYTES="${MIN_BINARY_BYTES:-1024}"

BACKEND_BIN=""
FRONTEND_DIR=""
backend_pid=""
frontend_pid=""

usage() {
  cat <<'EOF'
Usage:
  smoke-launch-runtime.sh --bundle-app <path/to/MyrmAgent.app>
  smoke-launch-runtime.sh --dev

Environment:
  API_PORT, WEBUI_PORT, HOST, POLL_INTERVAL_SEC, MAX_ATTEMPTS
EOF
}

fail() {
  echo "[launch-smoke] FAIL: $1" >&2
  exit 1
}

cleanup() {
  if [[ -n "${frontend_pid}" ]]; then
    kill "${frontend_pid}" 2>/dev/null || true
    wait "${frontend_pid}" 2>/dev/null || true
  fi
  if [[ -n "${backend_pid}" ]]; then
    kill "${backend_pid}" 2>/dev/null || true
    wait "${backend_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

assert_non_empty_file() {
  local path="$1"
  local label="$2"
  [[ -f "$path" ]] || fail "${label} missing at ${path}"
  local size
  size="$(wc -c <"$path" | tr -d ' ')"
  if [[ "$size" -lt "$MIN_BINARY_BYTES" ]]; then
    fail "${label} looks like a stub (${size} bytes): ${path}"
  fi
}

resolve_bundle_paths() {
  local app="$1"
  [[ -d "$app" ]] || fail "bundle app not found: ${app}"

  BACKEND_BIN="$(find "$app/Contents/MacOS" -maxdepth 1 -type f -name 'myrmagent-backend*' 2>/dev/null | head -1)"
  [[ -n "$BACKEND_BIN" ]] || fail "backend sidecar not found under ${app}/Contents/MacOS"

  local server_js
  server_js="$(find "$app/Contents/Resources/frontend" -name 'server.js' -type f 2>/dev/null | head -1)"
  [[ -n "$server_js" ]] || fail "Next standalone server.js not found under ${app}/Contents/Resources/frontend"
  FRONTEND_DIR="$(dirname "$server_js")"
}

resolve_dev_paths() {
  local script_dir repo_root host
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  repo_root="$(cd "${script_dir}/../../.." && pwd)"
  host="$(rustc -vV | sed -n 's/^host: //p')"

  BACKEND_BIN="${repo_root}/myrm-agent-desktop/src-tauri/binaries/myrmagent-backend-${host}"
  FRONTEND_DIR="${repo_root}/myrm-agent-frontend/.next/standalone/myrm-agent-frontend"
}

wait_http_ok() {
  local url="$1"
  local label="$2"
  local attempt=0
  while [[ "$attempt" -lt "$MAX_ATTEMPTS" ]]; do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      echo "[launch-smoke] ${label} ready (${url})"
      return 0
    fi
    attempt=$((attempt + 1))
    sleep "$POLL_INTERVAL_SEC"
  done
  fail "${label} not ready after ${MAX_ATTEMPTS} attempts (${url})"
}

start_backend() {
  assert_non_empty_file "$BACKEND_BIN" "Backend sidecar"
  DEPLOY_MODE=local PORT="${API_PORT}" HOST="${HOST}" "$BACKEND_BIN" &
  backend_pid=$!
  echo "[launch-smoke] backend pid=${backend_pid} port=${API_PORT}"
}

start_frontend() {
  assert_non_empty_file "${FRONTEND_DIR}/server.js" "Next standalone server.js"
  (
    cd "$FRONTEND_DIR"
    PORT="${WEBUI_PORT}" HOSTNAME="${HOST}" API_PORT="${API_PORT}" exec node server.js
  ) &
  frontend_pid=$!
  echo "[launch-smoke] frontend pid=${frontend_pid} port=${WEBUI_PORT}"
}

main() {
  local mode=""
  local bundle_app=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --bundle-app)
        mode="bundle"
        bundle_app="${2:?--bundle-app requires path}"
        shift 2
        ;;
      --dev)
        mode="dev"
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        fail "unknown argument: $1"
        ;;
    esac
  done

  [[ -n "$mode" ]] || fail "specify --bundle-app or --dev"

  if [[ "$mode" == "bundle" ]]; then
    resolve_bundle_paths "$bundle_app"
  else
    resolve_dev_paths
  fi

  echo "[launch-smoke] backend=${BACKEND_BIN}"
  echo "[launch-smoke] frontend=${FRONTEND_DIR}"

  start_backend
  wait_http_ok "http://${HOST}:${API_PORT}/health" "Backend /health"

  start_frontend
  wait_http_ok "http://${HOST}:${WEBUI_PORT}/" "Next standalone"

  echo "[launch-smoke] OK"
}

main "$@"
