#!/usr/bin/env bash
# Private-backend helpers of dev-stack.sh: stop, identity validation, port/identity sync and orphan
# reclaim for a backend-only pool member.
# Sourced by dev-stack.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

_stop_private_backend() {
  local py="${SERVER_DIR}/.venv/bin/python"
  local identity_helper="${SCRIPT_DIR}/lib/e2e_core/process_identity.py"
  local runtime_id="${MYRM_RUNTIME_NAMESPACE:-shared}"
  if [[ ! -x "${py}" ]]; then
    py="python3"
  fi
  if [[ -f "${BACKEND_IDENTITY}" ]]; then
    if ! "${py}" "${identity_helper}" terminate \
      --identity-file "${BACKEND_IDENTITY}" \
      --pid-file "${BACKEND_PID}" \
      --expected-runtime-id "${runtime_id}"; then
      echo "STACK_FAIL: private backend process ownership mismatch" >&2
      return 1
    fi
  elif [[ -f "${BACKEND_PID}" ]] || dev_port_in_use "${BACKEND_PORT}"; then
    echo "STACK_FAIL: private backend ownership identity missing; refusing to kill pid/port" >&2
    return 1
  fi
  if ! dev_wait_ports_released 45 "${BACKEND_PORT}"; then
    echo "STACK_FAIL: private backend port :${BACKEND_PORT} still owned by an unknown listener" >&2
    return 1
  fi
  _clear_stack_epoch
}

_private_backend_identity_valid() {
  [[ -f "${BACKEND_IDENTITY}" ]] || return 1
  local dev_pid port_owner_pid py="${SERVER_DIR}/.venv/bin/python"
  dev_pid=""
  if [[ -f "${BACKEND_PID}" ]]; then
    dev_pid="$(tr -d '[:space:]' <"${BACKEND_PID}")"
  fi
  port_owner_pid="$(lsof -nP -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  if [[ -n "${port_owner_pid}" && "${port_owner_pid}" =~ ^[0-9]+$ ]]; then
    dev_pid="${port_owner_pid}"
  fi
  [[ "${dev_pid}" =~ ^[0-9]+$ ]] || return 1
  if [[ ! -x "${py}" ]]; then
    py="python3"
  fi
  "${py}" "${SCRIPT_DIR}/lib/e2e_core/process_identity.py" verify \
    --identity-file "${BACKEND_IDENTITY}" \
    --expected-pid "${dev_pid}" \
    --expected-runtime-id "${MYRM_RUNTIME_NAMESPACE:-shared}" >/dev/null
}

_private_backend_scope() {
  [[ "${MYRM_PRIVATE_BACKEND:-}" == "1" || "${MYRM_E2E_PRIVATE_BACKEND:-}" == "1" ]] \
    || [[ "${MYRM_DEV_STATE_DIR:-}" != "$(_real_home_default_state_dir)" ]]
}

_shared_backend_listens_on_port() {
  local port="$1" shared_pid="$2" owner_pid
  [[ -n "${shared_pid}" && "${shared_pid}" =~ ^[0-9]+$ ]] || return 1
  dev_pid_alive "${shared_pid}" || return 1
  for owner_pid in $(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null); do
    [[ "${owner_pid}" == "${shared_pid}" ]] && return 0
  done
  return 1
}

_sync_private_backend_identity_from_port() {
  if _private_backend_identity_valid; then
    return 0
  fi
  dev_port_in_use "${BACKEND_PORT}" || return 1
  local port_owner_pid py="${SERVER_DIR}/.venv/bin/python"
  port_owner_pid="$(lsof -nP -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  [[ -n "${port_owner_pid}" && "${port_owner_pid}" =~ ^[0-9]+$ ]] || return 1
  if [[ ! -x "${py}" ]]; then
    py="python3"
  fi
  if ! "${py}" "${SCRIPT_DIR}/lib/e2e_core/process_identity.py" record \
    --pid "${port_owner_pid}" \
    --identity-file "${BACKEND_IDENTITY}" \
    --runtime-id "${MYRM_RUNTIME_NAMESPACE:-shared}" \
    --role backend \
    --expected-command-token run.py >/dev/null 2>&1; then
    return 1
  fi
  echo "${port_owner_pid}" >"${BACKEND_PID}"
  _private_backend_identity_valid
}

_repair_orphan_private_backend() {
  if ! _private_backend_scope; then
    return 1
  fi
  if _private_backend_identity_valid; then
    return 0
  fi
  # Port ownership truth: refuse reclaim only when the shared backend (default
  # state dir) is the actual LISTEN owner on BACKEND_PORT — not merely alive on
  # its own port while a private orphan occupies a private one.
  local shared_pid_file shared_pid
  shared_pid_file="$(_real_home_default_state_dir)/backend.pid"
  shared_pid=""
  if [[ -f "${shared_pid_file}" ]]; then
    shared_pid="$(tr -d '[:space:]' <"${shared_pid_file}")"
  fi
  if _shared_backend_listens_on_port "${BACKEND_PORT}" "${shared_pid}"; then
    echo "STACK_FAIL: private backend port :${BACKEND_PORT} owned by shared backend pid=${shared_pid} — refuse orphan reclaim" >&2
    return 1
  fi
  echo "STACK_HEAL: reclaiming orphan private backend on :${BACKEND_PORT}" >&2
  if [[ -f "${BACKEND_IDENTITY}" ]]; then
    _stop_private_backend 2>/dev/null || true
  fi
  rm -f "${BACKEND_PID}" "${BACKEND_IDENTITY}"
  if dev_port_in_use "${BACKEND_PORT}"; then
    # Only this runtime's own orphan is reclaimed; any other listener keeps the port and the
    # wait below fails closed.
    dev_kill_port_listeners "${BACKEND_PORT}"
  fi
  if ! dev_wait_ports_released 45 "${BACKEND_PORT}"; then
    echo "STACK_FAIL: private backend port :${BACKEND_PORT} still busy after orphan reclaim" >&2
    return 1
  fi
  _clear_stack_epoch
  return 0
}
