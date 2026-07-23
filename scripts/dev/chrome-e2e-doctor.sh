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

upstream_js="${MONOREPO_ROOT}/scripts/dev/cdmcp-mux-autoconnect/node_modules/chrome-devtools-mcp-mux/dist/daemon/upstream.js"
if [[ -f "${upstream_js}" ]] && grep -q '?? 180000' "${upstream_js}" && ! grep -q '?? 55000' "${upstream_js}"; then
  ok "mux upstream patch default timeout=180000"
else
  fail "mux upstream patch drift — run: bash scripts/dev/install-cdmcp-mux-autoconnect.sh"
fi

pages_js="${MONOREPO_ROOT}/scripts/dev/cdmcp-mux-autoconnect/node_modules/chrome-devtools-mcp/build/src/tools/pages.js"
if [[ -f "${pages_js}" ]] && grep -q 'Myrm exact targetId' "${pages_js}"; then
  ok "chrome-devtools-mcp new_page targetId patch applied"
else
  fail "chrome-devtools-mcp patch missing — run: bash scripts/dev/install-cdmcp-mux-autoconnect.sh"
fi

MUX_STATE_DIR="${CDMCP_MUX_STATE_DIR:-$HOME/.local/state/cdmcp-mux}"
MUX_SOCKET="${CDMCP_MUX_SOCKET:-${TMPDIR:-/tmp}/mux-$(id -u)/cdmcp-mux.sock}"
if [[ -f "${SCRIPT_DIR}/lib/mux_responsive_probe.py" ]]; then
  if "${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/mux_responsive_probe.py" \
    --expected-ms 180000 \
    --state-dir "${MUX_STATE_DIR}" \
    --socket "${MUX_SOCKET}" 2>/dev/null; then
    ok "mux runtime upstream timeout effective (180000ms)"
  else
    fail "mux runtime timeout not effective — run: ./myrm restart --chrome"
  fi
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

hygiene="${SCRIPT_DIR}/lib/browser_tab_hygiene.py"
if [[ -f "${hygiene}" ]] && chrome_e2e_cdp_healthy; then
  if hygiene_out="$("${PREFLIGHT_PY}" "${hygiene}" --report --cdp-port "${MYRM_CHROME_E2E_PORT}" 2>&1)"; then
    echo "${hygiene_out}"
    ok "tab hygiene report"
  else
    warn "tab hygiene report failed — ${hygiene_out}"
  fi
fi

endpoint_errors="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from runtime_identity import attach_endpoint_errors
print(','.join(attach_endpoint_errors('http://127.0.0.1:3000', 'http://127.0.0.1:8080')))
" 2>/dev/null || true)"
if [[ "${endpoint_errors}" == *"ui=half_dead"* ]]; then
  fail "STACK_UI_HALF_DEAD :3000 listening but HTTP unreachable — run: ./myrm restart --chrome (do not stop other pytest)"
elif [[ "${endpoint_errors}" == *"ui=unreachable"* ]]; then
  fail "shared UI unreachable — run: ./myrm ready --chrome"
elif [[ "${endpoint_errors}" == *"api=unreachable"* ]]; then
  fail "shared API unreachable — run: ./myrm ready --chrome"
fi

if [[ "${failures}" -eq 0 ]]; then
  echo "CHROME_E2E_DOCTOR_READY"
  exit 0
fi
echo "CHROME_E2E_DOCTOR_NOT_READY failures=${failures}"
exit 1
