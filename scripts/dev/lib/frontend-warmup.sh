#!/usr/bin/env bash
# Frontend compile warmth gate — SSOT for "GET / is hot" (not just port LISTEN or one-off HTTP 200).
# Sourced by dev-stack.sh; do not execute directly.
set -euo pipefail

FRONTEND_WARM_STREAK="${MYRM_FRONTEND_WARM_STREAK:-2}"
FRONTEND_WARM_MAX_SEC="${MYRM_FRONTEND_WARM_MAX_SEC:-180}"
FRONTEND_WARM_FAST_SEC="${MYRM_FRONTEND_WARM_FAST_SEC:-2}"

_frontend_warmup_state_file() {
  echo "${STATE_DIR}/frontend-warmth.json"
}

_frontend_lock_generation() {
  if [[ ! -f "${FRONTEND_LOCK}" ]]; then
    echo ""
    return 0
  fi
  local bundler_stamp="${FRONTEND_DIR}/.next/dev-bundler-mode"
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

_frontend_warmth_recorded() {
  local state_file gen
  state_file="$(_frontend_warmup_state_file)"
  gen="$(_frontend_lock_generation)"
  [[ -n "${gen}" ]] || return 1
  [[ -f "${state_file}" ]] || return 1
  python3 -c "
import json, sys
from pathlib import Path
state = Path('${state_file}')
if not state.is_file():
    sys.exit(1)
data = json.loads(state.read_text())
if data.get('generation') != '${gen}':
    sys.exit(1)
sys.exit(0)
" 2>/dev/null
}

_frontend_save_warmth() {
  local state_file gen
  state_file="$(_frontend_warmup_state_file)"
  gen="$(_frontend_lock_generation)"
  [[ -n "${gen}" ]] || return 0
  mkdir -p "${STATE_DIR}"
  python3 -c "
import json, datetime
from pathlib import Path
payload = {
    'generation': '${gen}',
    'warmed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'url': '${APP_URL}/',
}
Path('${state_file}').write_text(json.dumps(payload, indent=2) + '\n')
"
}

_frontend_clear_warmth() {
  local state_file
  state_file="$(_frontend_warmup_state_file)"
  rm -f "${state_file}" 2>/dev/null || true
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
    echo "STACK_OK: frontend compile_hot (cached warmth)"
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
          echo "STACK_OK: frontend compile_hot (${timing}s x${FRONTEND_WARM_STREAK})"
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

  echo "STACK_FAIL: frontend compile_hot not reached within ${FRONTEND_WARM_MAX_SEC}s — check ${FRONTEND_LOG}" >&2
  return 1
}
