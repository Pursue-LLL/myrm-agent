#!/usr/bin/env bash
# Dev stack pid/log path SSOT. State under MYRM_DEV_STATE_DIR (default ~/.local/state/myrm-dev).
set -euo pipefail

dev_state_dir() {
  echo "${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}"
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

read_backend_dev_pid() {
  _read_pid_from_file "$(dev_backend_pid_file)" 2>/dev/null || return 1
}

read_frontend_dev_pid() {
  _read_pid_from_file "$(dev_frontend_pid_file)" 2>/dev/null || return 1
}

_kill_pid_gracefully() {
  local pid="$1"
  [[ -n "${pid}" ]] || return 0
  kill -0 "${pid}" 2>/dev/null || return 0
  kill -TERM "-${pid}" 2>/dev/null || kill -TERM "${pid}" 2>/dev/null || true
  pkill -TERM -P "${pid}" 2>/dev/null || true
  local i
  for i in $(seq 1 15); do
    kill -0 "${pid}" 2>/dev/null || return 0
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

dev_kill_port_listeners() {
  local port="$1"
  local pids=""
  pids="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ' || true)"
  [[ -n "${pids// }" ]] || return 0
  # shellcheck disable=SC2086
  kill -TERM ${pids} 2>/dev/null || true
  sleep 2
  pids="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ' || true)"
  [[ -z "${pids// }" ]] || kill -9 ${pids} 2>/dev/null || true
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
  local state_dir="${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}"
  local explicit="${MYRM_NEXT_DIST_DIR:-}"
  if [[ -n "${explicit}" && "${explicit}" == "${state_dir}/next" ]]; then
    explicit=""
  fi
  if [[ -n "${explicit}" && "${explicit}" != /* ]]; then
    echo "${explicit}"
    return 0
  fi
  if [[ "${state_dir}" != "${HOME}/.local/state/myrm-dev" ]]; then
    local runtime_ns="${MYRM_RUNTIME_NAMESPACE:-$(basename "$(dirname "${state_dir}")")}"
    runtime_ns="${runtime_ns//[^[:alnum:]_.-]/-}"
    echo ".next-isolated-${runtime_ns}"
    return 0
  fi
  echo "${explicit:-.next}"
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
    if [[ -z "$(find "${entry}" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
      rmdir "${entry}" 2>/dev/null || true
    fi
  done
  shopt -u nullglob
}
