#!/usr/bin/env bash
# Unified CLI for mux shim and Python callers (no osascript in Node).
set -euo pipefail

_CHROME_E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lifecycle.sh
source "${_CHROME_E2E_DIR}/lifecycle.sh"

usage() {
  echo "Usage: chrome-e2e-cli.sh <capture-focus|recover-focus|ensure-surface|transition> [args]" >&2
}

cmd="${1:-}"
shift || true

case "${cmd}" in
  capture-focus)
    chrome_e2e_focus_capture
    ;;
  recover-focus)
    chrome_e2e_lifecycle_transition "mcp-page" "${1:-${MYRM_CHROME_E2E_SAVED_FRONTMOST_PID:-}}"
    ;;
  ensure-surface)
    chrome_e2e_surface_ensure
    ;;
  transition)
    event="${1:-}"
    saved_pid="${2:-}"
    chrome_e2e_lifecycle_transition "${event}" "${saved_pid}"
    ;;
  hil-show)
    py="${PREFLIGHT_PY:-python3}"
    target_id="${1:-}"
    message="${2:-Human action required on this page}"
    [[ -n "${target_id}" ]] || exit 1
    "${py}" "${_CHROME_E2E_DIR}/hil.py" --target-id "${target_id}" --message "${message}"
    ;;
  "")
    usage
    exit 1
    ;;
  *)
    usage
    exit 1
    ;;
esac
