#!/usr/bin/env bash
# Frontend client warmth of frontend-warmup.sh: the hydrated-client record in frontend-warmth.json, the
# single-flight client warmup lock and the CDP hydration run that sets it.
# Sourced by frontend-warmup.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

_frontend_save_client_warmth() {
  local state_file gen source_fingerprint
  state_file="$(_frontend_warmup_state_file)"
  gen="$(_frontend_lock_generation)"
  source_fingerprint="$(_frontend_source_fingerprint)"
  [[ -n "${gen}" ]] || return 0
  [[ -n "${source_fingerprint}" ]] || return 1
  mkdir -p "${STATE_DIR}"
  python3 -c "
import json, datetime
from pathlib import Path
path = Path('${state_file}')
data = {}
if path.is_file():
    data = json.loads(path.read_text())
data['generation'] = '${gen}'
data['source_fingerprint'] = '${source_fingerprint}'
data['client_hot'] = True
data['client_warmed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
if 'warmed_at' not in data:
    data['warmed_at'] = data['client_warmed_at']
    data['url'] = '${APP_URL}/'
path.write_text(json.dumps(data, indent=2) + '\n')
"
}

_frontend_client_warmth_recorded() {
  local state_file gen source_fingerprint
  state_file="$(_frontend_warmup_state_file)"
  gen="$(_frontend_lock_generation)"
  source_fingerprint="$(_frontend_source_fingerprint)"
  [[ -n "${gen}" ]] || return 1
  [[ -n "${source_fingerprint}" ]] || return 1
  [[ -f "${state_file}" ]] || return 1
  _lock_supervisor_alive || return 1
  python3 -c "
import json, sys
from pathlib import Path
state = Path('${state_file}')
if not state.is_file():
    sys.exit(1)
data = json.loads(state.read_text())
if data.get('generation') != '${gen}':
    sys.exit(1)
if data.get('client_hot') is not True:
    sys.exit(1)
fp = '${source_fingerprint}'
if fp and data.get('source_fingerprint') != fp:
    # The frontend sources changed since the client was warmed: the client bundle is cold again and
    # has to be recompiled before a page can boot. The tsconfig include/exclude globs are excluded
    # from the fingerprint, so this only fires for a real source change.
    sys.exit(1)
sys.exit(0)
" 2>/dev/null
}

_frontend_client_hot_status() {
  if ! _frontend_port_listening; then
    echo "down"
    return 0
  fi
  if _frontend_client_warmth_recorded; then
    echo "yes"
    return 0
  fi
  echo "no"
}

_frontend_shell_hot_status() {
  _frontend_compile_hot_status
}

_client_warmup_reclaim_stale_lock() {
  local lockdir="${STATE_DIR}/client-warmup.lock.d"
  [[ -d "${lockdir}" ]] || return 0
  local owner=""
  if [[ -f "${lockdir}/pid" ]]; then
    owner="$(tr -d '[:space:]' <"${lockdir}/pid")"
  fi
  if [[ -z "${owner}" ]] || ! dev_pid_alive "${owner}"; then
    rm -f "${lockdir}/pid" 2>/dev/null || true
    rmdir "${lockdir}" 2>/dev/null || true
  fi
}

_client_warmup_acquire_lock() {
  local lockdir="${STATE_DIR}/client-warmup.lock.d"
  _client_warmup_reclaim_stale_lock
  mkdir "${lockdir}" 2>/dev/null || return 1
  echo "$$" >"${lockdir}/pid"
}

_client_warmup_lock_owner_alive() {
  local owner_file="${STATE_DIR}/client-warmup.lock.d/pid"
  local owner=""
  [[ -f "${owner_file}" ]] || return 1
  owner="$(tr -d '[:space:]' <"${owner_file}")"
  [[ -n "${owner}" ]] && dev_pid_alive "${owner}"
}

_client_warmup_release_lock() {
  local lockdir="${STATE_DIR}/client-warmup.lock.d"
  rm -f "${lockdir}/pid" 2>/dev/null || true
  rmdir "${lockdir}" 2>/dev/null || true
}

_acquire_client_warmup_lock() {
  _client_warmup_acquire_lock
}

_release_client_warmup_lock() {
  _client_warmup_release_lock
}

_warmup_frontend_client() {
  local lib_dir warmup_py cdp_port
  lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  warmup_py="${lib_dir}/browser_orchestrator/frontend_client_warmup.py"
  cdp_port="${MYRM_CHROME_E2E_PORT:-9333}"
  [[ -f "${warmup_py}" ]] || {
    echo "STACK_FAIL: missing frontend_client_warmup.py at ${warmup_py}" >&2
    return 1
  }

  if _frontend_client_warmth_recorded; then
    echo "STACK_OK: frontend client_hot (cached warmth)"
    return 0
  fi

  if [[ "${MYRM_CHROME_E2E_ATTACH:-0}" == "1" ]]; then
    if _frontend_client_warmth_recorded; then
      echo "STACK_OK: frontend client_hot (cached warmth during attach)"
      return 0
    fi
    if [[ "${MYRM_E2E_ATTACH_CLIENT_WARMUP:-0}" == "1" ]]; then
      : # fall through to flock + CDP warmup below (body-phase hydration)
    else
      echo "STACK_WARN: client_hot skipped at attach ADMIT — pytest body will hydrate per-page" >&2
      return 0
    fi
  fi

  local owns_warmup_lock=0
  if _acquire_client_warmup_lock; then
    owns_warmup_lock=1
  else
    echo "STACK_WAIT: client warmup lock busy — waiting for peer Agent..." >&2
    for _ in $(seq 1 "${MYRM_CLIENT_WARMUP_LOCK_SEC:-120}"); do
      if _frontend_client_warmth_recorded; then
        echo "STACK_OK: frontend client_hot (peer warmed)"
        return 0
      fi
      if ! _client_warmup_lock_owner_alive; then
        if _acquire_client_warmup_lock; then
          owns_warmup_lock=1
          echo "STACK_JOIN: peer warmup exited — current Agent acquired client warmup lock" >&2
          break
        fi
      fi
      sleep 1
    done
  fi
  if [[ "${owns_warmup_lock}" -ne 1 ]]; then
    echo "STACK_FAIL: client_hot not reached while waiting for peer warmup" >&2
    return 1
  fi

  trap '_release_client_warmup_lock' RETURN

  if _frontend_client_warmth_recorded; then
    echo "STACK_OK: frontend client_hot (cached after lock)"
    return 0
  fi

  local py="${PREFLIGHT_PY:-python3}"
  local saved_frontmost_pid=""
  local dev_dir="${lib_dir%/lib}"
  local chrome_e2e_cli="${dev_dir}/chrome-e2e/cli.sh"
  if myrm_chrome_e2e_launch_background 2>/dev/null; then
    saved_frontmost_pid="$(myrm_chrome_e2e_save_frontmost_pid)"
    export MYRM_CHROME_E2E_SAVED_FRONTMOST_PID="${saved_frontmost_pid}"
  fi
  echo "STACK_WAIT: frontend client hydration via CDP (up to ${MYRM_CLIENT_WARMUP_TIMEOUT_SEC:-120}s)..." >&2
  if ! "${py}" "${warmup_py}" \
    --cdp-port "${cdp_port}" \
    --url "${APP_URL}/" \
    --timeout-sec "${MYRM_CLIENT_WARMUP_TIMEOUT_SEC:-120}"; then
    echo "STACK_FAIL: frontend client_hot warmup failed — check E2E Chrome :${cdp_port}" >&2
    return 1
  fi

  _frontend_save_client_warmth
  if [[ -f "${chrome_e2e_cli}" ]]; then
    bash "${chrome_e2e_cli}" transition warmup-done "${saved_frontmost_pid}" >/dev/null 2>&1 || true
  fi
  echo "STACK_OK: frontend client_hot (CDP hydration)"
  return 0
}
