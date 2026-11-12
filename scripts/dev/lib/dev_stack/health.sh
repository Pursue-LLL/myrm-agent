#!/usr/bin/env bash
# Health probes of dev-stack.sh: HTTP/asset/proxy checks of the API and UI, the stack-level predicates
# and their bounded waits.
# Sourced by dev-stack.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

_http_ok() {
  local url="$1"
  local max_time="${2:-8}"
  curl -sf --max-time "${max_time}" "${url}" >/dev/null 2>&1
}

_frontend_client_assets_ok() {
  # The dev server can serve HTML while every client chunk 404s: a production build in the same
  # directory wipes the dev server's output. The page then never hydrates, so every UI test fails
  # while the HTTP probe still reports "healthy". Probe one real client chunk before trusting it.
  local max_time="${1:-8}"
  local page chunk
  page="$(curl -sf --max-time "${max_time}" "${APP_URL}/" 2>/dev/null)" || return 1
  chunk="$(printf '%s' "${page}" | grep -oE '/_next/static/chunks/[^"'"'"' ]+\.js' | head -1)"
  [[ -n "${chunk}" ]] || return 1
  _http_ok "${APP_URL}${chunk}" "${max_time}"
}

_frontend_http_probe_timeout_sec() {
  local raw="${MYRM_E2E_ATTACH_UI_PROBE_TIMEOUT_SEC:-}"
  if [[ "${raw}" =~ ^[0-9]+$ && "${raw}" -gt 0 ]]; then
    echo "${raw}"
    return 0
  fi
  local resolved=""
  resolved="$("${PREFLIGHT_PY:-python3}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from dev_gate.contract import attach_ui_probe_timeout_sec
print(int(attach_ui_probe_timeout_sec()))
" 2>/dev/null)" || true
  if [[ "${resolved}" =~ ^[0-9]+$ && "${resolved}" -gt 0 ]]; then
    echo "${resolved}"
    return 0
  fi
  echo 8
}

_frontend_http_status() {
  local max_time
  max_time="$(_frontend_http_probe_timeout_sec)"
  curl -s -o /dev/null -w "%{http_code}" --max-time "${max_time}" "${APP_URL}/" 2>/dev/null || echo "000"
}

_wait_frontend_http_200() {
  local max="${1:-${ENSURE_FRONTEND_WAIT_SEC}}"
  local i code port_seen=0
  for i in $(seq 1 "${max}"); do
    if _frontend_port_listening; then
      port_seen=1
    fi
    code="$(_frontend_http_status)"
    if [[ "${code}" == "200" ]]; then
      return 0
    fi
    if ! _api_healthy 3; then
      if [[ "${i}" -eq 1 || $((i % 10)) -eq 0 ]]; then
        echo "STACK_HEAL: backend down during frontend wait (${i}/${max}s) — re-ensure backend" >&2
        _ensure_backend || true
      fi
    fi
    _sync_frontend_pid_from_lock
    if [[ -f "${FRONTEND_PID}" ]]; then
      local supervisor_pid
      supervisor_pid="$(tr -d '[:space:]' <"${FRONTEND_PID}")"
      if [[ -n "${supervisor_pid}" ]] && ! dev_pid_alive "${supervisor_pid}" && ! _lock_supervisor_alive; then
        echo "STACK_WARN: frontend supervisor exited before HTTP readiness — check ${FRONTEND_LOG}" >&2
        return 1
      fi
    fi
    if [[ "${port_seen}" -eq 1 ]] && [[ "${i}" == "1" || $((i % 15)) -eq 0 ]]; then
      echo "STACK_WAIT: frontend GET / → HTTP ${code} (${i}/${max}s, cold compile tolerated)..." >&2
    fi
    sleep 1
  done
  if [[ "${port_seen}" -eq 1 ]]; then
    echo "STACK_WARN: :${FRONTEND_PORT} listening but GET / never returned 200 (last=${code})" >&2
  else
    echo "STACK_WARN: :${FRONTEND_PORT} never listened within ${max}s" >&2
  fi
  return 1
}

_api_healthy() {
  _http_ok "${API_HEALTH}" "${1:-5}"
}

_frontend_healthy() {
  local probe_timeout
  probe_timeout="$(_frontend_http_probe_timeout_sec)"
  _http_ok "${APP_URL}/" "${1:-${probe_timeout}}"
}

_frontend_proxy_healthy() {
  # The static shell can serve 200 while the API rewrite behind it is dead: the
  # frontend bakes its upstream at spawn time, so it can point at a backend that has
  # since gone away. A shell-only probe reports that broken state as healthy, which
  # silently fails every UI test that reads data. Kept separate from
  # `_frontend_healthy` so the frontend restart path never churns on an API blip.
  _http_ok "${APP_URL}/api/v1/health" "${1:-5}"
}

_stack_healthy() {
  _api_healthy 5 && _frontend_healthy 8 && _frontend_proxy_healthy 5 && _frontend_binding_matches 2>/dev/null
}

_stack_warm() {
  _backend_supervisor_alive || return 1
  _lock_supervisor_alive || return 1
  _api_healthy 5 || return 1
  _frontend_healthy 8 || return 1
  _frontend_proxy_healthy 5 || return 1
  _frontend_binding_matches 2>/dev/null || return 1
  [[ "$(_frontend_compile_hot_status)" == "yes" ]]
}

_wait_stack_health() {
  local max="${1:-${ATTACH_WAIT_SEC}}"
  local i
  for i in $(seq 1 "${max}"); do
    if _stack_healthy; then
      return 0
    fi
    sleep 1
  done
  return 1
}

_wait_stack_warm() {
  local max="${1:-${ATTACH_WAIT_SEC}}"
  local i
  for i in $(seq 1 "${max}"); do
    if _stack_warm; then
      return 0
    fi
    sleep 1
  done
  return 1
}
