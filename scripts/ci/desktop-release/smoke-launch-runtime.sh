#!/usr/bin/env bash
# Runtime smoke for a built desktop bundle: start the bundled Python sidecar (a PyInstaller one-folder
# tree) and the Next standalone server the way the Tauri shell does, then probe both over HTTP.
# Modes:
#   --bundle <dir>   Unpacked bundle root: a macOS .app, or an AppImage's squashfs-root
#   --dev            Monorepo paths (maintainer / pre-release local)
set -euo pipefail

API_PORT="${API_PORT:-8080}"
WEBUI_PORT="${WEBUI_PORT:-3000}"
HOST="${HOST:-127.0.0.1}"
POLL_INTERVAL_SEC="${POLL_INTERVAL_SEC:-0.5}"
# Same startup budget as the shell (BACKEND_STARTUP_TIMEOUT in python_backend.rs).
READY_TIMEOUT_SEC="${READY_TIMEOUT_SEC:-120}"
# A PyInstaller executable is tens of MB; anything under this is a placeholder.
MIN_BINARY_BYTES="${MIN_BINARY_BYTES:-1048576}"
# Next standalone server.js is a few KB; this only rejects empty or truncated files.
MIN_SERVER_JS_BYTES=1024

BACKEND_BIN=""
FRONTEND_DIR=""
backend_pid=""
frontend_pid=""
data_dir=""

usage() {
  cat <<'EOF'
Usage:
  smoke-launch-runtime.sh --bundle <path/to/MyrmAgent.app | path/to/squashfs-root>
  smoke-launch-runtime.sh --dev

Environment:
  API_PORT, WEBUI_PORT, HOST, POLL_INTERVAL_SEC, READY_TIMEOUT_SEC
EOF
}

fail() {
  echo "[launch-smoke] FAIL: $1" >&2
  exit 1
}

# SIGTERM first so the server shuts down cleanly; SIGKILL after 10 s so a hung shutdown cannot stall CI.
stop_process() {
  local pid="$1"
  kill "$pid" 2>/dev/null || return 0
  local waited=0
  while kill -0 "$pid" 2>/dev/null && [[ "$waited" -lt 50 ]]; do
    sleep 0.2
    waited=$((waited + 1))
  done
  kill -9 "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

cleanup() {
  [[ -z "${frontend_pid}" ]] || stop_process "${frontend_pid}"
  [[ -z "${backend_pid}" ]] || stop_process "${backend_pid}"
  [[ -z "${data_dir}" ]] || rm -rf "${data_dir}"
}
trap cleanup EXIT

assert_min_size_file() {
  local path="$1"
  local label="$2"
  local min_bytes="$3"
  [[ -f "$path" ]] || fail "${label} missing at ${path}"
  local size
  size="$(wc -c <"$path" | tr -d ' ')"
  if [[ "$size" -lt "$min_bytes" ]]; then
    fail "${label} looks like a stub (${size} bytes): ${path}"
  fi
}

resolve_bundle_paths() {
  local root="$1"
  [[ -d "$root" ]] || fail "bundle not found: ${root}"

  # The resource layout is the contract: a binaries/myrmagent-backend/ folder and a frontend/ folder. Each is
  # located on its own because an AppImage keeps the sidecar tree in usr/share/<product> and the frontend in
  # usr/lib/<product>. `|| true` keeps a find error from ending the script before the explicit message below.
  local sidecar_dirs sidecar_count
  sidecar_dirs="$(find "$root" -type d -path '*/binaries/myrmagent-backend' 2>/dev/null || true)"
  sidecar_count="$(printf '%s' "$sidecar_dirs" | grep -c . || true)"
  [[ "$sidecar_count" -eq 1 ]] || fail "expected one binaries/myrmagent-backend folder under ${root}, found ${sidecar_count}"
  BACKEND_BIN="${sidecar_dirs}/myrmagent-backend"

  # -prune: the first frontend/ on a path is the resource; folders of that name inside it are not candidates.
  local server_js
  server_js="$(find "$root" -type d -name frontend -prune -exec find {} -type f -name server.js \; 2>/dev/null | head -1 || true)"
  [[ -n "$server_js" ]] || fail "Next standalone server.js not found under a frontend/ folder in ${root}"
  FRONTEND_DIR="$(dirname "$server_js")"
}

resolve_dev_paths() {
  local script_dir repo_root binaries_dir
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  repo_root="$(cd "${script_dir}/../../.." && pwd)"
  binaries_dir="${repo_root}/myrm-agent-desktop/src-tauri/binaries"

  BACKEND_BIN="${binaries_dir}/myrmagent-backend/myrmagent-backend"
  FRONTEND_DIR="${repo_root}/myrm-agent-frontend/.next/standalone/myrm-agent-frontend"
}

wait_http_ok() {
  local url="$1"
  local label="$2"
  local watched_pid="$3"
  local started="$SECONDS"
  while (( SECONDS - started < READY_TIMEOUT_SEC )); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      echo "[launch-smoke] ${label} ready in $((SECONDS - started))s (${url})"
      return 0
    fi
    kill -0 "$watched_pid" 2>/dev/null || fail "${label} process exited before becoming ready (${url})"
    sleep "$POLL_INTERVAL_SEC"
  done
  fail "${label} not ready after ${READY_TIMEOUT_SEC}s (${url})"
}

start_backend() {
  assert_min_size_file "$BACKEND_BIN" "Backend sidecar" "$MIN_BINARY_BYTES"
  [[ -x "$BACKEND_BIN" ]] || fail "Backend sidecar is not executable: ${BACKEND_BIN}"
  [[ -d "$(dirname "$BACKEND_BIN")/_internal" ]] \
    || fail "Backend sidecar has no _internal/ next to it (not a one-folder build): ${BACKEND_BIN}"

  # A fresh data dir makes this the first launch of a new profile, the slowest path a user hits.
  data_dir="$(mktemp -d)"
  DEPLOY_MODE=local PORT="${API_PORT}" HOST="${HOST}" MYRM_DATA_DIR="${data_dir}" "$BACKEND_BIN" &
  backend_pid=$!
  echo "[launch-smoke] backend pid=${backend_pid} port=${API_PORT}"
}

start_frontend() {
  assert_min_size_file "${FRONTEND_DIR}/server.js" "Next standalone server.js" "$MIN_SERVER_JS_BYTES"
  (
    cd "$FRONTEND_DIR"
    PORT="${WEBUI_PORT}" HOSTNAME="${HOST}" API_PORT="${API_PORT}" exec node server.js
  ) &
  frontend_pid=$!
  echo "[launch-smoke] frontend pid=${frontend_pid} port=${WEBUI_PORT}"
}

main() {
  local mode=""
  local bundle=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --bundle)
        mode="bundle"
        bundle="${2:?--bundle requires path}"
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

  [[ -n "$mode" ]] || fail "specify --bundle or --dev"

  if [[ "$mode" == "bundle" ]]; then
    resolve_bundle_paths "$bundle"
  else
    resolve_dev_paths
  fi

  echo "[launch-smoke] backend=${BACKEND_BIN}"
  echo "[launch-smoke] frontend=${FRONTEND_DIR}"

  start_backend
  wait_http_ok "http://${HOST}:${API_PORT}/health" "Backend /health" "$backend_pid"

  start_frontend
  wait_http_ok "http://${HOST}:${WEBUI_PORT}/" "Next standalone" "$frontend_pid"

  echo "[launch-smoke] OK"
}

main "$@"
