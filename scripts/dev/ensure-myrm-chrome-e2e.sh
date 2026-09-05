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

if [[ "$(uname -s)" == "Darwin" ]]; then
  MYRM_CHROME_APP="$(myrm_chrome_e2e_default_app)"
  if [[ ! -d "${MYRM_CHROME_APP}" ]]; then
    fail "Chrome.app not found at ${MYRM_CHROME_APP} — set MYRM_CHROME_APP or MYRM_CHROME_BIN"
  fi
elif [[ ! -x "${MYRM_CHROME_BIN:-}" ]]; then
  fail "Google Chrome not found — set MYRM_CHROME_BIN or install Chrome"
fi

mkdir -p "${MYRM_CHROME_E2E_DATA_DIR}"

if myrm_chrome_e2e_cdp_healthy && myrm_chrome_e2e_process_owns_port; then
  chrome_e2e_surface_ensure
  if myrm_chrome_e2e_launch_background; then
    chrome_e2e_lifecycle_transition "cold-start-done" "$(myrm_chrome_e2e_save_frontmost_pid)"
  fi
  ok "already running port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
  exit 0
fi

if lsof -iTCP:"${MYRM_CHROME_E2E_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  # R174: CDP /json/version is SSOT — lsof listener pid can race under parallel attach.
  if myrm_chrome_e2e_cdp_healthy; then
    chrome_e2e_surface_ensure
    ok "already running port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
    exit 0
  fi
  if ! myrm_chrome_e2e_process_owns_port; then
    fail "Port ${MYRM_CHROME_E2E_PORT} is in use by a non-Myrm Chrome — free the port or set MYRM_CHROME_E2E_PORT"
  fi
  stale_owner="$(myrm_chrome_e2e_owner_pid)"
  [[ -n "${stale_owner}" ]] \
    || fail "owned unhealthy Chrome listener has no resolvable pid on port ${MYRM_CHROME_E2E_PORT}"
  echo "MYRM_CHROME_E2E_HEAL: terminate unhealthy dedicated listener pid=${stale_owner} port=${MYRM_CHROME_E2E_PORT}" >&2
  kill "${stale_owner}" 2>/dev/null || true
  for _ in $(seq 1 30); do
    if ! kill -0 "${stale_owner}" 2>/dev/null \
      && ! lsof -iTCP:"${MYRM_CHROME_E2E_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done
  if kill -0 "${stale_owner}" 2>/dev/null; then
    kill -9 "${stale_owner}" 2>/dev/null || true
  fi
  for _ in $(seq 1 20); do
    if ! lsof -iTCP:"${MYRM_CHROME_E2E_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done
  lsof -iTCP:"${MYRM_CHROME_E2E_PORT}" -sTCP:LISTEN >/dev/null 2>&1 \
    && fail "unhealthy dedicated Chrome still owns port ${MYRM_CHROME_E2E_PORT} after exact-pid recovery"
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
  # Silence crash recovery bubble & crash reports
  --disable-session-crashed-bubble
  --disable-infobars
  --hide-crash-restore-bubble
  --disable-breakpad
  --no-crash-upload
  # Playwright-standard render flags: keep occluded/non-frontmost windows
  # rendering so E2E never needs Page.bringToFront (which steals macOS
  # focus from the user's active app) to unblock requestAnimationFrame.
  # Without these, a window that is merely not frontmost is treated as
  # occluded → document.visibilityState='hidden' → React freezes on its
  # skeleton (§26.21 focus-theft fix).
  --disable-backgrounding-occluded-windows
  --disable-renderer-backgrounding
  --disable-background-timer-throttling
)

# Reset crash flags in Preferences if present to suppress restore bubble
python3 -c "
import json, os
for rel in ['Default/Preferences', 'Profile 1/Preferences']:
    p = os.path.join('${MYRM_CHROME_E2E_DATA_DIR}', rel)
    if os.path.isfile(p):
        try:
            with open(p, 'r') as f: data = json.load(f)
            if isinstance(data, dict) and 'profile' in data and isinstance(data['profile'], dict):
                data['profile']['exit_type'] = 'Normal'
                data['profile']['exited_cleanly'] = True
                with open(p, 'w') as f: json.dump(data, f)
        except Exception: pass
" 2>/dev/null || true
if myrm_chrome_e2e_launch_background; then
  CHROME_LAUNCH_ARGS+=(--window-position=-24000,-24000)
elif [[ "$(uname -s)" == "Linux" ]]; then
  CHROME_LAUNCH_ARGS+=(--window-position=-24000,-24000)
fi
CHROME_LAUNCH_ARGS+=("${START_URL}")
if [[ "$(uname -s)" == "Darwin" ]]; then
  OPEN_ARCH_FLAGS=()
  if [[ "$(uname -m)" == "arm64" ]] || [[ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" == "1" ]]; then
    OPEN_ARCH_FLAGS+=(--arch arm64)
  fi
  if myrm_chrome_e2e_launch_background; then
    echo "MYRM_CHROME_E2E_START: macOS background launch (about:blank; set MYRM_CHROME_E2E_FOREGROUND=1 to foreground)" >&2
    open "${OPEN_ARCH_FLAGS[@]}" -gj -na "${MYRM_CHROME_APP}" --args "${CHROME_LAUNCH_ARGS[@]}"
  else
    echo "MYRM_CHROME_E2E_START: macOS foreground launch (${START_URL})" >&2
    open "${OPEN_ARCH_FLAGS[@]}" -na "${MYRM_CHROME_APP}" --args "${CHROME_LAUNCH_ARGS[@]}"
  fi
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
  chrome_e2e_lifecycle_transition "cold-start-done" "${SAVED_FRONTMOST_PID}"
fi

ok "started port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
echo "MYRM_CHROME_E2E_HINT: first run — log in once in Myrm E2E Chrome (Cmd+Tab or MYRM_CHROME_E2E_FOREGROUND=1); session persists for unattended MCP E2E" >&2
