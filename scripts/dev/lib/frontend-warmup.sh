#!/usr/bin/env bash
# Frontend compile warmth gate — SSOT for "GET / is hot" (not just port LISTEN or one-off HTTP 200).
# Sourced by dev-stack.sh; do not execute directly.
set -euo pipefail

FRONTEND_WARM_STREAK="${MYRM_FRONTEND_WARM_STREAK:-2}"
FRONTEND_WARM_MAX_SEC="${MYRM_FRONTEND_WARM_MAX_SEC:-180}"
FRONTEND_WARM_FAST_SEC="${MYRM_FRONTEND_WARM_FAST_SEC:-2}"

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
if data.get('source_fingerprint') != '${source_fingerprint}':
    sys.exit(1)
if data.get('client_hot') is not True:
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
    echo "STACK_FAIL: client_hot missing during attach — first Agent must finish ./myrm ready --chrome" >&2
    return 1
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
  echo "STACK_WAIT: frontend client hydration via CDP (up to ${MYRM_CLIENT_WARMUP_TIMEOUT_SEC:-120}s)..." >&2
  if ! "${py}" "${warmup_py}" \
    --cdp-port "${cdp_port}" \
    --url "${APP_URL}/" \
    --timeout-sec "${MYRM_CLIENT_WARMUP_TIMEOUT_SEC:-120}"; then
    echo "STACK_FAIL: frontend client_hot warmup failed — check E2E Chrome :${cdp_port}" >&2
    return 1
  fi

  _frontend_save_client_warmth
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

_frontend_compile_hot_status() {
  if ! _frontend_port_listening; then
    echo "down"
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
