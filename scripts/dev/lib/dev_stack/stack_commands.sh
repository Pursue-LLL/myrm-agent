#!/usr/bin/env bash
# Shared-stack commands of dev-stack.sh: backend ensure, attach, ensure, reset and status.
# Sourced by dev-stack.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

_ensure_backend() {
  if ! _start_backend_bg "${SERVER_DIR}"; then
    echo "STACK_FAIL: backend start failed" >&2
    return 1
  fi
  if _wait_backend_health "${MYRM_BACKEND_ENSURING_HEALTH_SEC:-60}"; then
    echo "STACK_OK: backend → ${API_BASE}"
    return 0
  fi
  echo "STACK_FAIL: backend not healthy after start" >&2
  return 1
}

cmd_attach() {
  local attach_start="${SECONDS}"
  local elapsed remaining probe_sec

  _refuse_foreign_backend_listener || exit 1

  _attach_wall_remaining() {
    elapsed=$((SECONDS - attach_start))
    remaining=$((ATTACH_WAIT_SEC - elapsed))
    if (( remaining <= 0 )); then
      return 1
    fi
    echo "${remaining}"
  }

  probe_sec="$(_attach_wall_remaining)" || {
    echo "STACK_ATTACH_TIMEOUT: stack not healthy within ${ATTACH_WAIT_SEC}s — run: ./myrm-dev ready" >&2
    exit 1
  }
  if _api_healthy "${probe_sec}" && _frontend_healthy "${probe_sec}"; then
    echo "STACK_ATTACH_OK api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=http"
    exit 0
  fi

  remaining="$(_attach_wall_remaining)" || {
    echo "STACK_ATTACH_TIMEOUT: stack not healthy within ${ATTACH_WAIT_SEC}s — run: ./myrm-dev ready" >&2
    exit 1
  }
  if _wait_stack_warm "${remaining}"; then
    echo "STACK_ATTACH_OK api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=yes"
    exit 0
  fi

  remaining="$(_attach_wall_remaining)" || {
    echo "STACK_ATTACH_TIMEOUT: stack not healthy within ${ATTACH_WAIT_SEC}s — run: ./myrm-dev ready" >&2
    exit 1
  }
  if _wait_stack_health "${remaining}"; then
    echo "STACK_ATTACH_OK api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=http"
    exit 0
  fi
  echo "STACK_ATTACH_TIMEOUT: stack not healthy within ${ATTACH_WAIT_SEC}s — run: ./myrm-dev ready" >&2
  exit 1
}

_try_optional_client_hot() {
  # The warmup navigates and re-focuses the E2E Chrome, a browser every parallel test agent shares;
  # the user's own stack (`myrm start`) never touches it.
  if dev_is_user_runtime; then
    return 0
  fi
  local cdp_port="${MYRM_CHROME_E2E_PORT:-9333}"
  local py="${SERVER_DIR}/.venv/bin/python"
  if ! curl -sf --max-time 2 "http://127.0.0.1:${cdp_port}/json/version" >/dev/null 2>&1; then
    return 0
  fi
  if [[ ! -x "${py}" ]]; then
    py="python3"
  fi
  export MYRM_CHROME_E2E_PORT="${cdp_port}"
  export PREFLIGHT_PY="${py}"
  unset MYRM_CHROME_E2E_ATTACH
  if _warmup_frontend_client; then
    echo "STACK_OK: client_hot during ensure"
    return 0
  fi
  echo "STACK_WARN: client_hot failed during ensure — run: ./myrm-dev ready --chrome" >&2
  return 0
}

cmd_ensure() {
  if _stack_warm; then
    _ensure_backend || exit 1
    _try_optional_client_hot
    echo "STACK_ENSURE_OK: already shell_hot api=:${BACKEND_PORT} ui=:${FRONTEND_PORT}"
    exit 0
  fi

  if ! _wave_assert_stack_write_allowed; then
    if _frontend_port_listening || _api_healthy 5; then
      echo "STACK_JOIN: ensure deferred — wave/lease active; attach-wait for shell_hot" >&2
      if _wait_stack_warm "${ATTACH_WAIT_SEC}"; then
        _try_optional_client_hot
        echo "STACK_ENSURE_OK: attach-wait during wave pin api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=yes"
        exit 0
      fi
      echo "STACK_ATTACH_TIMEOUT: stack not shell_hot within ${ATTACH_WAIT_SEC}s during wave pin" >&2
      exit 1
    fi
    echo "STACK_FAIL: ensure denied while wave pins stack — use: ./myrm-dev ready --attach --chrome" >&2
    exit 1
  fi

  if _join_ensure_in_progress "${_lock_dir}" "${ATTACH_WAIT_SEC}"; then
    exit 0
  fi

  if ! _acquire_dir_lock "${_lock_dir}" "${ATTACH_WAIT_SEC}"; then
    if _wait_stack_warm "${ATTACH_WAIT_SEC}"; then
      _try_optional_client_hot
      echo "STACK_ENSURE_OK: joined late ensure api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=yes"
      exit 0
    fi
    echo "STACK_FAIL: could not acquire stack ensure lock within ${ATTACH_WAIT_SEC}s" >&2
    exit 1
  fi
  trap '_release_dir_lock "${_lock_dir}"' EXIT

  if _stack_warm; then
    _ensure_backend || exit 1
    _try_optional_client_hot
    echo "STACK_ENSURE_OK: already shell_hot api=:${BACKEND_PORT} ui=:${FRONTEND_PORT}"
    exit 0
  fi

  _ensure_backend || exit 1
  _start_frontend_supervisor || exit 1

  if ! _wait_stack_health "${ENSURE_FRONTEND_WAIT_SEC}"; then
    if ! _api_healthy 5 || ! _wait_frontend_http_200 30; then
      echo "STACK_FAIL: stack not HTTP healthy after ensure" >&2
      exit 1
    fi
  fi

  if _warmup_frontend_compile; then
    _try_optional_client_hot
    echo "STACK_ENSURE_OK: api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=yes"
    exit 0
  fi
  echo "STACK_FAIL: stack not shell_hot after ensure" >&2
  exit 1
}

cmd_reset() {
  _wave_assert_stack_write_allowed || exit 3

  # reset stops what this stack started — a listener it did not start (the desktop sidecar,
  # a `myrm start` WebUI) is left running and reported.
  _frontend_journal_kill reset \
    "$(_owned_pid_from_file "${FRONTEND_PID}") $(_owned_frontend_listener_pids)"
  if [[ -f "${FRONTEND_PID}" ]]; then
    local fe_pid
    fe_pid="$(_owned_pid_from_file "${FRONTEND_PID}")"
    if [[ -n "${fe_pid}" ]]; then
      kill "${fe_pid}" 2>/dev/null || true
    fi
    rm -f "${FRONTEND_PID}"
  fi
  rm -f "${FRONTEND_LOCK}"
  _frontend_clear_warmth
  _clear_stack_epoch

  if [[ -f "${BACKEND_PID}" ]]; then
    local dev_pid
    dev_pid="$(_owned_pid_from_file "${BACKEND_PID}")"
    if [[ -n "${dev_pid}" ]] && dev_pid_alive "${dev_pid}"; then
      kill -TERM "${dev_pid}" 2>/dev/null || true
      local _
      for _ in $(seq 1 15); do
        dev_pid_alive "${dev_pid}" || break
        sleep 1
      done
      if dev_pid_alive "${dev_pid}"; then
        kill -9 "${dev_pid}" 2>/dev/null || true
      fi
    fi
    rm -f "${BACKEND_PID}"
  fi

  local owned_pids
  owned_pids="$(_owned_frontend_listener_pids)"
  if [[ -n "${owned_pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${owned_pids} 2>/dev/null || true
  fi

  owned_pids="$(_owned_backend_listener_pids)"
  if [[ -n "${owned_pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${owned_pids} 2>/dev/null || true
  fi

  _clear_stack_epoch

  echo "STACK_RESET_OK"
}

cmd_status() {
  local api="down" fe="down" lock="missing" shell_hot="down" stack_epoch=""
  _api_healthy 3 && api="up"
  _frontend_healthy 5 && fe="up"
  shell_hot="$(_frontend_compile_hot_status)"
  stack_epoch="$(_read_stack_epoch 2>/dev/null || true)"
  _lock_supervisor_alive && lock="alive"
  [[ -f "${FRONTEND_LOCK}" ]] && [[ "${lock}" == "missing" ]] && lock="stale"
  echo "stack_status api=${api} frontend=${fe} shell_hot=${shell_hot} client_hot=$(_frontend_client_hot_status) stack_epoch=${stack_epoch:-none} dev_lock=${lock}"
}
