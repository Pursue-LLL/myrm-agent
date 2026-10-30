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

# True while macOS routes keyboard input to pid $1. `lsappinfo front` agrees with WindowServer; System Events does not
# see IFM's feedback window as the front app and reports the app behind it instead, which let this fallback pull the
# front out from under the window the user was typing in.
chrome_e2e_is_front() {
  [[ "$(lsappinfo info -only pid "$(lsappinfo front 2>/dev/null)" 2>/dev/null)" == "\"pid\"=$1" ]]
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
  # Cheap filter: while Chrome is not the front (the usual case) no osascript is started at all.
  chrome_e2e_is_front "${chrome_pid}" || return 0
  # osascript needs a good fraction of a second to start and the front may move on meanwhile, so the same check
  # runs again inside the script, right before the restore.
  local script outcome
  IFS= read -r -d '' script <<'APPLESCRIPT' || true
on run argv
  set chromePid to item 1 of argv
  set savedPid to (item 2 of argv) as integer
  tell application "System Events" to set savedProc to first application process whose unix id is savedPid
  set frontInfo to do shell script "/usr/bin/lsappinfo info -only pid \"$(/usr/bin/lsappinfo front)\""
  if frontInfo is not ("\"pid\"=" & chromePid) then return "idle"
  tell application "System Events" to set frontmost of savedProc to true
  return "recovered"
end run
APPLESCRIPT
  outcome="$(osascript -e "${script}" "${chrome_pid}" "${saved_pid}" 2>/dev/null || true)"
  if [[ "${outcome}" == "recovered" ]]; then
    chrome_e2e_focus_recover_log "${chrome_pid}" "${saved_pid}"
  fi
  return 0
}
