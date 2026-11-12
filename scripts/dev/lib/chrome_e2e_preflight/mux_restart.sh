#!/usr/bin/env bash
# When the mux daemon may be restarted or re-stamped (parallel load, solo gate, timeout predicates) and
# the guarded restart that applies them.
# Sourced by chrome-e2e-preflight.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash
# shellcheck disable=SC2034  # `i` only counts the retries

_mux_attach_timeout_restart_allowed() {
  [[ "${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-}" == "1" ]] || return 1
  [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]] || return 1
  _mux_parallel_load_blocks_global_restart && return 1
  _mux_upstream_ready && _mux_ws_stamp_matches
}

_mux_parallel_load_blocks_global_restart() {
  # UBDP-6: health SSOT — unhealthy mux always allows restart; only HEALTHY+parallel blocks.
  if PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" "${PREFLIGHT_PY}" \
    "${SCRIPT_DIR}/lib/mux/health.py" restart-blocked 2>/dev/null; then
    return 0
  fi
  return 1
}

_mux_solo_gate_cluster_clear() {
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
from mux.load import solo_gate_cluster_clear
import sys
sys.exit(0 if solo_gate_cluster_clear() else 1)
" 2>/dev/null
}

_mux_ws_restamp_solo_heal() {
  local label="$1"
  echo "CHROME_E2E_SOLO_WS_RESTAMP: ${label}" >&2
  _stamp_mux_ws_url || return 1
  _stamp_mux_daemon_ws_url || true
  if _mux_ws_stamp_matches && _mux_daemon_ws_matches && _mux_upstream_ready; then
    ok "cdmcp-mux solo ws restamp (${label})"
    return 0
  fi
  return 1
}

_mux_restart_allowed() {
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
    if [[ "${MYRM_E2E_P0A_GATE:-}" == "1" ]] && _mux_solo_gate_cluster_clear; then
      :
    else
      return 1
    fi
  fi
  _mux_parallel_load_blocks_global_restart && return 1
  if [[ "${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-}" == "1" ]]; then
    return 0
  fi
  bash "${SCRIPT_DIR}/wave.sh" check-stack-write >/dev/null 2>&1
}

_mux_timeout_restart_allowed() {
  [[ "${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-}" == "1" ]] || return 1
  _mux_parallel_load_blocks_global_restart && return 1
  bash "${SCRIPT_DIR}/wave.sh" check-stack-write >/dev/null 2>&1
}

_wait_mux_upstream_self_heal() {
  local i
  for i in $(seq 1 "${MYRM_MUX_SELF_HEAL_WAIT_SEC:-15}"); do
    if _mux_upstream_ready; then
      return 0
    fi
    sleep 1
  done
  return 1
}

_restart_mux_safely() {
  local reason="$1"
  local allowed=0
  if _mux_restart_allowed; then
    allowed=1
  elif [[ "${reason}" == *"timeout"* ]] && _mux_timeout_restart_allowed; then
    allowed=1
  elif [[ "${reason}" == *"timeout"* ]] && _mux_attach_timeout_restart_allowed; then
    allowed=1
  fi
  if [[ "${allowed}" -eq 0 ]]; then
    local contexts="unknown"
    contexts="$(_mux_context_count 2>/dev/null || echo unknown)"
    fail "mux restart blocked (${reason}); contexts=${contexts}, attach=${MYRM_CHROME_E2E_ATTACH}, or Wave pins runtime"
  fi
  echo "CHROME_E2E_WARN: restarting owned mux namespace (${reason})" >&2
  _stop_mux_daemon
  _start_mux_daemon
}
