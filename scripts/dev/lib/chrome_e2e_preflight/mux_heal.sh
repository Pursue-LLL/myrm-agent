#!/usr/bin/env bash
# Mux self-heal: upstream and request-timeout drift, the parallel-attach shortcut, cold start and the
# recovery after a CDP restart.
# Sourced by chrome-e2e-preflight.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash
# shellcheck disable=SC2034  # `i` only counts the retries

_ensure_mux_upstream() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  if _mux_ws_stamp_matches && _mux_daemon_ws_matches && _mux_upstream_ready; then
    return 0
  fi
  # solo gate/signoff — restamp CDP ws drift before attach fail-closed or blocked restart.
  if ! _mux_ws_stamp_matches && _mux_upstream_ready && _mux_solo_gate_cluster_clear; then
    if [[ "${E2E_SIGNOFF:-}" == "1" || "${MYRM_E2E_P0A_GATE:-}" == "1" ]]; then
      _mux_ws_restamp_solo_heal "signoff-or-p0a-gate upstreamReady" && return 0
    fi
    if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
      _mux_ws_restamp_solo_heal "attach solo cluster ws drift" && return 0
    fi
  fi
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
    fail "mux not ready for parallel attach (upstreamReady or CDP ws drift) — first Agent must run: ./myrm-dev ready --chrome"
  fi
  if _mux_ws_stamp_matches; then
    echo "CHROME_E2E_WAIT: mux upstreamReady=false — waiting for daemon self-heal" >&2
    if _wait_mux_upstream_self_heal; then
      ok "cdmcp-mux upstream self-healed without daemon restart"
      return 0
    fi
    _restart_mux_safely "upstream self-heal timeout"
  else
    echo "CHROME_E2E_WARN: Chrome CDP WebSocket drifted — daemon options require a new endpoint" >&2
    # signoff or solo gate — restamp ws without restart when cluster is solo-clear.
    if _mux_upstream_ready \
      && { [[ "${E2E_SIGNOFF:-}" == "1" ]] || [[ "${MYRM_E2E_P0A_GATE:-}" == "1" ]]; } \
      && _mux_solo_gate_cluster_clear; then
      _mux_ws_restamp_solo_heal "solo cluster upstreamReady" && return 0
    fi
    if [[ "${E2E_SIGNOFF:-}" == "1" ]] && _mux_upstream_ready; then
      echo "CHROME_E2E_SIGNOFF_MUX_WS_RESTAMP: upstreamReady with parallel contexts — restamp ws without restart" >&2
      _stamp_mux_ws_url || true
      _stamp_mux_daemon_ws_url || true
      ok "cdmcp-mux signoff ws restamp (upstreamReady=1)"
      return 0
    fi
    _restart_mux_safely "CDP WebSocket drift"
  fi
  local i
  for i in $(seq 1 15); do
    sleep 1
    if _mux_upstream_ready; then
      _stamp_mux_ws_url || true
      _stamp_mux_daemon_ws_url || true
      ok "cdmcp-mux upstream reconnected"
      return 0
    fi
  done
  fail "cdmcp-mux upstreamReady still false — Cmd+Q Cursor, then: ./myrm-dev ready --chrome"
}

_stamp_mux_request_timeout() {
  mkdir -p "${MUX_STATE_DIR}"
  printf '%s\n' "${MUX_REQUEST_TIMEOUT_MS}" >"${MUX_TIMEOUT_STAMP}"
}

_stamp_mux_daemon_request_timeout() {
  mkdir -p "${MUX_STATE_DIR}"
  printf '%s\n' "${MUX_REQUEST_TIMEOUT_MS}" >"${MUX_DAEMON_TIMEOUT_STAMP}"
}

_mux_parallel_active_leases() {
  _wave_active_lease_count "${MONOREPO_ROOT}" 2>/dev/null || echo 0
}

_mux_probe_timeout_sec() {
  local active_leases probe_timeout
  active_leases="$(_mux_parallel_active_leases)"
  probe_timeout=8
  if [[ "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    probe_timeout=$((8 + active_leases * 3))
    if [[ "${probe_timeout}" -gt 45 ]]; then
      probe_timeout=45
    fi
  fi
  echo "${probe_timeout}"
}

_mux_request_timeout_effective() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  local probe_timeout
  probe_timeout="$(_mux_probe_timeout_sec)"
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/mux/responsive_probe.py" \
    --expected-ms "${MUX_REQUEST_TIMEOUT_MS}" \
    --state-dir "${MUX_STATE_DIR}" \
    --socket "${MUX_SOCKET}" \
    --probe-timeout-sec "${probe_timeout}"
}

_mux_daemon_pid_alive() {
  [[ -f "${MUX_PID_FILE}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' < "${MUX_PID_FILE}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

_mux_parallel_attach_health_ok() {
  _mux_upstream_ready && _mux_ws_stamp_matches && _mux_daemon_pid_alive
}

_heal_mux_under_parallel_attach_load() {
  [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]] || return 1
  local active_leases attempt
  active_leases="$(_mux_parallel_active_leases)"
  [[ "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]] || return 1
  # ++: under parallel Wave leases, tools/list can queue behind peer tabs.
  # Trust upstream+ws+pid before expensive probes so attach clears mux_begin quickly.
  if _mux_parallel_attach_health_ok; then
    echo "CHROME_E2E_WARN: mux parallel attach fast-path — skip timeout probe (${active_leases} active leases)" >&2
    return 0
  fi
  for attempt in 1 2; do
    if _mux_request_timeout_effective; then
      return 0
    fi
    echo "CHROME_E2E_WARN: mux probe slow (${active_leases} active leases) attempt ${attempt}/2" >&2
    sleep $((attempt * 2))
    if _mux_parallel_attach_health_ok; then
      echo "CHROME_E2E_WARN: mux probe timeout under parallel load — skip restart (${active_leases} active leases)" >&2
      return 0
    fi
  done
  if _mux_parallel_attach_health_ok; then
    echo "CHROME_E2E_WARN: mux probe timeout under parallel load — skip restart (${active_leases} active leases)" >&2
    return 0
  fi
  return 1
}

_heal_mux_request_timeout_drift() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  # UBDP-6: reap zombie mux (alive pid without socket) before heal/restart decisions.
  if PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" "${PREFLIGHT_PY}" \
    "${SCRIPT_DIR}/lib/mux/health.py" reap >/dev/null 2>&1; then
    :
  fi
  local active_leases
  active_leases="$(_mux_parallel_active_leases)"
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" && "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    if _mux_parallel_attach_health_ok; then
      echo "CHROME_E2E_WARN: mux parallel attach fast-path — skip timeout probe (${active_leases} active leases)" >&2
      return 0
    fi
  fi
  if _mux_request_timeout_effective; then
    return 0
  fi
  if _heal_mux_under_parallel_attach_load; then
    return 0
  fi
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" && "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    if _mux_parallel_attach_health_ok; then
      echo "CHROME_E2E_WARN: mux heal restart suppressed during attach (${active_leases} active leases)" >&2
      return 0
    fi
  fi
  # Probe failed — heal/restart (fail-closed for stale 55s upstream).
  if ! _mux_daemon_pid_alive; then
    _ensure_mux_cold_start_if_absent
    return 0
  fi
  if _mux_timeout_restart_allowed || _mux_restart_allowed; then
    _restart_mux_safely "request timeout drift (${MUX_REQUEST_TIMEOUT_MS}ms)"
  elif _mux_attach_timeout_restart_allowed; then
    _restart_mux_safely "attach request timeout drift (${MUX_REQUEST_TIMEOUT_MS}ms)"
  elif _mux_upstream_ready && _mux_ws_stamp_matches; then
    fail "mux request timeout drift (${MUX_REQUEST_TIMEOUT_MS}ms) — daemon probe failed; attach restart not allowed"
  elif _mux_parallel_load_blocks_global_restart; then
    echo "CHROME_E2E_WARN: mux heal restart blocked — parallel contexts or wave leases active" >&2
    return 0
  else
    _restart_mux_safely "request timeout drift (${MUX_REQUEST_TIMEOUT_MS}ms)"
  fi
  if ! _mux_request_timeout_effective; then
    fail "mux timeout probe still failing after heal (${MUX_REQUEST_TIMEOUT_MS}ms)"
  fi
}

_mux_daemon_present() {
  if _mux_daemon_pid_alive; then
    return 0
  fi
  local mux_count
  mux_count="$(_mux_daemon_count 2>/dev/null || echo 0)"
  [[ "${mux_count}" =~ ^[0-9]+$ && "${mux_count}" -ge 1 ]]
}

_ensure_mux_cold_start_if_absent() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  [[ -f "${MUX_BIN}" ]] || fail "Missing mux bin ${MUX_BIN} — run: bash scripts/dev/install-cdmcp-mux-autoconnect.sh"
  if _mux_daemon_present; then
    return 0
  fi
  if ! myrm_chrome_e2e_cdp_healthy; then
    if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
      fail "cdmcp-mux daemon not running during attach — Myrm E2E Chrome CDP not reachable — first Agent must run: ./myrm-dev ready --chrome"
    fi
    fail "Myrm E2E Chrome CDP not reachable — run: ./myrm-dev ready --chrome"
  fi
  echo "CHROME_E2E_WARN: cold-starting cdmcp-mux daemon (idempotent; no peer restart)" >&2
  if ! PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.plane_health import ensure_mux_daemon_if_absent
raise SystemExit(0 if ensure_mux_daemon_if_absent() else 1)
"; then
    # A losing racer of a concurrent cold start exits with "already owned"; the shared
    # mux is up in that case, so re-check presence before failing the lane.
    if _mux_daemon_present; then
      ok "cdmcp-mux daemon cold-start raced with a peer but the daemon is present"
      return 0
    fi
    fail "cdmcp-mux daemon cold-start failed — run: ./myrm-dev restart --chrome"
  fi
  local attempt mux_count
  for attempt in $(seq 1 15); do
    if _mux_daemon_present; then
      ok "cdmcp-mux daemon cold-started"
      return 0
    fi
    sleep 1
  done
  mux_count="$(_mux_daemon_count 2>/dev/null || echo 0)"
  fail "cdmcp-mux daemon cold-start did not produce live daemon (count=${mux_count})"
}

_ensure_mux_daemon() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  [[ -f "${MUX_BIN}" ]] || fail "Missing mux bin ${MUX_BIN} — run: bash scripts/dev/install-cdmcp-mux-autoconnect.sh"
  if _mux_daemon_present; then
    if ! _mux_request_timeout_effective; then
      _heal_mux_request_timeout_drift
    fi
    return 0
  fi
  _ensure_mux_cold_start_if_absent
}

_recover_mux_after_cdp_restart() {
  [[ -f "${MUX_BIN}" ]] || fail "Missing mux bin ${MUX_BIN} during Chrome crash recovery"
  MUX_USING=1
  if _mux_daemon_pid_alive; then
    local attempt
    for attempt in 1 2 3; do
      if _mux_upstream_ready; then
        _stamp_mux_ws_url || true
        _stamp_mux_daemon_ws_url || true
        ok "cdmcp-mux reattached after Chrome crash without restart"
        return 0
      fi
      sleep 1
    done
    echo "CHROME_E2E_ATTACH_HEAL: mux upstream stayed down after Chrome recovery — restart exact owned namespace" >&2
    _stop_mux_daemon
  fi
  _start_mux_daemon
  local attempt
  for attempt in $(seq 1 15); do
    if _mux_daemon_pid_alive && _mux_upstream_ready; then
      _stamp_mux_ws_url || true
      _stamp_mux_daemon_ws_url || true
      ok "cdmcp-mux recovered after Chrome crash"
      return 0
    fi
    sleep 1
  done
  fail "cdmcp-mux did not recover after Chrome/CDP restart"
}
