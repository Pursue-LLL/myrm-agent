#!/usr/bin/env bash
# Dev stack pid/log path SSOT. State under MYRM_DEV_STATE_DIR
# (default: real user home, mirroring wave_orchestrator/paths.py `_real_user_home()`
# which bypasses sandboxed HOME such as ~/.cursor-3 injected by the Cursor runtime).
set -euo pipefail

# Resolve the real login user home, bypassing sandboxed HOME (e.g. Cursor's
# ~/.cursor-3). Used for the dev state dir and for spawning stack processes so
# that harness data (Path.home()/.myrm) stays on the user's real data dir.
real_user_home() {
  local real_home
  real_home="$(python3 -c '
import os
import pwd
try:
    print(pwd.getpwuid(os.getuid()).pw_dir)
except (KeyError, OSError):
    print(os.path.expanduser("~"))
' 2>/dev/null || true)"
  real_home="${real_home:-${HOME}}"
  printf '%s' "${real_home}"
}

# Runtime namespace that identifies the real user's own stack (`myrm start|dev|stop`). The OSS
# CLI exports it; every maintainer entry (`./myrm-dev`, tests, isolated runtimes) uses another
# namespace, so each side classifies the other's processes as foreign and never signals them.
USER_RUNTIME_NAMESPACE="user"

dev_runtime_namespace() {
  printf '%s' "${MYRM_RUNTIME_NAMESPACE:-shared}"
}

dev_is_user_runtime() {
  [[ "$(dev_runtime_namespace)" == "${USER_RUNTIME_NAMESPACE}" ]]
}

# State root of the real user's stack: disjoint from the maintainers' `myrm-dev` state dir so
# pid files, locks and the supervisor of the two stacks can never overwrite each other.
user_runtime_state_dir() {
  printf '%s/.local/state/myrm' "$(real_user_home)"
}

# Data root of every non-user runtime that does not bring its own (the shared dev stack). Never
# `~/.myrm`: that is the real user's database (desktop sidecar, `myrm start`); two servers on one
# SQLite file corrupt it, and E2E provider seeding rewrites the backend's provider config.
dev_default_data_dir() {
  printf '%s/.local/share/myrm-dev/data' "$(real_user_home)"
}

_canonical_dir() {
  local dir="${1%/}"
  if [[ -d "${dir}" ]]; then
    (cd -P "${dir}" && pwd -P)
  else
    printf '%s' "${dir}"
  fi
}

# Export HOME/MYRM_DATA_DIR for stack child processes (backend/frontend).
# Prevents sandboxed HOME from leaking harness data into e.g. ~/.cursor-3/.myrm.
export_spawn_home() {
  HOME="$(real_user_home)"
  export HOME
  # The user's own stack keeps the backend's default data dir (~/.myrm) — that is its whole point.
  dev_is_user_runtime && return 0
  # Isolated runtimes pre-set MYRM_DATA_DIR to their own dataDir; do not clobber.
  if [[ -z "${MYRM_DATA_DIR:-}" ]]; then
    MYRM_DATA_DIR="$(dev_default_data_dir)"
    export MYRM_DATA_DIR
    mkdir -p "${MYRM_DATA_DIR}"
    return 0
  fi
  if [[ "$(_canonical_dir "${MYRM_DATA_DIR/#\~/${HOME}}")" == "$(_canonical_dir "${HOME}/.myrm")" ]]; then
    echo "DEV_DATA_DIR_IS_USER_DATA: MYRM_DATA_DIR=${MYRM_DATA_DIR} is the real user's data dir; refusing to" \
      "start dev processes on it. Unset MYRM_DATA_DIR (default: $(dev_default_data_dir)) or use an" \
      "isolated runtime: ./myrm-dev isolate" >&2
    return 1
  fi
}

dev_state_dir() {
  # WAVE override wins over DEV (mirror resolve_dev_state_dir()).
  if [[ -n "${MYRM_WAVE_STATE_DIR:-}" ]]; then
    echo "${MYRM_WAVE_STATE_DIR}"
    return 0
  fi
  if [[ -n "${MYRM_DEV_STATE_DIR:-}" ]]; then
    echo "${MYRM_DEV_STATE_DIR}"
    return 0
  fi
  _real_home_default_state_dir
}

_real_home_default_state_dir() {
  printf '%s/.local/state/myrm-dev' "$(real_user_home)"
}

dev_backend_pid_file() {
  echo "${MYRM_BACKEND_PID_FILE:-$(dev_state_dir)/backend.pid}"
}

dev_backend_log_file() {
  echo "${MYRM_BACKEND_LOG_FILE:-$(dev_state_dir)/backend.log}"
}

dev_frontend_pid_file() {
  echo "${MYRM_FRONTEND_PID_FILE:-$(dev_state_dir)/frontend.pid}"
}

dev_frontend_log_file() {
  echo "${MYRM_FRONTEND_LOG_FILE:-$(dev_state_dir)/frontend.log}"
}

_read_pid_from_file() {
  local path="$1"
  [[ -f "${path}" ]] || return 1
  local raw
  raw="$(tr -d '[:space:]' <"${path}")"
  [[ "${raw}" =~ ^[0-9]+$ ]] || return 1
  echo "${raw}"
}

dev_pid_alive() {
  local pid="${1:-}" probe=""
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  probe="$(kill -0 "${pid}" 2>&1)" && return 0
  case "${probe}" in
    *"Operation not permitted"*|*"operation not permitted"*) return 0 ;;
  esac
  return 1
}

read_backend_dev_pid() {
  _read_pid_from_file "$(dev_backend_pid_file)" 2>/dev/null || return 1
}

read_frontend_dev_pid() {
  _read_pid_from_file "$(dev_frontend_pid_file)" 2>/dev/null || return 1
}

_kill_pid_gracefully() {
  local pid="$1"
  [[ -n "${pid}" ]] || return 0
  dev_pid_alive "${pid}" || return 0
  kill -TERM "-${pid}" 2>/dev/null || kill -TERM "${pid}" 2>/dev/null || true
  pkill -TERM -P "${pid}" 2>/dev/null || true
  local i
  for i in $(seq 1 15); do
    dev_pid_alive "${pid}" || return 0
    sleep 1
  done
  pkill -9 -P "${pid}" 2>/dev/null || true
  kill -9 "-${pid}" 2>/dev/null || kill -9 "${pid}" 2>/dev/null || true
}

dev_port_in_use() {
  local port="$1"
  python3 -c '
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(0)
raise SystemExit(1)
' "${port}"
}

# Pids LISTENing on a TCP port, space separated (lsof is the port-truth SSOT).
dev_listener_pids() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ' || true
}

# Print the pids among "$@" that this runtime's dev stack started, one per line; every other
# pid is reported on stderr and dropped. Ownership is the dev stamp in the process environment
# (e2e_core/dev_ownership.py), never the command line: the desktop sidecar runs the same
# run.py on the same default port. Every signal the dev tooling sends goes through here.
dev_filter_owned_pids() {
  [[ "$#" -gt 0 ]] || return 0
  python3 "$(dirname "${BASH_SOURCE[0]}")/e2e_core/dev_ownership.py" filter \
    --runtime-id "$(dev_runtime_namespace)" "$@"
}

# Stop the dev-owned listeners on a port; anything else holding it is left running.
dev_kill_port_listeners() {
  local port="$1" listeners="" owned_pids=""
  listeners="$(dev_listener_pids "${port}")"
  [[ -n "${listeners// }" ]] || return 0
  # shellcheck disable=SC2086
  owned_pids="$(dev_filter_owned_pids ${listeners} | tr '\n' ' ')"
  [[ -n "${owned_pids// }" ]] || return 0
  # shellcheck disable=SC2086
  kill -TERM ${owned_pids} 2>/dev/null || true
  sleep 2
  # shellcheck disable=SC2046,SC2086
  owned_pids="$(dev_filter_owned_pids $(dev_listener_pids "${port}") 2>/dev/null | tr '\n' ' ')"
  [[ -z "${owned_pids// }" ]] || kill -9 ${owned_pids} 2>/dev/null || true
}

dev_wait_ports_released() {
  local max_wait="${1:-30}"
  shift
  local waited=0 port
  while [[ "${waited}" -lt "${max_wait}" ]]; do
    local busy=0
    for port in "$@"; do
      [[ -n "${port}" ]] || continue
      if dev_port_in_use "${port}"; then
        busy=1
        break
      fi
    done
    [[ "${busy}" -eq 0 ]] && return 0
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

resolve_myrm_next_dist_dir() {
  local state_dir
  state_dir="$(dev_state_dir)"
  local default_dir
  default_dir="$(_real_home_default_state_dir)"
  local explicit="${MYRM_NEXT_DIST_DIR:-}"
  if [[ -n "${explicit}" && "${explicit}" == "${state_dir}/next" ]]; then
    explicit=""
  fi
  if [[ -n "${explicit}" && "${explicit}" != /* ]]; then
    echo "${explicit}"
    return 0
  fi
  if [[ "${state_dir}" != "${default_dir}" ]]; then
    local runtime_ns="${MYRM_RUNTIME_NAMESPACE:-$(basename "$(dirname "${state_dir}")")}"
    runtime_ns="${runtime_ns//[^[:alnum:]_.-]/-}"
    echo ".next-isolated-${runtime_ns}"
    return 0
  fi
  # The dev server writes to .next-dev: `next build` clears the dist dir, and sharing one
  # directory means a production build deletes the running dev server's chunks (the page
  # then serves HTML whose scripts 404 and never hydrates).
  echo "${explicit:-.next-dev}"
}

export_myrm_next_dist_dir() {
  MYRM_NEXT_DIST_DIR="$(resolve_myrm_next_dist_dir)"
  export MYRM_NEXT_DIST_DIR
}

resolve_frontend_lock_path() {
  local frontend_dir="$1"
  export_myrm_next_dist_dir
  echo "${frontend_dir}/${MYRM_NEXT_DIST_DIR}/dev-server.lock"
}

cleanup_legacy_dev_artifacts() {
  local server_dir="${1:-}"
  local frontend_dir="${2:-}"
  local agent_root=""
  if [[ -n "${server_dir}" ]]; then
    rm -f "${server_dir}/.myrm-dev-backend.pid" "${server_dir}/.myrm-dev-backend.log"
    agent_root="$(dirname "${server_dir}")"
    rm -f "${agent_root}/.myrm-dev-backend.pid" "${agent_root}/.myrm-dev-backend.log"
  fi
  if [[ -n "${frontend_dir}" ]]; then
    rm -f "${frontend_dir}/.myrm-dev-frontend.pid" "${frontend_dir}/.myrm-dev-frontend.log" \
      "${frontend_dir}/.myrm-dev-frontend-fg.log"
    [[ -n "${agent_root}" ]] || agent_root="$(dirname "${frontend_dir}")"
  fi
  if [[ -n "${agent_root}" && -d "${agent_root}/scripts/dev" ]]; then
    rm -rf "${agent_root}/scripts/dev/myrm-agent-server" "${agent_root}/scripts/dev/myrm-agent-frontend"
  fi
}

prune_stale_isolated_next_dirs() {
  local frontend_dir="${1:-}"
  [[ -n "${frontend_dir}" && -d "${frontend_dir}" ]] || return 0
  local active_dist
  active_dist="$(resolve_myrm_next_dist_dir)"
  local entry name
  shopt -s nullglob
  for entry in "${frontend_dir}"/.next-isolated-*; do
    [[ -d "${entry}" ]] || continue
    name="$(basename "${entry}")"
    [[ "${name}" == "${active_dist}" ]] && continue
    rm -rf "${entry}" 2>/dev/null || true
  done
  shopt -u nullglob
}
