#!/usr/bin/env bash
# Desktop TCC recovery — re-anchor the backend under the current (granted) shell.
# macOS attributes Accessibility/Screen Recording to the backend's process chain:
# a backend re-spawned under launchd loses the grant even though the port stays
# up. This script probes /webui/desktop/permissions and, only when Accessibility
# is missing, TERM-kills the port owner and cold-starts via _start_backend_bg
# from THIS shell so the new backend inherits the caller's TCC chain.
# Usage: ./desktop-tcc-recover.sh [--port 8080]
# Idempotent: exits 0 without touching anything when Accessibility is granted.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
# shellcheck source=lib/backend_bg.sh
source "${SCRIPT_DIR}/lib/backend_bg.sh"
# shellcheck source=lib/dev_state_paths.sh
source "${SCRIPT_DIR}/lib/dev_state_paths.sh"
resolve_agent_paths "${REPO_ROOT}"

BACKEND_PORT="${MYRM_BACKEND_PORT:-${PORT:-8080}}"
for arg in "$@"; do
  case "${arg}" in
    --port=*) BACKEND_PORT="${arg#--port=}" ;;
    --port) shift; BACKEND_PORT="${1:-${BACKEND_PORT}}" ;;
  esac
done
PERM_URL="http://127.0.0.1:${BACKEND_PORT}/webui/desktop/permissions"

probe_ax() {
  python3 -c '
import json, sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=10) as r:
        print("true" if json.loads(r.read().decode()).get("accessibility") else "false")
except OSError:
    print("unknown")
' "${PERM_URL}"
}

ax="$(probe_ax)"
if [[ "${ax}" == "true" ]]; then
  echo "TCC_OK: backend :${BACKEND_PORT} Accessibility granted — nothing to do"
  exit 0
fi
echo "TCC_MISS: backend :${BACKEND_PORT} Accessibility=${ax} — re-anchoring under current shell" >&2

owner="$(lsof -nP -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
if [[ -n "${owner}" ]]; then
  kill -TERM "${owner}" 2>/dev/null || true
  for _ in $(seq 1 20); do
    dev_pid_alive "${owner}" || break
    sleep 0.25
  done
  if dev_pid_alive "${owner}"; then
    kill -KILL "${owner}" 2>/dev/null || true
  fi
  for _ in $(seq 1 20); do
    if ! lsof -nP -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN -t >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
fi

if ! _start_backend_bg "${SERVER_DIR}"; then
  echo "TCC_FAIL: backend cold start failed — see backend.log" >&2
  exit 1
fi

ax_after="$(probe_ax)"
if [[ "${ax_after}" == "true" ]]; then
  echo "TCC_OK: backend :${BACKEND_PORT} re-anchored, Accessibility granted"
  exit 0
fi
echo "TCC_FAIL: backend restarted but Accessibility=${ax_after} — grant the terminal/IDE in System Settings → Privacy & Security → Accessibility, then rerun" >&2
exit 1
