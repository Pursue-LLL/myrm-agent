#!/usr/bin/env bash
# Chrome E2E lifecycle transitions: surface PRIMARY + focus FALLBACK.
set -euo pipefail

_CHROME_E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runtime.sh
source "${_CHROME_E2E_DIR}/runtime.sh"
# shellcheck source=focus.sh
source "${_CHROME_E2E_DIR}/focus.sh"

chrome_e2e_surface_py() {
  printf '%s' "${_CHROME_E2E_DIR}/surface.py"
}

chrome_e2e_surface_ensure() {
  local py="${PREFLIGHT_PY:-python3}"
  local surface_py
  surface_py="$(chrome_e2e_surface_py)"
  [[ -f "${surface_py}" ]] || return 0
  if ! chrome_e2e_cdp_healthy; then
    return 0
  fi
  "${py}" "${surface_py}" ensure --cdp-port "${MYRM_CHROME_E2E_PORT}" >/dev/null 2>&1 || true
}

chrome_e2e_lifecycle_transition() {
  local event="${1:-}"
  local saved_pid="${2:-}"
  case "${event}" in
    cold-start-done|warmup-navigate|warmup-done|mcp-page|preflight-done)
      chrome_e2e_surface_ensure
      chrome_e2e_focus_recover "${saved_pid}"
      ;;
    *)
      return 0
      ;;
  esac
}
