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

chrome_e2e_focus_recover() {
  local saved_pid="${1:-${MYRM_CHROME_E2E_SAVED_FRONTMOST_PID:-}}"
  [[ "$(uname -s)" == "Darwin" ]] || return 0
  [[ "${MYRM_CHROME_E2E_FOREGROUND:-0}" == "1" ]] && return 0
  local chrome_pid
  chrome_pid="$(chrome_e2e_owner_pid)"
  [[ -n "${chrome_pid}" ]] || return 0
  if [[ -z "${saved_pid}" || ! "${saved_pid}" =~ ^[0-9]+$ ]]; then
    saved_pid="$(chrome_e2e_focus_capture)"
  fi
  if [[ "${saved_pid}" =~ ^[0-9]+$ ]]; then
    osascript <<EOF 2>/dev/null || true
tell application "System Events"
  try
    set chromeProc to first application process whose unix id is ${chrome_pid}
    repeat with w in (every window of chromeProc)
      set miniaturized of w to true
    end repeat
  end try
  try
    set frontProc to first application process whose unix id is ${saved_pid}
    set frontmost of frontProc to true
  end try
end tell
EOF
  else
    osascript <<EOF 2>/dev/null || true
tell application "System Events"
  try
    set chromeProc to first application process whose unix id is ${chrome_pid}
    repeat with w in (every window of chromeProc)
      set miniaturized of w to true
    end repeat
  end try
end tell
EOF
  fi
}
