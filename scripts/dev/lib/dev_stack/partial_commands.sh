#!/usr/bin/env bash
# Partial-stack commands of dev-stack.sh: backend-only ensure/stop and frontend-only ensure.
# Sourced by dev-stack.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

cmd_backend_only_ensure() {
  # 与 cmd_ensure 共用 ensure.lock.d，但 backend-only 恢复不能等待前端
  # shell_hot：那会把一次 backend heal 放大成 360s 的前端冷编译等待。
  # 只等待 API 健康，并在锁仍被完整 ensure 持有时 fail-fast；禁止恢复路径
  # 误杀正在进行的完整 ensure。
  local backend_lock_wait
  backend_lock_wait="$(_backend_only_lock_wait_sec)"
  if _join_backend_ensure_in_progress "${_lock_dir}" "${backend_lock_wait}"; then
    exit 0
  fi
  if ! _acquire_dir_lock "${_lock_dir}" "${backend_lock_wait}" 0; then
    echo "STACK_FAIL: backend-only ensure lock busy after ${backend_lock_wait}s; retry via bounded supervisor heal" >&2
    exit 1
  fi
  trap '_release_dir_lock "${_lock_dir}"' EXIT
  _stack_stage lock_acquired

  if ! _ensure_backend; then
    echo "STACK_FAIL: private backend start failed" >&2
    exit 1
  fi

  if _api_healthy 5; then
    if ! _private_backend_identity_valid; then
      if ! _sync_private_backend_identity_from_port; then
        if ! _repair_orphan_private_backend; then
          echo "STACK_FAIL: healthy private port lacks matching process ownership" >&2
          exit 1
        fi
        if ! _ensure_backend; then
          echo "STACK_FAIL: private backend restart after orphan reclaim failed" >&2
          exit 1
        fi
      fi
      if ! _private_backend_identity_valid; then
        echo "STACK_FAIL: healthy private port lacks matching process ownership after reclaim" >&2
        exit 1
      fi
    fi
    echo "STACK_OK: private backend already healthy → ${API_BASE}"
    _stack_stage ensure_done
    echo "STACK_BACKEND_ONLY_ENSURE_OK: api=:${BACKEND_PORT} ui=shared:${FRONTEND_PORT}"
    exit 0
  fi

  if _wait_backend_health "${MYRM_BACKEND_ENSURING_HEALTH_SEC:-60}"; then
    _stack_stage ensure_done
    echo "STACK_BACKEND_ONLY_ENSURE_OK: api=:${BACKEND_PORT} ui=shared:${FRONTEND_PORT}"
    exit 0
  fi
  echo "STACK_FAIL: private backend not healthy after ensure" >&2
  exit 1
}

cmd_backend_only_stop() {
  if ! _stop_private_backend; then
    exit 1
  fi
  echo "STACK_BACKEND_ONLY_STOP_OK"
}

cmd_frontend_only_ensure() {
  local gate_rc=0 start_rc=0
  if _frontend_dev_paused; then
    if _frontend_healthy || _frontend_port_listening; then
      echo "STACK_FRONTEND_RECLAIM: pause active — stopping existing frontend on :${FRONTEND_PORT}" >&2
      _kill_frontend_supervisor pause || true
      _repair_orphan_frontend pause || true
    fi
    echo "STACK_FRONTEND_ONLY_ENSURE_SKIP: frontend dev paused (bun run cleanup); run: frontend-only clear-pause" >&2
    exit 0
  fi
  local needs_client_hot=0
  # Only the attach heal path requires client_hot (SHPOIB shell binds a hydrated
  # page). warm_ui_route heal sets MYRM_CHROME_E2E_FRONTEND_HEAL but runs before
  # Chrome opens any page, so client_hot is legitimately "no" there — requiring
  # it would clean-restart the frontend every warm heal (heal loop, §26.30).
  if [[ "${MYRM_E2E_ATTACH_FRONTEND_HEAL:-}" == "1" ]]; then
    needs_client_hot=1
  fi
  if _frontend_healthy; then
    if ! _frontend_client_assets_ok; then
      # HTTP 200 but the client chunks are gone: the page renders server-side HTML and never
      # hydrates, so the E2E bridge never installs and every UI test fails on a "healthy" UI.
      echo "STACK_HEAL: frontend HTTP 200 but client assets missing — clean restart" >&2
      if _frontend_clean_restart_heal client_assets_missing client_assets_heal; then
        exit 0
      fi
      echo "STACK_FAIL: frontend client assets are missing and the heal was denied" >&2
      exit 1
    fi
    if [[ "${needs_client_hot}" -eq 0 ]] || [[ "$(_frontend_client_hot_status)" == "yes" ]]; then
      echo "STACK_FRONTEND_ONLY_ENSURE_OK: ui=:${FRONTEND_PORT}"
      exit 0
    fi
    echo "STACK_HEAL: frontend HTTP 200 but client_hot=no — clean restart (attach frontend heal)" >&2
    if _frontend_clean_restart_heal client_hot_no client_hot_heal; then
      exit 0
    fi
    echo "STACK_FAIL: frontend client_hot heal failed within attach frontend heal" >&2
    exit 1
  fi
  if _frontend_port_listening; then
    if _wait_frontend_http_200 "${ATTACH_WAIT_SEC}"; then
      _sync_frontend_pid_from_lock
      echo "STACK_FRONTEND_ONLY_ENSURE_OK: ui=:${FRONTEND_PORT} compile_wait=yes"
      exit 0
    fi
    if _frontend_heal_stack_write_allowed; then
      echo "STACK_HEAL: frontend listening but not HTTP 200 — clean retry (E2E attach heal)" >&2
      _frontend_restart_prepare unresponsive || gate_rc=$?
      case "${gate_rc}" in
        0)
          if _try_frontend_start_with_clean_fallback; then
            echo "STACK_FRONTEND_ONLY_ENSURE_OK: ui=:${FRONTEND_PORT} compile_wait=clean_retry"
            exit 0
          fi
          ;;
        "${FRONTEND_GATE_HEALTHY}")
          _sync_frontend_pid_from_lock
          echo "STACK_FRONTEND_ONLY_ENSURE_OK: ui=:${FRONTEND_PORT} compile_wait=yes"
          exit 0
          ;;
        "${FRONTEND_GATE_DENIED}")
          echo "STACK_FAIL: frontend still compiling — restart denied, nothing was killed (retry later)" >&2
          exit 1
          ;;
      esac
    fi
    echo "STACK_FAIL: frontend listening but not HTTP 200 within ${ATTACH_WAIT_SEC}s" >&2
    exit 1
  fi
  echo "STACK_HEAL: shared frontend port :${FRONTEND_PORT} dead — cold start (no kill)" >&2
  _start_frontend_supervisor || start_rc=$?
  if [[ "${start_rc}" -eq "${FRONTEND_GATE_DENIED}" ]]; then
    echo "STACK_FAIL: frontend still compiling — restart denied, nothing was killed (retry later)" >&2
    exit 1
  fi
  if [[ "${start_rc}" -ne 0 ]]; then
    if _frontend_heal_stack_write_allowed; then
      echo "STACK_HEAL: frontend cold start failed — retry with --clean (E2E attach heal)" >&2
      _frontend_restart_prepare unresponsive || gate_rc=$?
      case "${gate_rc}" in
        0)
          if _try_frontend_start_with_clean_fallback; then
            echo "STACK_FRONTEND_ONLY_ENSURE_OK: ui=:${FRONTEND_PORT} cold_start=clean_retry"
            exit 0
          fi
          ;;
        "${FRONTEND_GATE_HEALTHY}")
          _sync_frontend_pid_from_lock
          echo "STACK_FRONTEND_ONLY_ENSURE_OK: ui=:${FRONTEND_PORT} cold_start=yes"
          exit 0
          ;;
        "${FRONTEND_GATE_DENIED}")
          echo "STACK_FAIL: frontend still compiling — restart denied, nothing was killed (retry later)" >&2
          exit 1
          ;;
      esac
    fi
    echo "STACK_FAIL: frontend cold start failed" >&2
    exit 1
  fi
  echo "STACK_FRONTEND_ONLY_ENSURE_OK: ui=:${FRONTEND_PORT} cold_start=yes"
}
