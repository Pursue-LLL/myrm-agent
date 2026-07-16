#!/usr/bin/env bash
# Launch or verify Myrm dedicated E2E Chrome (:9333, no Allow modal).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=myrm-chrome-e2e-lib.sh
source "${SCRIPT_DIR}/myrm-chrome-e2e-lib.sh"

fail() {
  echo "MYRM_CHROME_E2E_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "MYRM_CHROME_E2E_OK: $*"
}

if myrm_chrome_e2e_launch_background; then
  MYRM_CHROME_APP="$(myrm_chrome_e2e_default_app)"
  if [[ ! -d "${MYRM_CHROME_APP}" ]]; then
    fail "Chrome.app not found at ${MYRM_CHROME_APP} — set MYRM_CHROME_APP or MYRM_CHROME_BIN"
  fi
elif [[ ! -x "${MYRM_CHROME_BIN:-}" ]]; then
  fail "Google Chrome not found — set MYRM_CHROME_BIN or install Chrome"
fi

mkdir -p "${MYRM_CHROME_E2E_DATA_DIR}"

if myrm_chrome_e2e_cdp_healthy && myrm_chrome_e2e_process_owns_port; then
  ok "already running port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
  exit 0
fi

if lsof -iTCP:"${MYRM_CHROME_E2E_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  if ! myrm_chrome_e2e_process_owns_port; then
    fail "Port ${MYRM_CHROME_E2E_PORT} is in use by a non-Myrm Chrome — free the port or set MYRM_CHROME_E2E_PORT"
  fi
fi

echo "MYRM_CHROME_E2E_START: launching Chrome port=${MYRM_CHROME_E2E_PORT}" >&2
SAVED_FRONTMOST_PID=""
if myrm_chrome_e2e_launch_background; then
  SAVED_FRONTMOST_PID="$(myrm_chrome_e2e_save_frontmost_pid)"
fi
START_URL="about:blank"
if ! myrm_chrome_e2e_launch_background; then
  if curl -sf --max-time 3 "http://127.0.0.1:3000/" >/dev/null 2>&1; then
    START_URL="http://127.0.0.1:3000/"
  fi
fi
CHROME_LAUNCH_ARGS=(
  --user-data-dir="${MYRM_CHROME_E2E_DATA_DIR}"
  --remote-debugging-port="${MYRM_CHROME_E2E_PORT}"
  --remote-debugging-address=127.0.0.1
  --no-first-run
  --no-default-browser-check
)
if myrm_chrome_e2e_launch_background; then
  CHROME_LAUNCH_ARGS+=(--window-position=-24000,-24000)
elif [[ "$(uname -s)" == "Linux" ]]; then
  CHROME_LAUNCH_ARGS+=(--window-position=-24000,-24000)
fi
CHROME_LAUNCH_ARGS+=("${START_URL}")
if myrm_chrome_e2e_launch_background; then
  echo "MYRM_CHROME_E2E_START: macOS background launch (about:blank; set MYRM_CHROME_E2E_FOREGROUND=1 to foreground)" >&2
  open -gj -na "${MYRM_CHROME_APP}" --args "${CHROME_LAUNCH_ARGS[@]}"
else
  nohup "${MYRM_CHROME_BIN}" "${CHROME_LAUNCH_ARGS[@]}" >/dev/null 2>&1 &
fi

ready=0
for _ in $(seq 1 45); do
  if myrm_chrome_e2e_cdp_healthy; then
    ready=1
    break
  fi
  sleep 1
done

if [[ "${ready}" -ne 1 ]]; then
  fail "Chrome CDP not ready on port ${MYRM_CHROME_E2E_PORT} after 45s"
fi

if [[ -n "${SAVED_FRONTMOST_PID}" ]]; then
  myrm_chrome_e2e_suppress_ui "${SAVED_FRONTMOST_PID}"
fi

ok "started port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
echo "MYRM_CHROME_E2E_HINT: first run — log in once in Myrm E2E Chrome (Cmd+Tab or MYRM_CHROME_E2E_FOREGROUND=1); session persists for unattended MCP E2E" >&2
