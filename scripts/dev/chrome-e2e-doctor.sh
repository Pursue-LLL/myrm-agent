#!/usr/bin/env bash
# One-shot Chrome MCP E2E diagnostics (CDP, AOS, mux, automation permission).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MONOREPO_ROOT="$(cd "${AGENT_ROOT}/.." && pwd)"

_CHROME_E2E_DIR="${SCRIPT_DIR}/chrome-e2e"
# shellcheck source=chrome-e2e/runtime.sh
source "${_CHROME_E2E_DIR}/runtime.sh"
# shellcheck source=chrome-e2e/focus.sh
source "${_CHROME_E2E_DIR}/focus.sh"

PREFLIGHT_PY="${AGENT_ROOT}/myrm-agent-server/.venv/bin/python"
if [[ ! -x "${PREFLIGHT_PY}" ]]; then
  PREFLIGHT_PY="python3"
fi
export PREFLIGHT_PY

failures=0
ok() { echo "CHROME_E2E_DOCTOR_OK: $*"; }
warn() { echo "CHROME_E2E_DOCTOR_WARN: $*" >&2; }
fail() { echo "CHROME_E2E_DOCTOR_FAIL: $*" >&2; failures=$((failures + 1)); }

echo "CHROME_E2E_DOCTOR: starting"

if chrome_e2e_cdp_healthy && chrome_e2e_process_owns_port; then
  ok "cdp port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
else
  fail "cdp not healthy on :${MYRM_CHROME_E2E_PORT} — run: ./myrm ready --chrome"
fi

if [[ -f "${_CHROME_E2E_DIR}/surface.py" ]] && chrome_e2e_cdp_healthy; then
  if "${PREFLIGHT_PY}" "${_CHROME_E2E_DIR}/surface.py" ensure --cdp-port "${MYRM_CHROME_E2E_PORT}" 2>/dev/null | grep -q CHROME_E2E_SURFACE_OK; then
    ok "agent operating surface (AOS)"
  else
    warn "AOS ensure returned non-ok — focus fallback may still work"
  fi
  registry="$("${PREFLIGHT_PY}" "${_CHROME_E2E_DIR}/surface.py" registry 2>/dev/null || echo '{}')"
  if echo "${registry}" | grep -q windowId; then
    ok "AOS registry present"
  else
    warn "AOS registry empty"
  fi
fi

mux_bin="${MONOREPO_ROOT}/scripts/dev/cdmcp-mux-autoconnect/bin/cdmcp-mux-autoconnect.mjs"
if [[ -x "${mux_bin}" ]]; then
  ok "cdmcp-mux-autoconnect installed"
else
  fail "mux missing — run: bash scripts/dev/install-cdmcp-mux-autoconnect.sh"
fi

shim="${MONOREPO_ROOT}/scripts/dev/cdmcp-mux-autoconnect/lib/resilient-shim.mjs"
if [[ -f "${shim}" ]] && grep -q "chrome-e2e/cli.sh" "${shim}"; then
  ok "resilient-shim uses chrome-e2e CLI (no inline osascript)"
elif [[ -f "${shim}" ]]; then
  warn "resilient-shim may still use legacy suppress path — reload Cursor MCP"
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  if chrome_e2e_focus_capture | grep -qE '^[0-9]+$'; then
    ok "macOS automation (frontmost PID readable)"
  else
    fail "macOS automation blocked — grant Terminal/Cursor Automation for System Events"
  fi
fi

preflight="${SCRIPT_DIR}/chrome-e2e-preflight.sh"
if [[ -f "${preflight}" ]]; then
  ok "chrome-e2e-preflight present"
else
  fail "missing chrome-e2e-preflight.sh"
fi

if [[ "${failures}" -eq 0 ]]; then
  echo "CHROME_E2E_DOCTOR_READY"
  exit 0
fi
echo "CHROME_E2E_DOCTOR_NOT_READY failures=${failures}"
exit 1
