#!/usr/bin/env bash
# Frontend compile warmth gate — SSOT for "GET / is hot" (not just port LISTEN or one-off HTTP 200).
# Sourced by dev-stack.sh; do not execute directly.
set -euo pipefail

_MYRM_WARMUP_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! declare -f myrm_chrome_e2e_launch_background >/dev/null 2>&1; then
  # shellcheck source=../myrm-chrome-e2e-lib.sh
  source "${_MYRM_WARMUP_LIB_DIR}/../myrm-chrome-e2e-lib.sh"
fi

FRONTEND_WARM_STREAK="${MYRM_FRONTEND_WARM_STREAK:-2}"
FRONTEND_WARM_MAX_SEC="${MYRM_FRONTEND_WARM_MAX_SEC:-180}"
FRONTEND_WARM_FAST_SEC="${MYRM_FRONTEND_WARM_FAST_SEC:-2}"
MYRM_UI_HEAL_SLOW_SEC="${MYRM_UI_HEAL_SLOW_SEC:-5}"
MYRM_UI_HEAL_PROBE_TIMEOUT_SEC="${MYRM_UI_HEAL_PROBE_TIMEOUT_SEC:-}"

_attach_ui_probe_timeout_sec() {
  if [[ "${MYRM_UI_HEAL_PROBE_TIMEOUT_SEC:-}" =~ ^[0-9]+$ && "${MYRM_UI_HEAL_PROBE_TIMEOUT_SEC}" -gt 0 ]]; then
    echo "${MYRM_UI_HEAL_PROBE_TIMEOUT_SEC}"
    return 0
  fi
  local resolved=""
  resolved="$("${PREFLIGHT_PY:-python3}" -c "
import sys
sys.path.insert(0, '${_MYRM_WARMUP_LIB_DIR}')
from dev_gate_contract import attach_ui_probe_timeout_sec
print(int(attach_ui_probe_timeout_sec()))
" 2>/dev/null)" || true
  if [[ "${resolved}" =~ ^[0-9]+$ && "${resolved}" -gt 0 ]]; then
    echo "${resolved}"
    return 0
  fi
  echo 12
}

_attach_ui_liveness_probe_timeout_sec() {
  local resolved=""
  resolved="$("${PREFLIGHT_PY:-python3}" -c "
import sys
sys.path.insert(0, '${_MYRM_WARMUP_LIB_DIR}')
from dev_gate_contract import attach_ui_liveness_probe_timeout_sec
print(int(attach_ui_liveness_probe_timeout_sec()))
" 2>/dev/null)" || true
  if [[ "${resolved}" =~ ^[0-9]+$ && "${resolved}" -gt 0 ]]; then
    echo "${resolved}"
    return 0
  fi
  echo 8
}

# Frontend dev-server lock holder must be alive (warmth invalid if Turbopack process died).
# Also sourced by chrome-e2e-preflight.sh without dev-stack.sh — must live here.
_lock_supervisor_alive() {
  [[ -f "${FRONTEND_LOCK}" ]] || return 1
  local pid
  pid="$(python3 -c "
import json, sys
from pathlib import Path
p = Path('${FRONTEND_LOCK}')
if not p.is_file():
    sys.exit(1)
data = json.loads(p.read_text())
pid = data.get('pid')
if not isinstance(pid, int):
    sys.exit(1)
print(pid)
" 2>/dev/null)" || return 1
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

_frontend_port_listening() {
  local port="${FRONTEND_PORT:-3000}"
  lsof -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1
}

_frontend_warmup_state_file() {
  echo "${STATE_DIR}/frontend-warmth.json"
}

_frontend_lock_generation() {
  if [[ ! -f "${FRONTEND_LOCK}" ]]; then
    echo ""
    return 0
  fi
  local bundler_stamp="$(dirname "${FRONTEND_LOCK}")/dev-bundler-mode"
  local bundler_mode=""
  if [[ -f "${bundler_stamp}" ]]; then
    bundler_mode="$(tr -d '[:space:]' < "${bundler_stamp}")"
  fi
  python3 -c "
import json
from pathlib import Path
p = Path('${FRONTEND_LOCK}')
if not p.is_file():
    raise SystemExit(0)
data = json.loads(p.read_text())
parts = [str(data.get('pid', '')), str(data.get('startedAt', '')), str(data.get('port', '')), '${bundler_mode}']
print(':'.join(parts))
" 2>/dev/null || true
}

_frontend_source_fingerprint() {
  local lib_dir py
  lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  py="${PREFLIGHT_PY:-python3}"
  "${py}" - "${lib_dir}" "${FRONTEND_DIR}" <<'PY' 2>/dev/null || true
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from runtime_identity import frontend_source_fingerprint

print(frontend_source_fingerprint(Path(sys.argv[2])))
PY
}

_frontend_warmth_recorded() {
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
if data.get('source_fingerprint') != '${source_fingerprint}':
    sys.exit(1)
sys.exit(0)
" 2>/dev/null
}

_frontend_save_warmth() {
  local state_file gen source_fingerprint client_hot_py
  state_file="$(_frontend_warmup_state_file)"
  gen="$(_frontend_lock_generation)"
  source_fingerprint="$(_frontend_source_fingerprint)"
  [[ -n "${gen}" ]] || return 0
  [[ -n "${source_fingerprint}" ]] || return 1
  client_hot_py="False"
  if [[ "${1:-}" == "true" ]]; then
    client_hot_py="True"
  fi
  mkdir -p "${STATE_DIR}"
  python3 -c "
import json, datetime
from pathlib import Path
payload = {
    'generation': '${gen}',
    'source_fingerprint': '${source_fingerprint}',
    'warmed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'url': '${APP_URL}/',
    'client_hot': ${client_hot_py},
}
if ${client_hot_py}:
    payload['client_warmed_at'] = payload['warmed_at']
Path('${state_file}').write_text(json.dumps(payload, indent=2) + '\n')
"
}

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
if data.get('source_fingerprint') != fp and fp:
    # Next.js may rewrite tsconfig include during cold start; same dev-server generation is still valid.
    data['source_fingerprint'] = fp
    state.write_text(json.dumps(data, indent=2) + '\n')
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
  if [[ -z "${owner}" ]] || ! kill -0 "${owner}" 2>/dev/null; then
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
  [[ -n "${owner}" ]] && kill -0 "${owner}" 2>/dev/null
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
  warmup_py="${lib_dir}/frontend-client-warmup.py"
  cdp_port="${MYRM_CHROME_E2E_PORT:-9333}"
  [[ -f "${warmup_py}" ]] || {
    echo "STACK_FAIL: missing frontend-client-warmup.py at ${warmup_py}" >&2
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
      : # fall through to flock + CDP warmup below (R284 body-phase hydration)
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
    local i
    for i in $(seq 1 "${MYRM_CLIENT_WARMUP_LOCK_SEC:-120}"); do
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

_frontend_clear_warmth() {
  local state_file
  state_file="$(_frontend_warmup_state_file)"
  rm -f "${state_file}" 2>/dev/null || true
  _client_warmup_release_lock
}

_frontend_curl_seconds() {
  curl -sf --max-time 5 -o /dev/null -w "%{time_total}" "${APP_URL}/" 2>/dev/null || return 1
}

_frontend_html_probe_ok() {
  # W2 #4: SSOT dual probe — fresh TCP connect + first-packet HTML (not cached urlopen 200).
  local py probe_timeout
  py="${PREFLIGHT_PY:-python3}"
  probe_timeout="$(_attach_ui_probe_timeout_sec)"
  "${py}" - "${_MYRM_WARMUP_LIB_DIR}" "${APP_URL}" "${probe_timeout}" <<'PY' 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
from runtime_identity import frontend_tcp_html_probe_ok
sys.exit(0 if frontend_tcp_html_probe_ok(sys.argv[2], timeout_sec=float(sys.argv[3])) else 1)
PY
}

_frontend_compile_hot_status() {
  if ! _frontend_port_listening; then
    echo "down"
    return 0
  fi
  # W2 #4: cached warmth must not fake liveness — require live TCP+HTML before any "yes".
  if ! _frontend_html_probe_ok; then
    echo "no"
    return 0
  fi
  if _frontend_warmth_recorded; then
    echo "yes"
    return 0
  fi
  local timing
  if timing="$(_frontend_curl_seconds)"; then
    if awk -v t="${timing}" -v fast="${FRONTEND_WARM_FAST_SEC}" 'BEGIN { exit (t <= fast ? 0 : 1) }'; then
      echo "yes"
      return 0
    fi
    echo "compiling"
    return 0
  fi
  echo "no"
}

_warmup_frontend_compile() {
  if _frontend_warmth_recorded; then
    echo "STACK_OK: frontend shell_hot (cached warmth)"
    return 0
  fi

  local streak=0
  local i timing
  for i in $(seq 1 "${FRONTEND_WARM_MAX_SEC}"); do
    if ! _frontend_port_listening; then
      streak=0
      echo "STACK_WAIT: frontend port not listening (${i}/${FRONTEND_WARM_MAX_SEC}s)..." >&2
      sleep 1
      continue
    fi

    if timing="$(_frontend_curl_seconds)"; then
      if awk -v t="${timing}" -v fast="${FRONTEND_WARM_FAST_SEC}" 'BEGIN { exit (t <= fast ? 0 : 1) }'; then
        streak=$((streak + 1))
        if [[ "${streak}" -ge "${FRONTEND_WARM_STREAK}" ]]; then
          _frontend_save_warmth
          echo "STACK_OK: frontend shell_hot (${timing}s x${FRONTEND_WARM_STREAK})"
          return 0
        fi
        echo "STACK_WAIT: frontend warm streak ${streak}/${FRONTEND_WARM_STREAK} (${timing}s)..." >&2
      else
        streak=0
        echo "STACK_WAIT: frontend compiling (${timing}s)..." >&2
      fi
    else
      streak=0
      echo "STACK_WAIT: frontend HTTP not ready (${i}/${FRONTEND_WARM_MAX_SEC}s)..." >&2
    fi
    sleep 1
  done

  echo "STACK_FAIL: frontend shell_hot not reached within ${FRONTEND_WARM_MAX_SEC}s — check ${FRONTEND_LOG}" >&2
  return 1
}

_frontend_root_probe_seconds() {
  local probe_timeout
  probe_timeout="$(_attach_ui_probe_timeout_sec)"
  curl -sf --connect-timeout 5 --max-time "${probe_timeout}" -o /dev/null -w "%{time_total}" "${APP_URL}/" 2>/dev/null || return 1
}

_frontend_liveness_probe_seconds() {
  local probe_timeout
  probe_timeout="$(_attach_ui_liveness_probe_timeout_sec)"
  curl -sf --connect-timeout 3 --max-time "${probe_timeout}" -o /dev/null -w "%{time_total}" "${APP_URL}/" 2>/dev/null || return 1
}

# R149: parallel Next compile may flap HTTP 000 immediately after ensure OK — require warm streak.
_frontend_post_heal_warm_streak_ok() {
  local max_sec="${MYRM_UI_HEAL_POST_ENSURE_MAX_SEC:-60}"
  local streak_required="${FRONTEND_WARM_STREAK}" streak=0 i timing="" pressure=0
  pressure="$("${PREFLIGHT_PY:-python3}" -c "
import sys
sys.path.insert(0, '${_MYRM_WARMUP_LIB_DIR}')
from dev_gate_contract import _parallel_chrome_e2e_pressure
print(_parallel_chrome_e2e_pressure())
" 2>/dev/null || echo 0)"
  if [[ "${pressure}" =~ ^[0-9]+$ && "${pressure}" -ge 1 ]]; then
    streak_required=1
    local scaled=$((60 + pressure * 6))
    if [[ "${scaled}" -gt "${max_sec}" ]]; then
      max_sec="${scaled}"
    fi
  fi
  for i in $(seq 1 "${max_sec}"); do
    if timing="$(_frontend_liveness_probe_seconds)"; then
      if awk -v t="${timing}" -v slow="${MYRM_UI_HEAL_SLOW_SEC}" 'BEGIN { exit (t <= slow ? 0 : 1) }'; then
        streak=$((streak + 1))
        if [[ "${streak}" -ge "${streak_required}" ]]; then
          echo "${timing}"
          return 0
        fi
        echo "CHROME_E2E_HEAL: post-ensure warm streak ${streak}/${streak_required} (${timing}s)..." >&2
      else
        streak=0
        echo "CHROME_E2E_HEAL: post-ensure still slow (${timing}s)..." >&2
      fi
    else
      streak=0
      echo "CHROME_E2E_HEAL: post-ensure HTTP not ready (${i}/${max_sec}s)..." >&2
    fi
    sleep 1
  done
  return 1
}

# Wave-safe heal: detect LISTEN-but-slow / stale warmth (black-screen class) and cold-start Next.
_heal_shared_ui_if_stale() {
  local stack="${MYRM_DEV_STACK:-}"
  local timing="" reason=""
  if ! _frontend_port_listening; then
    reason="port_down"
  elif timing="$(_frontend_liveness_probe_seconds)"; then
    if awk -v t="${timing}" -v slow="${MYRM_UI_HEAL_SLOW_SEC}" 'BEGIN { exit (t <= slow ? 0 : 1) }'; then
      return 0
    fi
    reason="slow_${timing}s"
  else
    reason="http_fail"
  fi
  [[ -n "${stack}" && -f "${stack}" ]] || {
    echo "CHROME_E2E_HEAL_SKIP: shared UI stale (${reason}) but MYRM_DEV_STACK missing" >&2
    return 1
  }
  local monorepo_root heal_py outcome timing_after=""
  monorepo_root="$(cd "$(dirname "${stack}")/../../.." && pwd)"
  heal_py="${_MYRM_WARMUP_LIB_DIR}/e2e_warm_ui_heal.py"
  for heal_attempt in 1 2; do
    echo "CHROME_E2E_HEAL: shared UI stale (${reason}) — frontend-only ensure ${heal_attempt}/2" >&2
    _frontend_clear_warmth
    outcome="$("${PREFLIGHT_PY:-python3}" "${heal_py}" attach "${monorepo_root}" 2>&1 | tail -1 || true)"
    if timing_after="$(_frontend_post_heal_warm_streak_ok)"; then
      echo "CHROME_E2E_HEAL_OK: shared UI ${timing_after}s after frontend-only ensure (${outcome})" >&2
      return 0
    fi
    if [[ "${heal_attempt}" -eq 1 && "${outcome}" == "follower_timeout" ]]; then
      echo "CHROME_E2E_HEAL: attach frontend heal deferred — retry after leader window" >&2
      sleep 5
      continue
    fi
    if [[ "${heal_attempt}" -eq 1 ]]; then
      echo "CHROME_E2E_HEAL: frontend-only ensure failed — supervisor fallback (wave-safe frontend heal)" >&2
      if bash "${stack%/*}/stack-supervisor.sh" rpc ping >/dev/null 2>&1; then
        outcome="$("${PREFLIGHT_PY:-python3}" "${heal_py}" attach "${monorepo_root}" 2>&1 | tail -1 || true)"
        if timing_after="$(_frontend_post_heal_warm_streak_ok)"; then
          echo "CHROME_E2E_HEAL_OK: shared UI ${timing_after}s after supervisor frontend fallback (${outcome})" >&2
          return 0
        fi
      fi
    fi
  done
  echo "CHROME_E2E_HEAL_FAIL: shared UI still unhealthy after frontend-only ensure (2 attempts)" >&2
  return 1
}
