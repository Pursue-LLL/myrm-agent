#!/usr/bin/env bash
# Listener and pid ownership of dev-stack.sh: pid-file reads that prove this stack started the process,
# owned-listener lookups on the backend/frontend ports, and the binding and pid re-sync helpers.
# Sourced by dev-stack.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

# The pid in a pid file, only when this stack started that process (a stale file whose pid
# was recycled by an unrelated process yields nothing).
_owned_pid_from_file() {
  local pid
  pid="$(tr -d '[:space:]' <"$1" 2>/dev/null || true)"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 0
  dev_filter_owned_pids "${pid}"
}

# Pids LISTENing on a stack port that this stack started; foreign listeners are reported on
# stderr and never returned, so nothing built on this list can signal them.
_owned_frontend_listener_pids() {
  # shellcheck disable=SC2046
  dev_filter_owned_pids $(dev_listener_pids "${FRONTEND_PORT}") | tr '\n' ' '
}

_owned_backend_listener_pids() {
  # shellcheck disable=SC2046
  dev_filter_owned_pids $(dev_listener_pids "${BACKEND_PORT}") | tr '\n' ' '
}

# Fail fast when the backend port is held by a process this stack did not start (the desktop
# sidecar, a `myrm start` runtime). Waiting on it can never turn healthy for the dev stack.
_refuse_foreign_backend_listener() {
  local listeners owned_pids foreign
  listeners="$(dev_listener_pids "${BACKEND_PORT}")"
  [[ -n "${listeners// }" ]] || return 0
  # shellcheck disable=SC2086
  owned_pids=" $(dev_filter_owned_pids ${listeners} 2>/dev/null | tr '\n' ' ')"
  for foreign in ${listeners}; do
    if [[ "${owned_pids}" != *" ${foreign} "* ]]; then
      echo "STACK_FOREIGN_LISTENER: :${BACKEND_PORT} is held by pid ${foreign}, which this dev stack (runtime=${MYRM_RUNTIME_NAMESPACE}) did not start — it will never be adopted, stamped or signalled. Stop it yourself, or run on an isolated runtime: ./myrm-dev isolate" >&2
      return 1
    fi
  done
}

_backend_supervisor_alive() {
  [[ -f "${BACKEND_PID}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' <"${BACKEND_PID}")"
  [[ -n "${pid}" ]] && dev_pid_alive "${pid}"
}

_frontend_port_listening() {
  python3 -c '
import socket, sys
try:
    with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=0.25):
        pass
except (OSError, ValueError):
    raise SystemExit(1)
' "${FRONTEND_PORT}" >/dev/null 2>&1
}

_frontend_bound_api_port() {
  # The frontend rewrites /api/v1 to whichever port it was spawned with; recover that
  # port from the live process so a stale binding can be detected before adoption.
  local pid
  pid="$(lsof -nP -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -t 2>/dev/null | head -1)"
  if [[ -z "${pid}" ]]; then
    if [[ -f "${FRONTEND_PID}" ]]; then
      pid="$(cat "${FRONTEND_PID}" 2>/dev/null)"
    fi
  fi
  [[ -n "${pid}" ]] || return 1
  ps eww -p "${pid}" 2>/dev/null | tr ' ' '\n' | sed -n 's/^API_PORT=//p' | head -1
}

_frontend_binding_matches() {
  # Reusing a frontend whose upstream moved means every /api/v1 call can hit a dead or
  # foreign port while the shell still answers 200. Only adopt it when the bound port
  # is the backend this ensure targets.
  local bound
  bound="$(_frontend_bound_api_port)" || return 0
  [[ -z "${bound}" ]] && return 0
  if [[ "${bound}" == "${FRONTEND_API_PORT}" ]]; then
    return 0
  fi
  echo "STACK_REBIND: frontend :${FRONTEND_PORT} bound to api=:${bound} but this ensure targets :${FRONTEND_API_PORT} — restarting frontend" >&2
  return 1
}

_sync_frontend_pid_from_lock() {
  if [[ ! -f "${FRONTEND_LOCK}" ]]; then
    return 0
  fi
  local pid
  pid="$(python3 -c "
import json
from pathlib import Path
p = Path('${FRONTEND_LOCK}')
data = json.loads(p.read_text())
print(data.get('pid', ''))
" 2>/dev/null)" || return 0
  if [[ -n "${pid}" ]] && [[ "${pid}" =~ ^[0-9]+$ ]]; then
    echo "${pid}" >"${FRONTEND_PID}"
  fi
}
