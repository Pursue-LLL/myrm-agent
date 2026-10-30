#!/usr/bin/env bash
# macOS focus FALLBACK for Myrm E2E Chrome (single osascript entry).
set -euo pipefail

_CHROME_E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runtime.sh
source "${_CHROME_E2E_DIR}/runtime.sh"

chrome_e2e_focus_capture() {
  [[ "$(uname -s)" == "Darwin" ]] || return 0
  osascript -e 'tell application "System Events"
    set frontProc to first application process whose frontmost is true
    return unix id of frontProc
  end tell' 2>/dev/null || true
}

# One line per real recovery: whether this fallback is still needed is answered by this log, not by guesswork.
chrome_e2e_focus_recover_log() {
  mkdir -p "${MYRM_CHROME_E2E_STATE_DIR}" 2>/dev/null || return 0
  printf '%s chrome_pid=%s restored_pid=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$1" "$2" \
    >>"${MYRM_CHROME_E2E_STATE_DIR}/chrome-e2e-focus-recover.log" 2>/dev/null || true
}

# Hand the front back to the app the user was in, but ONLY while the dedicated E2E Chrome itself holds the front.
# Any other front app means the user has already moved on; re-activating the saved app would then hijack their focus.
# Never minimizes windows: a minimized window is hidden, freezes rAF and strands React on its skeleton
# (scripts/dev/CHROME_MCP_E2E.md, window visibility policy).
chrome_e2e_focus_recover() {
  local saved_pid="${1:-${MYRM_CHROME_E2E_SAVED_FRONTMOST_PID:-}}"
  [[ "$(uname -s)" == "Darwin" ]] || return 0
  [[ "${MYRM_CHROME_E2E_FOREGROUND:-0}" == "1" ]] && return 0
  local chrome_pid
  chrome_pid="$(chrome_e2e_owner_pid)"
  if [[ ! "${chrome_pid}" =~ ^[0-9]+$ || ! "${saved_pid}" =~ ^[0-9]+$ ]]; then
    return 0
  fi
  local script outcome
  printf -v script '%s\n' \
    'tell application "System Events"' \
    "  if (unix id of first application process whose frontmost is true) is not ${chrome_pid} then return \"idle\"" \
    '  try' \
    "    set frontmost of (first application process whose unix id is ${saved_pid}) to true" \
    '  end try' \
    '  return "recovered"' \
    'end tell'
  outcome="$(osascript -e "${script}" 2>/dev/null || true)"
  if [[ "${outcome}" == "recovered" ]]; then
    chrome_e2e_focus_recover_log "${chrome_pid}" "${saved_pid}"
  fi
  return 0
}
