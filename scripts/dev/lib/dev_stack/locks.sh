#!/usr/bin/env bash
# Ensure-lock primitives of dev-stack.sh: the mkdir lock with holder-identity proof, and the bounded
# joins that wait for another caller's ensure to finish.
# Sourced by dev-stack.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

_acquire_dir_lock() {
  local lockdir="$1"
  local wait_sec="$2"
  local reclaim_hung="${3:-1}"

  if [[ -d "${lockdir}" ]]; then
    local owner=""
    if [[ -f "${lockdir}/pid" ]]; then
      owner="$(tr -d '[:space:]' <"${lockdir}/pid")"
    fi
    if [[ -n "${owner}" ]] && dev_pid_alive "${owner}"; then
      local lock_mtime now age
      lock_mtime="$(stat -f %m "${lockdir}/pid" 2>/dev/null || stat -c %Y "${lockdir}/pid" 2>/dev/null || echo 0)"
      now="$(date +%s)"
      age=$((now - lock_mtime))
      if [[ "${reclaim_hung}" == "1" && "${age}" -gt "${wait_sec}" ]]; then
        echo "STACK_WARN: reclaiming hung lock ${lockdir} owner=${owner} age=${age}s" >&2
        # A stale lock can name a pid that any other process has since recycled; only the
        # process that took the lock (same start time) is ever signalled.
        if _lock_owner_is_holder "${lockdir}" "${owner}"; then
          kill -TERM "${owner}" 2>/dev/null || true
          sleep 1
        fi
        _release_dir_lock "${lockdir}"
      fi
    elif [[ -z "${owner}" ]] || ! dev_pid_alive "${owner}"; then
      echo "STACK_WARN: reclaiming stale lock ${lockdir}" >&2
      _release_dir_lock "${lockdir}"
    fi
  fi

  local _
  for _ in $(seq 1 "${wait_sec}"); do
    if mkdir "${lockdir}" 2>/dev/null; then
      echo "$$" >"${lockdir}/pid"
      _pid_start_time "$$" >"${lockdir}/start"
      return 0
    fi
    sleep 1
  done
  return 1
}

_pid_start_time() {
  ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' || true
}

# True when `owner` is still the process that took the lock (its start time was recorded with it).
_lock_owner_is_holder() {
  local recorded
  recorded="$(cat "$1/start" 2>/dev/null || true)"
  [[ -n "${recorded}" && "$(_pid_start_time "$2")" == "${recorded}" ]]
}

_release_dir_lock() {
  local lockdir="$1"
  rm -f "${lockdir}/pid" "${lockdir}/start" 2>/dev/null || true
  rmdir "${lockdir}" 2>/dev/null || true
}

_ensure_lock_owner_alive() {
  local lockdir="$1"
  local owner=""

  [[ -d "${lockdir}" ]] || return 1
  if [[ -f "${lockdir}/pid" ]]; then
    owner="$(tr -d '[:space:]' <"${lockdir}/pid")"
  fi
  [[ -n "${owner}" ]] && dev_pid_alive "${owner}"
}

_join_ensure_in_progress() {
  local lockdir="$1"
  local wait_sec="$2"
  local owner=""

  if ! _ensure_lock_owner_alive "${lockdir}"; then
    return 1
  fi
  owner="$(tr -d '[:space:]' <"${lockdir}/pid")"
  echo "STACK_JOIN: ensure in progress (pid=${owner}) — waiting for shell_hot" >&2
  if _wait_stack_warm "${wait_sec}"; then
    _try_optional_client_hot
    echo "STACK_ENSURE_OK: joined in-progress ensure api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=yes"
    return 0
  fi
  return 1
}

_backend_only_lock_wait_sec() {
  local raw="${MYRM_BACKEND_ONLY_LOCK_WAIT_SEC:-60}"
  if [[ "${raw}" =~ ^[0-9]+$ && "${raw}" -ge 15 ]]; then
    echo "${raw}"
  else
    echo 60
  fi
}

_wait_backend_health() {
  local max="${1:-60}"
  local _
  for _ in $(seq 1 "${max}"); do
    if _api_healthy 1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

_join_backend_ensure_in_progress() {
  local lockdir="$1"
  local wait_sec="$2"
  local owner=""

  if ! _ensure_lock_owner_alive "${lockdir}"; then
    return 1
  fi
  owner="$(tr -d '[:space:]' <"${lockdir}/pid")"
  echo "STACK_JOIN: backend ensure in progress (pid=${owner}) — waiting for API health" >&2
  if _wait_backend_health "${wait_sec}"; then
    echo "STACK_BACKEND_ONLY_ENSURE_OK: joined in-progress backend api=:${BACKEND_PORT}" >&2
    return 0
  fi
  return 1
}
