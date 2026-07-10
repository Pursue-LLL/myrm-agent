#!/usr/bin/env bash
# Shared Myrm E2E Chrome paths (zero Allow — launched with --remote-debugging-port).
set -euo pipefail

MYRM_CHROME_E2E_PORT="${MYRM_CHROME_E2E_PORT:-9333}"
MYRM_CHROME_E2E_BROWSER_URL="http://127.0.0.1:${MYRM_CHROME_E2E_PORT}"

if [[ -z "${MYRM_CHROME_E2E_DATA_DIR:-}" ]]; then
  case "$(uname -s)" in
    Darwin)
      MYRM_CHROME_E2E_DATA_DIR="${HOME}/Library/Application Support/Myrm/ChromeE2E"
      ;;
    Linux)
      MYRM_CHROME_E2E_DATA_DIR="${HOME}/.local/share/myrm/chrome-e2e"
      ;;
    *)
      MYRM_CHROME_E2E_DATA_DIR="${HOME}/.myrm/chrome-e2e"
      ;;
  esac
fi

if [[ -z "${MYRM_CHROME_BIN:-}" || ! -x "${MYRM_CHROME_BIN}" ]]; then
  case "$(uname -s)" in
    Darwin)
      MYRM_CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
      ;;
    Linux)
      MYRM_CHROME_BIN=""
      for candidate in google-chrome google-chrome-stable chromium chromium-browser; do
        if command -v "${candidate}" >/dev/null 2>&1; then
          MYRM_CHROME_BIN="$(command -v "${candidate}")"
          break
        fi
      done
      ;;
  esac
fi

MYRM_CHROME_E2E_ACTIVE_PORT_FILE="${MYRM_CHROME_E2E_DATA_DIR}/DevToolsActivePort"

myrm_chrome_e2e_cdp_healthy() {
  curl -sf --max-time 3 "${MYRM_CHROME_E2E_BROWSER_URL}/json/version" >/dev/null 2>&1
}

myrm_chrome_e2e_process_owns_port() {
  local pid
  pid="$(lsof -tiTCP:"${MYRM_CHROME_E2E_PORT}" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
  [[ -n "${pid}" ]] || return 1
  local cmdline
  cmdline="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
  [[ "${cmdline}" == *"${MYRM_CHROME_E2E_DATA_DIR}"* ]]
}
