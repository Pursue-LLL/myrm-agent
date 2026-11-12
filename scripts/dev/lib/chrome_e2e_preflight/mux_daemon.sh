#!/usr/bin/env bash
# Mux daemon process control: which pids own the daemon, and stopping, killing and starting it.
# Sourced by chrome-e2e-preflight.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash
# shellcheck disable=SC2034  # `i` only counts the retries

_mux_owned_pids() {
  if [[ -f "${MUX_PID_FILE}" ]]; then
    local pid
    pid="$(tr -d '[:space:]' <"${MUX_PID_FILE}")"
    if [[ -n "${pid}" ]] && ps -p "${pid}" -o command= 2>/dev/null | grep -q 'cdmcp-mux-autoconnect'; then
      # daemon.pid is the ownership SSOT (a recycled pid is no daemon: its command must say so);
      # stale extra FDs on the same socket must not count as additional owned daemons.
      echo "${pid}"
      return 0
    fi
  fi
  if command -v lsof >/dev/null 2>&1 && [[ -S "${MUX_SOCKET}" ]]; then
    lsof -t -- "${MUX_SOCKET}" 2>/dev/null || true
  fi
}

_mux_daemon_count() {
  _mux_owned_pids | sort -u | sed '/^$/d' | wc -l | tr -d '[:space:]'
}

_kill_owned_mux_daemon() {
  local pids pid
  pids="$(_mux_owned_pids | sort -u | tr '\n' ' ')"
  if [[ -n "${pids// }" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    for _ in $(seq 1 20); do
      [[ "$(_mux_daemon_count)" == "0" ]] && break
      sleep 0.1
    done
    while IFS= read -r pid; do
      [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && kill -9 "${pid}" 2>/dev/null || true
    done < <(_mux_owned_pids | sort -u)
  fi
  [[ "$(_mux_daemon_count)" == "0" ]] && rm -f "${MUX_PID_FILE}"
}

_stop_mux_daemon() {
  _kill_owned_mux_daemon
}

_start_mux_daemon() {
  mkdir -p "${MUX_STATE_DIR}"
  if ! mkdir "${MUX_START_LOCK_DIR}" 2>/dev/null; then
    if [[ "$(_mux_daemon_count)" != "0" ]]; then
      return 0
    fi
    rmdir "${MUX_START_LOCK_DIR}" 2>/dev/null || true
    mkdir "${MUX_START_LOCK_DIR}" 2>/dev/null || return 0
  fi
  # The preflight shell exits immediately after readiness. Detached stdio is
  # required so the shared mux survives that shell and remains available to
  # every later Chrome DevTools MCP client.
  nohup env \
    CHROME_DATA_DIR="${MYRM_CHROME_E2E_DATA_DIR}" \
    MYRM_CHROME_E2E_DATA_DIR="${MYRM_CHROME_E2E_DATA_DIR}" \
    MYRM_CHROME_E2E_PORT="${MYRM_CHROME_E2E_PORT}" \
    CDMCP_MUX_STATE_DIR="${MUX_STATE_DIR}" \
    CDMCP_MUX_SOCKET="${MUX_SOCKET}" \
    CDMCP_MUX_REQUEST_TIMEOUT_MS="${MUX_REQUEST_TIMEOUT_MS}" \
    MCP_MUX_UPSTREAM_STDERR="${MCP_MUX_UPSTREAM_STDERR:-1}" \
    node "${MUX_BIN}" daemon \
    >>"${MUX_LOG_FILE}" 2>&1 < /dev/null &
  local i
  for i in $(seq 1 15); do
    if [[ -f "${MUX_PID_FILE}" ]] && kill -0 "$(tr -d '[:space:]' < "${MUX_PID_FILE}")" 2>/dev/null; then
      mkdir -p "${MUX_STATE_DIR}"
      _stamp_mux_request_timeout
      _stamp_mux_daemon_request_timeout
      _stamp_mux_daemon_ws_url || true
      rmdir "${MUX_START_LOCK_DIR}" 2>/dev/null || true
      return 0
    fi
    sleep 1
  done
  rmdir "${MUX_START_LOCK_DIR}" 2>/dev/null || true
}
