#!/usr/bin/env bash
# Preflight steps 4-8: the attach branch (mux heal only, private backend, fast path), the mux daemon
# reconcile and the vanilla chrome-devtools-mcp check (with the orchestrator ensure they use).
# Sourced by chrome-e2e-preflight.sh at the point where this step starts. It runs in the entry's shell, so
# its globals, `fail` and `exit` are the entry's.
# shellcheck shell=bash

_ensure_browser_orchestrator_after_data_plane() {
  [[ "${MYRM_BROWSER_ORCHESTRATOR:-}" == "1" ]] || return 0
  local orchestrator_ensure="${MONOREPO_ROOT}/scripts/dev/ensure-browser-orchestrator.sh"
  [[ -f "${orchestrator_ensure}" ]] || return 0
  local ensure_rc=0
  if bash "${orchestrator_ensure}"; then
    return 0
  else
    ensure_rc=$?
  fi
  if [[ "${ensure_rc}" -ne 75 ]]; then
    fail "browser-orchestrator daemon required after Chrome/CDP/mux readiness"
  fi
  echo "CHROME_E2E_INFRA_RACE_HEAL: CDP collapsed after preflight — recover Chrome→mux→orchestrator" >&2
  bash "${ENSURE_CHROME}" \
    || fail "Chrome/CDP recovery failed after orchestrator CDP_UNAVAILABLE"
  export MYRM_CHROME_E2E_CDP_RECOVERED=1
  _recover_mux_after_cdp_restart
  bash "${orchestrator_ensure}" \
    || fail "browser-orchestrator failed after Chrome/CDP race recovery"
}

if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
  # mux-only must exit before attach crash/drift heal (parallel signoff stack heal).
  if [[ "${MYRM_CHROME_E2E_MUX_HEAL_ONLY:-}" == "1" ]]; then
    if [[ "${MYRM_CHROME_E2E_CDP_RECOVERED:-}" == "1" ]]; then
      _recover_mux_after_cdp_restart
    else
      _heal_mux_request_timeout_drift
    fi
    _ensure_browser_orchestrator_after_data_plane
    ok "mux heal-only complete (attach mode, timeout=${MUX_REQUEST_TIMEOUT_MS}ms)"
    exit 0
  fi
  if [[ "${MYRM_MUX_FORCE_ATTACH_RESTART:-}" == "1" ]]; then
    if _mux_parallel_load_blocks_global_restart; then
      echo "CHROME_E2E_WARN: force attach restart blocked — parallel contexts or wave leases active" >&2
      exit 1
    fi
    _restart_mux_safely "attach new_page timeout (forced open_mcp_page heal)"
    ok "mux daemon force-restarted (attach new_page heal)"
    exit 0
  fi
  attach_parallel_leases="$(_wave_active_lease_count "${MONOREPO_ROOT}" 2>/dev/null || echo 0)"
  if [[ "${attach_parallel_leases}" =~ ^[0-9]+$ && "${attach_parallel_leases}" -gt 0 ]]; then
    echo "CHROME_E2E_ATTACH: parallel leases=${attach_parallel_leases} — keep healthy pinned backend; defer source-drift reload" >&2
  fi
  if [[ -f "${SCRIPT_DIR}/dev-stack.sh" ]]; then
    # Crash recovery is independent of source promotion and remains available
    # under parallel load. Both helpers are idempotent when the shared backend is healthy;
    # drift handling records metadata only and never restarts the pinned backend.
    _smp_attach_backend_crash_heal "${MONOREPO_ROOT}" "${SCRIPT_DIR}/dev-stack.sh"
    _smp_attach_backend_drift_heal "${MONOREPO_ROOT}" "${SERVER_DIR}" "${SCRIPT_DIR}/dev-stack.sh"
  fi
  _preflight_progress "mux_begin"
  _ensure_mux_cold_start_if_absent
  _heal_mux_request_timeout_drift
  _preflight_progress "mux_ready"
  if [[ "${MYRM_PRIVATE_BACKEND:-}" == "1" ]]; then
    _private_backend_attach_path
    _ensure_browser_orchestrator_after_data_plane
    exit 0
  fi
  _attach_fast_path
  _preflight_progress "attach_health"
  _ensure_browser_orchestrator_after_data_plane
  _preflight_progress "orchestrator"
  exit 0
fi

_ensure_mux_daemon

VANILLA_MCP_COUNT=0
if pgrep -f 'npm exec chrome-devtools-mcp' >/dev/null 2>&1; then
  # Exclude compliant isolated Agent MCP instances connecting to ChromeAgent :9410
  VANILLA_MCP_COUNT="$(pgrep -lf 'npm exec chrome-devtools-mcp' | { grep -v '9410' || true; } | wc -l | tr -d ' ')"
fi
if [[ "${MUX_USING}" -eq 1 ]]; then
  if [[ "${VANILLA_MCP_COUNT}" -gt 0 ]]; then
    if [[ "${MYRM_BROWSER_ORCHESTRATOR:-}" == "1" ]]; then
      echo "CHROME_E2E_WARN: legacy vanilla chrome-devtools-mcp (${VANILLA_MCP_COUNT}) ignored — formal E2E uses browser orchestrator RPC-only" >&2
    else
      fail "Legacy vanilla chrome-devtools-mcp still running (${VANILLA_MCP_COUNT}) — Cmd+Q Cursor; Agent MCP must use ChromeAgent :9410 (./myrm-dev doctor --mcp-isolation --strict-live)"
    fi
  fi
  if [[ ! -f "${MUX_PID_FILE}" ]]; then
    fail "cdmcp-mux daemon not running — run: ./myrm-dev ready --chrome"
  fi
  mux_pid="$(tr -d '[:space:]' < "${MUX_PID_FILE}")"
  if ! kill -0 "${mux_pid}" 2>/dev/null; then
    fail "cdmcp-mux daemon pid ${mux_pid} not alive — Cmd+Q Cursor and reopen"
  fi
  _ensure_mux_upstream
  mux_count="$(_mux_daemon_count)"
  if [[ "${mux_count}" != "1" ]]; then
    if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
      fail "mux daemon count=${mux_count} during attach — first Agent: ./myrm-dev ready --chrome (attach must not kill mux)"
    fi
    _restart_mux_safely "expected one owned daemon, found ${mux_count}"
    sleep 1
    _ensure_mux_upstream
    mux_count="$(_mux_daemon_count)"
    [[ "${mux_count}" == "1" ]] || fail "mux daemon count=${mux_count} after reconcile — Cmd+Q Cursor, then: ./myrm-dev ready --chrome"
  fi
  ok "cdmcp-mux daemon pid=${mux_pid} (parallel Agent tabs OK)"
else
  if [[ "${VANILLA_MCP_COUNT}" -gt 1 ]]; then
    fail "Too many vanilla chrome-devtools-mcp processes (${VANILLA_MCP_COUNT}) — Cmd+Q Cursor windows using Agent browser MCP"
  fi
  if [[ "${VANILLA_MCP_COUNT}" -eq 1 ]]; then
    echo "CHROME_E2E_WARN: vanilla chrome-devtools-mcp detected — Agent MCP must use ChromeAgent :9410 (./myrm-dev doctor --mcp-isolation --strict-live); E2E uses ./myrm-dev ready --chrome" >&2
  fi
fi
