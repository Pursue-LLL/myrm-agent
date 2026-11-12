#!/usr/bin/env bash
# Mux status probes: the current CDP ws url, its stamps, upstream readiness and the context count.
# Sourced by chrome-e2e-preflight.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

_current_cdp_ws_url() {
  MYRM_CHROME_E2E_PORT="${MYRM_CHROME_E2E_PORT}" "${PREFLIGHT_PY}" - <<'PY'
import json
import os
import urllib.request

port = os.environ.get("MYRM_CHROME_E2E_PORT", "9333")
with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as resp:
    data = json.load(resp)
ws = data.get("webSocketDebuggerUrl")
if not isinstance(ws, str) or not ws.startswith("ws://"):
    raise SystemExit("missing webSocketDebuggerUrl")
print(ws)
PY
}

_mux_ws_stamp_matches() {
  [[ -f "${MUX_WS_STAMP}" ]] || return 1
  local current stored
  current="$(_current_cdp_ws_url 2>/dev/null)" || return 1
  stored="$(tr -d '[:space:]' < "${MUX_WS_STAMP}")"
  [[ -n "${stored}" && "${current}" == "${stored}" ]]
}

_stamp_mux_ws_url() {
  local current
  current="$(_current_cdp_ws_url)" || return 1
  mkdir -p "${MUX_STATE_DIR}"
  printf '%s\n' "${current}" >"${MUX_WS_STAMP}"
}

_stamp_mux_daemon_ws_url() {
  local current
  current="$(_current_cdp_ws_url 2>/dev/null)" || return 1
  mkdir -p "${MUX_STATE_DIR}"
  printf '%s\n' "${current}" >"${MUX_DAEMON_WS_STAMP}"
}

_mux_daemon_ws_matches() {
  [[ -f "${MUX_DAEMON_WS_STAMP}" ]] || return 1
  local current stored
  current="$(_current_cdp_ws_url 2>/dev/null)" || return 1
  stored="$(tr -d '[:space:]' < "${MUX_DAEMON_WS_STAMP}")"
  [[ -n "${stored}" && "${current}" == "${stored}" ]]
}

_mux_upstream_ready() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  [[ -f "${MUX_BIN}" ]] || return 1
  local status_json ready
  status_json="$(node "${MUX_BIN}" status 2>/dev/null)" || return 1
  ready="$("${PREFLIGHT_PY}" -c "
import json, sys
try:
    d = json.loads(sys.argv[1])
    print('1' if d.get('upstreamReady') else '0')
except Exception:
    print('0')
" "${status_json}" 2>/dev/null)" || ready=0
  [[ "${ready}" == "1" ]]
}

_mux_context_count() {
  local status_json
  status_json="$(node "${MUX_BIN}" status 2>/dev/null)" || return 1
  "${PREFLIGHT_PY}" -c "
import json, sys
data = json.loads(sys.argv[1])
contexts = data.get('contexts')
print(len(contexts) if isinstance(contexts, list) else 0)
" "${status_json}"
}
