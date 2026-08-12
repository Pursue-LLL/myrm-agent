#!/usr/bin/env bash
# Chrome MCP E2E preflight — dedicated Myrm E2E Chrome (:9333, zero Allow).
# Exit 0 prints CHROME_E2E_READY; exit 1 prints actionable failures.
set -euo pipefail

PREFLIGHT_STARTED_SECONDS=${SECONDS}

_preflight_progress() {
  local phase="$1"
  echo "CHROME_E2E_PROGRESS: phase=${phase} elapsed_sec=$((SECONDS - PREFLIGHT_STARTED_SECONDS))" >&2
}

# Ensure toolchain bins (bun for model seed, node for orchestrator) are
# reachable even when the caller's shell lacks the standard Homebrew PATH
# (e.g. Cursor agent shells that never sourced .zshrc). Mirror the explicit
# candidate lookup used by ensure-browser-orchestrator.sh.
for _tool_dir in /opt/homebrew/bin /usr/local/bin /usr/bin "$HOME/.bun/bin"; do
  if [[ -d "${_tool_dir}" ]]; then
    case ":${PATH}:" in
      *":${_tool_dir}:"*) ;;
      *) PATH="${_tool_dir}:${PATH}" ;;
    esac
  fi
done
export PATH

UI_BASE="${E2E_UI_BASE:-http://127.0.0.1:3000}"
SHARED_API_BASE="${MYRM_SHARED_API_BASE:-http://127.0.0.1:8080}"
API_BASE="${E2E_API_BASE:-${SHARED_API_BASE}}"
MYRM_CHROME_E2E_ATTACH="${MYRM_CHROME_E2E_ATTACH:-0}"
export MYRM_CHROME_E2E_ATTACH
MYRM_MUX_ALLOW_TIMEOUT_RESTART="${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-1}"
export MYRM_MUX_ALLOW_TIMEOUT_RESTART
# R286: python -m e2e_bootstrap_deadline must share one holder key across subprocesses.
export MYRM_E2E_DEDUPE_HOLDER_PID="${MYRM_E2E_DEDUPE_HOLDER_PID:-$$}"
# R292: launch-force maintainer override must use fast attach path (solo PASS ~212s);
# without SKIP_ATTACH_WAIT, preflight burns 650s+ on signoff-stream hot-pool gate.
if [[ "${MYRM_E2E_LAUNCH_FORCE:-}" == "1" && "${MYRM_PREFLIGHT_SKIP_ATTACH_WAIT:-}" != "1" ]]; then
  export MYRM_PREFLIGHT_SKIP_ATTACH_WAIT=1
fi

_attach_api_base() {
  if [[ "${MYRM_E2E_EPOCH_PIN:-0}" == "1" && -n "${E2E_API_BASE:-}" ]]; then
    echo "${E2E_API_BASE}"
  else
    echo "${API_BASE}"
  fi
}

_epoch_pin_reseed_verify_api() {
  local new_api=""
  new_api="$(
    PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
      "${PREFLIGHT_PY}" -c "
import sys
from pathlib import Path
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from verify_backend_seed import ensure_verify_backend_seed
seed = ensure_verify_backend_seed(monorepo=Path('${MONOREPO_ROOT}'))
if not seed.ok:
    raise SystemExit(1)
print(seed.api_base.rstrip('/'))
" 2>/dev/null
  )" || return 1
  export E2E_API_BASE="${new_api}"
  echo "CHROME_E2E_ATTACH_HEAL: epoch pin verify-api reseeded api=${new_api}" >&2
  return 0
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=myrm-chrome-e2e-lib.sh
source "${SCRIPT_DIR}/myrm-chrome-e2e-lib.sh"

AGENT_ROOT="${MYRM_AGENT_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
export MYRM_DEV_STACK="${AGENT_ROOT}/scripts/dev/dev-stack.sh"
MONOREPO_ROOT="${MYRM_MONOREPO_ROOT:-$(cd "${AGENT_ROOT}/.." && pwd)}"
# shellcheck source=lib/dev_state_paths.sh
source "${SCRIPT_DIR}/lib/dev_state_paths.sh"
# Sandboxed HOME (e.g. Cursor's ~/.cursor2) would split mux state, warm shells and
# harness data across two homes. Run the whole preflight under the real user home so
# every $HOME-derived path (cdmcp-mux state, frontend caches) stays on one SSOT dir.
export_spawn_home
STATE_DIR="$(dev_state_dir)"
FRONTEND_DIR="${AGENT_ROOT}/myrm-agent-frontend"
export_myrm_next_dist_dir
FRONTEND_LOCK="$(resolve_frontend_lock_path "${FRONTEND_DIR}")"
FRONTEND_LOG="${STATE_DIR}/frontend.log"
APP_URL="${UI_BASE}"
FRONTEND_PORT="${MYRM_FRONTEND_PORT:-3000}"
# shellcheck source=lib/frontend-warmup.sh
source "${SCRIPT_DIR}/lib/frontend-warmup.sh"
# shellcheck source=lib/stack-epoch.sh
source "${SCRIPT_DIR}/lib/stack-epoch.sh"
# shellcheck source=lib/stack_mutation_policy.sh
source "${SCRIPT_DIR}/lib/stack_mutation_policy.sh"
MUX_BIN="${MONOREPO_ROOT}/scripts/dev/cdmcp-mux-autoconnect/bin/cdmcp-mux-autoconnect.mjs"
ENSURE_CHROME="${SCRIPT_DIR}/ensure-myrm-chrome-e2e.sh"
SERVER_DIR="${AGENT_ROOT}/myrm-agent-server"
PREFLIGHT_PY="${SERVER_DIR}/.venv/bin/python"
if [[ ! -x "${PREFLIGHT_PY}" ]]; then
  PREFLIGHT_PY="python3"
fi

_admit_poll_touch() {
  local node="$1"
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/e2e_admit_poll.py" touch --node "${node}" \
    2>/dev/null || true
}

_admit_poll_budget_or_fail() {
  local node="$1"
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/e2e_admit_poll.py" assert-budget --node "${node}"
}

_epoch_drift_shared_attach_cap_sec() {
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
import os
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_api_verify import epoch_drift_attach_cap_sec, resolve_e2e_api_context
if os.environ.get('MYRM_E2E_SHPOIB', '').strip() == '1':
    print(0)
    raise SystemExit(0)
if os.environ.get('MYRM_E2E_EPOCH_PIN', '').strip() == '1':
    print(0)
    raise SystemExit(0)
if os.environ.get('E2E_SIGNOFF', '').strip() == '1':
    print(0)
    raise SystemExit(0)
if os.environ.get('MYRM_E2E_LAUNCH_FORCE', '').strip() == '1':
    print(0)
    raise SystemExit(0)
try:
    ctx = resolve_e2e_api_context(retry_after_apply=False)
except Exception:
    print(0)
    raise SystemExit(0)
print(
    epoch_drift_attach_cap_sec(
        blocked=ctx.blocked,
        epoch_match=ctx.epoch_match,
        drift_pending=ctx.drift_pending,
        active_leases=ctx.active_leases,
    )
)
" 2>/dev/null || echo 0
}

_attach_health_require_args() {
  if [[ "${E2E_SIGNOFF:-}" == "1" ]]; then
    echo "--require-signoff-stream-ready"
    return 0
  fi
  local active_leases
  active_leases="$(_parallel_attach_active_leases)"
  # R150/R289: registry peer count can lag wave leases during parallel ADMIT.
  if [[ "${active_leases}" -le 0 && "${E2E_SIGNOFF:-}" != "1" ]]; then
    active_leases=1
  fi
  # R290: parallel attach with live UI/API — signoff-stream gate (no frontendEpoch SMP defer).
  if [[ "${active_leases}" -gt 0 ]] && _shared_stack_endpoints_ok; then
    echo "--require-signoff-stream-ready"
    return 0
  fi
  if [[ "${MYRM_E2E_LANE:-}" == "READ" && "${MYRM_E2E_SHARED_HOT:-0}" != "1" ]]; then
    echo "--require-read-attach-ready"
    return 0
  fi
  echo "--require-attach-ready"
}

_attach_wait_label() {
  if [[ "${MYRM_E2E_LANE:-}" == "READ" && "${MYRM_E2E_SHARED_HOT:-0}" != "1" ]]; then
    echo "READ stack-core attach"
    return 0
  fi
  echo "shared hot pool is recovering; read-only attach"
}

export MYRM_CHROME_E2E_DATA_DIR
export MYRM_CHROME_E2E_PORT
export CHROME_DATA_DIR="${MYRM_CHROME_E2E_DATA_DIR}"

SAVED_FRONTMOST_PID=""
if myrm_chrome_e2e_launch_background; then
  SAVED_FRONTMOST_PID="$(myrm_chrome_e2e_save_frontmost_pid)"
  export MYRM_CHROME_E2E_SAVED_FRONTMOST_PID="${SAVED_FRONTMOST_PID}"
fi

fail() {
  echo "CHROME_E2E_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "CHROME_E2E_OK: $*"
}

_maybe_seed_providers() {
  # R215 fix: the DONE flag is for the SHARED stack only. A private-backend
  # preflight (SHPOIB bootstrap) targets E2E_API_BASE=:<private port> and must
  # always seed, otherwise the fresh private backend inherits stale providers
  # (e.g. stale provider quota) and live E2E fails silently.
  if [[ "${MYRM_E2E_MODEL_SEED_DONE:-0}" == "1" ]] \
    && [[ "${MYRM_PRIVATE_BACKEND:-0}" != "1" ]] \
    && _shared_stack_endpoints_ok; then
    echo "CHROME_E2E_WARN: skip redundant model seed (R215; stack healthy)" >&2
    MYRM_E2E_MODEL_SEED_FAILED=0
    return 0
  fi
  MYRM_E2E_MODEL_SEED_FAILED=0
  if [[ -f "${SERVER_DIR}/.env.test" ]]; then
    if ! PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" "${PREFLIGHT_PY}" -c "
import sys
from pathlib import Path
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from env_test_shell_lint import assert_env_test_shell_safe
assert_env_test_shell_safe(Path('${SERVER_DIR}/.env.test'))
"; then
      echo "E2E_ENV_TEST_SHELL_UNSAFE: ${SERVER_DIR}/.env.test is not safe to source (S0)" >&2
      return 1
    fi
    set -a
    # shellcheck disable=SC1091
    source "${SERVER_DIR}/.env.test"
    set +a
  fi
  if [[ -n "${BASIC_MODEL:-}" && -n "${BASIC_API_KEY:-}" ]]; then
    local attempt max_attempts=5 seed_out="" seed_lock parallel_leases flock_wait_sec=120
    max_attempts="${MYRM_E2E_MODEL_SEED_RETRIES:-5}"
    seed_lock="${STATE_DIR}/chrome-e2e-model-seed.lock"
    parallel_leases="$(_parallel_attach_active_leases)"
    export MYRM_E2E_PARALLEL_ACTIVE_LEASES="${parallel_leases}"
    if [[ "${parallel_leases}" -gt 0 ]] && _shared_stack_endpoints_ok; then
      flock_wait_sec="${MYRM_E2E_MODEL_SEED_FLOCK_WAIT_SEC:-8}"
      max_attempts="${MYRM_E2E_MODEL_SEED_PARALLEL_RETRIES:-2}"
    fi
    for attempt in $(seq 1 "${max_attempts}"); do
      _admit_poll_touch "CHROME_E2E_MODEL_SEED"
      if seed_out="$(
        python3 - "${seed_lock}" "${flock_wait_sec}" "${SCRIPT_DIR}/chrome-e2e-model-seed.mjs" <<'PY'
import fcntl
import os
import subprocess
import sys
import time

lock_file = sys.argv[1]
wait_sec = float(sys.argv[2])
seed_script = sys.argv[3]
fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o644)
deadline = time.monotonic() + wait_sec
acquired = False
try:
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                sys.exit(1)
            time.sleep(0.25)
    proc = subprocess.run(
        ["bun", seed_script],
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    sys.exit(proc.returncode)
finally:
    if acquired:
        fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
PY
      )"; then
        echo "${seed_out}"
        ok "model seed"
        MYRM_E2E_MODEL_SEED_FAILED=0
        MYRM_E2E_MODEL_SEED_DONE=1
        return 0
      fi
      if [[ "${attempt}" -lt "${max_attempts}" ]]; then
        echo "CHROME_E2E_WARN: model seed attempt ${attempt}/${max_attempts} failed — retry in 2s: ${seed_out}" >&2
        sleep 2
      fi
    done
    if [[ "${MYRM_PRIVATE_BACKEND:-0}" != "1" ]] \
      && [[ "${MYRM_E2E_PRIVATE_BACKEND:-0}" != "1" ]] \
      && [[ "${parallel_leases}" -gt 0 ]] \
      && _shared_stack_endpoints_ok; then
      echo "CHROME_E2E_WARN: model seed non-fatal under parallel load (R214; shared stack healthy)" >&2
      MYRM_E2E_MODEL_SEED_FAILED=0
      MYRM_E2E_MODEL_SEED_DONE=1
      return 0
    fi
    echo "CHROME_E2E_WARN: model seed failed — ${seed_out}" >&2
    MYRM_E2E_MODEL_SEED_FAILED=1
    return 1
  fi
  echo "CHROME_E2E_WARN: skip model seed (set BASIC_MODEL and BASIC_API_KEY in .env.test)" >&2
  return 0
}

_seed_providers_for_runtime() {
  if [[ "${MYRM_PRIVATE_BACKEND:-0}" == "1" ]] \
    || [[ "${MYRM_E2E_PRIVATE_BACKEND:-0}" == "1" ]]; then
    # Attach-time PRIVATE seed targets a warm-pool backend that a short-lived
    # maintainer may have already released; a failure here only delays attach
    # and cannot cause a false product failure, because every PRIVATE item
    # re-seeds its own backend in the bootstrap preflight_seed phase, which
    # stays fail-closed below. Keep bootstrap-time (MYRM_E2E_API_ONLY=1) strict.
    if [[ "${MYRM_E2E_API_ONLY:-0}" != "1" ]]; then
      _maybe_seed_providers || true
      return 0
    fi
    # PRIVATE owns an isolated backend/database; allowing a failed seed to
    # pass would make the test observe stale provider state and report a
    # product failure unrelated to the requested scenario.
    _maybe_seed_providers
    return $?
  fi
  # SHARED attach remains non-blocking when another session already owns the
  # healthy deployed stack; its model seed is not a session admission gate.
  _maybe_seed_providers || true
}

_parallel_attach_active_leases() {
  local active_leases
  active_leases="$(_wave_active_lease_count "${MONOREPO_ROOT}")"
  [[ "${active_leases}" =~ ^[0-9]+$ ]] || active_leases=0
  if [[ "${active_leases}" -le 0 ]]; then
    active_leases="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_session_runtime.registry import list_live_e2e_sessions
print(len(list_live_e2e_sessions()))
" 2>/dev/null || echo 0)"
    [[ "${active_leases}" =~ ^[0-9]+$ ]] || active_leases=0
  fi
  echo "${active_leases}"
}

_bootstrap_attach_begin() {
  local active_leases="${1:-0}"
  [[ "${active_leases}" =~ ^[0-9]+$ ]] || active_leases=0
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -m e2e_bootstrap_deadline begin --active-leases "${active_leases}" >/dev/null
}

_bootstrap_attach_remaining_sec() {
  local remaining
  remaining="$(
    PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
      "${PREFLIGHT_PY}" -m e2e_bootstrap_deadline remaining 2>/dev/null || echo 0
  )"
  [[ "${remaining}" =~ ^[0-9]+$ ]] || remaining=0
  echo "${remaining}"
}

_wait_attach_endpoints_under_parallel_load() {
  local initial_errors="$1"
  [[ -n "${initial_errors}" ]] || return 0
  local active_leases wait_sec poll_sec waited errors heal_during_wait=0 ui_heal_during_wait=0
  active_leases="$(_parallel_attach_active_leases)"
  # R150: never fast-fail ui=unreachable when attach errors exist — wave lease count can lag registry under parallel ADMIT.
  # R200-C: signoff with true zero peers uses solo attach wait (no synthetic lease=1 → 660s ADMIT burn).
  if [[ "${active_leases}" -le 0 && "${E2E_SIGNOFF:-}" != "1" ]]; then
    active_leases=1
    echo "CHROME_E2E_ATTACH: registry peer count=0 — minimum parallel ADMIT attach wait (R150)" >&2
  fi

  _bootstrap_attach_begin "${active_leases}"
  local bootstrap_budget
  bootstrap_budget="$(_bootstrap_attach_remaining_sec)"
  wait_sec="${bootstrap_budget}"
  poll_sec="${MYRM_CHROME_E2E_ATTACH_POLL_SEC:-2}"
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  local wait_started=$SECONDS
  waited=0
  local ui_heal_cap=2 ui_heal_timeout_sec=60 ui_heal_post_ensure_max_sec=120 ui_heal_next_at=30 api_heal_next_at=30
  if [[ "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    ui_heal_cap=$((2 + active_leases / 3))
    if [[ "${ui_heal_cap}" -gt 6 ]]; then
      ui_heal_cap=6
    fi
    ui_heal_timeout_sec="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from dev_gate_contract import attach_ui_heal_timeout_sec
print(attach_ui_heal_timeout_sec(${active_leases}))
")"
    ui_heal_post_ensure_max_sec="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from dev_gate_contract import attach_ui_heal_post_ensure_max_sec
print(attach_ui_heal_post_ensure_max_sec(${active_leases}))
")"
    [[ "${ui_heal_timeout_sec}" =~ ^[0-9]+$ ]] || ui_heal_timeout_sec=300
    [[ "${ui_heal_post_ensure_max_sec}" =~ ^[0-9]+$ ]] || ui_heal_post_ensure_max_sec=120
  fi
  local attach_api
  attach_api="$(_attach_api_base)"
  local epoch_pin_reseed=0 epoch_pin_reseed_max=3
  while true; do
    waited=$((SECONDS - wait_started))
    errors="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from runtime_identity import attach_wait_errors
print(', '.join(attach_wait_errors('${UI_BASE}', '${attach_api}')))
")"
    [[ -z "${errors}" ]] && return 0
    wait_sec="$(_bootstrap_attach_remaining_sec)"
    if [[ "${wait_sec}" -le 0 ]]; then
      printf '%s\n' "${errors}" >&2
      if [[ "${errors}" == *"ui=half_dead"* ]]; then
        echo "E2E_ATTACH_UI_HALF_DEAD_QUEUE: attach ADMIT waited ${wait_sec}s — shared UI still half_dead; leases=${active_leases} (do not stop other pytest; pending heal when idle)" >&2
      fi
      return 1
    fi
    if [[ "${MYRM_E2E_EPOCH_PIN:-0}" == "1" ]] \
      && [[ "${errors}" == *"api=unreachable"* ]] \
      && [[ "${epoch_pin_reseed}" -lt "${epoch_pin_reseed_max}" ]]; then
      epoch_pin_reseed=$((epoch_pin_reseed + 1))
      if _epoch_pin_reseed_verify_api; then
        attach_api="$(_attach_api_base)"
        continue
      fi
    fi
    if [[ "${MYRM_E2E_EPOCH_PIN:-0}" == "1" ]] \
      && [[ "${attach_api}" != "${SHARED_API_BASE}" ]] \
      && [[ "${errors}" == *"api=unreachable"* ]] \
      && curl -sf --max-time 5 "${SHARED_API_BASE%/}/api/v1/health" >/dev/null 2>&1; then
      echo "CHROME_E2E_ATTACH: epoch pin shared fallback during ADMIT wait api=${SHARED_API_BASE} (isolated ${attach_api} unreachable)" >&2
      unset MYRM_E2E_EPOCH_PIN
      export E2E_API_BASE="${SHARED_API_BASE}"
      attach_api="${SHARED_API_BASE}"
      continue
    fi
    if [[ "${MYRM_PRIVATE_BACKEND:-}" != "1" ]] \
      && [[ "${MYRM_E2E_EPOCH_PIN:-0}" != "1" ]] \
      && [[ "${errors}" == *"api=unreachable"* ]] \
      && [[ "${waited}" -ge "${api_heal_next_at}" ]] \
      && [[ "${heal_during_wait}" -lt 2 ]] \
      && [[ -f "${SCRIPT_DIR}/dev-stack.sh" ]]; then
      heal_during_wait=$((heal_during_wait + 1))
      api_heal_next_at=$((api_heal_next_at + 30))
      echo "CHROME_E2E_ATTACH_HEAL: api unreachable during attach wait — retry crash heal ${heal_during_wait}/2" >&2
      if _smp_attach_backend_crash_heal "${MONOREPO_ROOT}" "${SCRIPT_DIR}/dev-stack.sh"; then
        continue
      fi
    fi
    if [[ "${errors}" == *"ui=half_dead"* || "${errors}" == *"ui=unreachable"* ]] \
      && "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from warm_shell_registry import platform_shell_fresh
raise SystemExit(0 if platform_shell_fresh(route_path='/') else 1)
" 2>/dev/null; then
      echo "CHROME_E2E_ATTACH: epoch warm shell fresh — skip per-lane ui heal (§19.11 TAB-6b)" >&2
      _admit_poll_touch "CHROME_E2E_ATTACH_WARM_SHELL_FRESH"
      _admit_poll_budget_or_fail "CHROME_E2E_ATTACH_WARM_SHELL_FRESH" || return $?
      sleep "${poll_sec}"
      continue
    fi
    if [[ "${errors}" == *"ui=half_dead"* || "${errors}" == *"ui=unreachable"* ]] \
      && [[ "${waited}" -ge "${ui_heal_next_at}" ]] \
      && [[ "${ui_heal_during_wait:-0}" -lt "${ui_heal_cap}" ]]; then
      ui_heal_during_wait=$((ui_heal_during_wait + 1))
      ui_heal_next_at=$((ui_heal_next_at + 30))
      echo "CHROME_E2E_ATTACH_HEAL: ui half_dead during attach queue — bounded frontend heal ${ui_heal_during_wait}/${ui_heal_cap} (do not stop other pytest)" >&2
      if command -v timeout >/dev/null 2>&1; then
        timeout "${ui_heal_timeout_sec}" env \
          SCRIPT_DIR="${SCRIPT_DIR}" UI_BASE="${UI_BASE}" FRONTEND_PORT="${FRONTEND_PORT}" \
          MYRM_DEV_STACK="${MYRM_DEV_STACK}" MYRM_DEV_STATE_DIR="${STATE_DIR}" \
          MYRM_FRONTEND_DIR="${FRONTEND_DIR}" \
          MYRM_UI_HEAL_POST_ENSURE_MAX_SEC="${ui_heal_post_ensure_max_sec}" \
          MYRM_STACK_FRONTEND_WAIT_SEC="${MYRM_STACK_FRONTEND_WAIT_SEC:-360}" \
          bash "${SCRIPT_DIR}/lib/frontend-warmup-heal-entry.sh" || true
      else
        _heal_shared_ui_if_stale || true
      fi
      continue
    fi
    if [[ "${waited}" -eq 0 || $((waited % 10)) -eq 0 ]]; then
      echo "CHROME_E2E_WAIT: parallel attach waiting for ${errors} (${active_leases} active leases) ${waited}s remaining=${wait_sec}s (monotonic BOOTSTRAP)" >&2
    fi
    _admit_poll_touch "CHROME_E2E_ATTACH_ENDPOINT_WAIT"
    _admit_poll_budget_or_fail "CHROME_E2E_ATTACH_ENDPOINT_WAIT" || return $?
    sleep "${poll_sec}"
  done
}

_attach_parallel_wait_sec() {
  local base="${MYRM_CHROME_E2E_ATTACH_WAIT_SEC:-360}"
  local active_leases scaled
  active_leases="$(_parallel_attach_active_leases)"
  [[ "${base}" =~ ^[0-9]+$ ]] || base=360
  [[ "${active_leases}" =~ ^[0-9]+$ ]] || active_leases=0
  scaled="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from dev_gate_contract import attach_parallel_wait_sec
print(attach_parallel_wait_sec(${active_leases}, base=${base}))
")"
  [[ "${scaled}" =~ ^[0-9]+$ ]] || scaled="${base}"
  if [[ "${active_leases}" -gt 0 ]]; then
    echo "CHROME_E2E_ATTACH: parallel ADMIT scaled wait ≤${scaled}s (R161; leases=${active_leases}; do not stop other pytest)" >&2
  fi
  echo "${scaled}"
}

_attach_epoch_pin_drop_stale_when_shared_aligned() {
  # R280: test.sh may pin a verify-api port before shared :8080 heals; drop stale pin when aligned.
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_api_verify import resolve_e2e_api_context
from epoch_delivery_plane import needs_epoch_pin_backend
ctx = resolve_e2e_api_context(retry_after_apply=False)
raise SystemExit(0 if not needs_epoch_pin_backend(ctx) else 1)
" 2>/dev/null
}

_attach_epoch_pin_fast_path() {
  # P0-DGR-6: pinned verify-api must not wait monotonic shared-hot BOOTSTRAP (578s+).
  if [[ "${MYRM_E2E_EPOCH_PIN:-0}" != "1" ]]; then
    return 1
  fi
  if _attach_epoch_pin_drop_stale_when_shared_aligned; then
    echo "CHROME_E2E_ATTACH: shared epoch aligned — drop stale epoch pin api=${API_BASE}" >&2
    unset MYRM_E2E_EPOCH_PIN
    export E2E_API_BASE="${API_BASE}"
    return 1
  fi
  local runtime_py="${SCRIPT_DIR}/lib/runtime_identity.py"
  local pin_api="${E2E_API_BASE:-${API_BASE}}"
  local health="" waited=0 poll_sec wait_sec
  poll_sec="${MYRM_CHROME_E2E_ATTACH_POLL_SEC:-2}"
  wait_sec="${MYRM_E2E_EPOCH_PIN_ATTACH_WAIT_SEC:-90}"
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  [[ "${wait_sec}" =~ ^[0-9]+$ && "${wait_sec}" -gt 0 ]] || wait_sec=90
  echo "CHROME_E2E_ATTACH: epoch pin fast path api=${pin_api} wait≤${wait_sec}s (skip shared-hot monotonic BOOTSTRAP)" >&2
  while [[ "${waited}" -lt "${wait_sec}" ]]; do
    if _attach_epoch_pin_drop_stale_when_shared_aligned; then
      echo "CHROME_E2E_ATTACH: shared epoch aligned during pin wait — drop stale epoch pin api=${API_BASE}" >&2
      unset MYRM_E2E_EPOCH_PIN
      export E2E_API_BASE="${API_BASE}"
      return 1
    fi
    if [[ "${pin_api}" != "${SHARED_API_BASE}" ]] \
      && curl -sf --max-time 5 "${SHARED_API_BASE%/}/api/v1/health" >/dev/null 2>&1; then
      echo "CHROME_E2E_ATTACH: epoch pin early fallback to shared api=${SHARED_API_BASE} (isolated ${pin_api} not ready)" >&2
      unset MYRM_E2E_EPOCH_PIN
      export E2E_API_BASE="${SHARED_API_BASE}"
      return 1
    fi
    if health="$("${PREFLIGHT_PY}" "${runtime_py}" \
      --auto-probe \
      --auto-hot \
      --ui "${UI_BASE}" \
      --api "${pin_api}" \
      --attach-mode \
      --require-read-attach-ready 2>&1)"; then
      echo "CHROME_E2E_READY ui=${UI_BASE} api=${pin_api} port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
      echo "${health}"
      return 0
    fi
    if [[ "${waited}" -eq 0 || $((waited % 10)) -eq 0 ]]; then
      echo "CHROME_E2E_WAIT: epoch pin attach ${waited}s remaining=$((wait_sec - waited))s" >&2
    fi
    _admit_poll_touch "CHROME_E2E_EPOCH_PIN_ATTACH"
    _admit_poll_budget_or_fail "CHROME_E2E_EPOCH_PIN_ATTACH" || return 1
    sleep "${poll_sec}"
    waited=$((waited + poll_sec))
  done
  echo "${health}" >&2
  # R277: isolated verify-api flaked under parallel attach — fall back to shared when healthy.
  if [[ "${pin_api}" != "${SHARED_API_BASE}" ]] \
    && curl -sf --max-time 5 "${SHARED_API_BASE%/}/api/v1/health" >/dev/null 2>&1; then
    echo "CHROME_E2E_ATTACH: epoch pin fallback to shared api=${SHARED_API_BASE} (isolated ${pin_api} not ready)" >&2
    unset MYRM_E2E_EPOCH_PIN
    export E2E_API_BASE="${SHARED_API_BASE}"
    return 1
  fi
  fail "epoch pin attach did not become ready within ${wait_sec}s — run ./myrm verify-api --ensure-backend"
}

_maybe_reseal_auth_template_after_attach() {
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_auth_provisioner import reseal_auth_template_for_current_runtime
from e2e_api_verify import workspace_backend_fingerprint
origin = '${UI_BASE:-http://127.0.0.1:3000}'
ws = workspace_backend_fingerprint()
status = reseal_auth_template_for_current_runtime(origin=origin, workspace_fingerprint=ws)
print(
    f'CHROME_E2E_AUTH_RESEAL: status={status[\"status\"]} '
    f'next={status[\"next_action\"]} runtime_fp={status.get(\"runtimeFingerprint\", \"\")}',
    flush=True,
)
" 2>/dev/null || true
}

_prepare_auth_template_before_attach() {
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_auth_provisioner import prepare_auth_template_for_attach
from e2e_api_verify import workspace_backend_fingerprint
origin = '${UI_BASE:-http://127.0.0.1:3000}'
status = prepare_auth_template_for_attach(
    origin=origin,
    workspace_fingerprint=workspace_backend_fingerprint(),
)
print(
    f'CHROME_E2E_AUTH_PREPARE: status={status[\"status\"]} '
    f'next={status[\"next_action\"]} runtime_fp={status.get(\"runtimeFingerprint\", \"\")}',
    flush=True,
)
if status['next_action'] not in {'READY', 'AUTH_SETUP_REQUIRED'}:
    raise SystemExit('AUTH_TEMPLATE_PREPARE_UNAVAILABLE')
" 2>/dev/null || fail "auth template preparation failed before attach"
}

_attach_fast_path() {
  if _attach_epoch_pin_fast_path; then
    return 0
  fi
  local runtime_py="${SCRIPT_DIR}/lib/runtime_identity.py"
  local health="" waited=0 ui_heal_during_wait=0 mux_heal_during_wait=0
  local wait_sec poll_sec active_leases errors require_ready
  # R291: launch-force + skip attach wait — match solo PASS (46138): dev servers + CDP verified
  # above; do not burn 590s hot-pool BOOTSTRAP (shellHot=false acceptable under attach).
  if [[ "${MYRM_E2E_LAUNCH_FORCE:-}" == "1" && "${MYRM_PREFLIGHT_SKIP_ATTACH_WAIT:-}" == "1" ]] \
    && myrm_chrome_e2e_cdp_healthy; then
    health="$("${PREFLIGHT_PY}" "${runtime_py}" \
      --auto-probe \
      --auto-hot \
      --ui "${UI_BASE}" \
      --api "${API_BASE}" \
      --attach-mode 2>&1)" || health=""
    echo "CHROME_E2E_ATTACH: launch-force fast path (CDP live; defer hot-pool gate)" >&2
    echo "CHROME_E2E_READY ui=${UI_BASE} api=${API_BASE} port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
    echo "${health}"
    _maybe_reseal_auth_template_after_attach
    return 0
  fi
  require_ready="$(_attach_health_require_args)"
  poll_sec="${MYRM_CHROME_E2E_ATTACH_POLL_SEC:-2}"
  active_leases="$(_parallel_attach_active_leases)"
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  _bootstrap_attach_begin "${active_leases}"
  wait_sec="$(_bootstrap_attach_remaining_sec)"
  if [[ "${require_ready}" == "--require-read-attach-ready" ]]; then
    echo "CHROME_E2E_ATTACH: READ lane stack-core attach uses monotonic BOOTSTRAP remaining=${wait_sec}s (no independent 150s gate)" >&2
  fi
  if [[ "${wait_sec}" -le 0 ]]; then
    fail "BOOTSTRAP attach budget exhausted before stack-core gate — do not stop other pytest; run ./myrm e2e-context"
  fi
  local wait_started=$SECONDS drift_cap=0
  drift_cap="$(_epoch_drift_shared_attach_cap_sec)"
  [[ "${drift_cap}" =~ ^[0-9]+$ ]] || drift_cap=0
  if [[ "${drift_cap}" -gt 0 ]]; then
    echo "CHROME_E2E_ATTACH: epoch drift SHARED attach cap=${drift_cap}s (parallel lease aware; monotonic BOOTSTRAP may be higher)" >&2
  fi
  _attach_drift_cap_exceeded() {
    [[ "${drift_cap}" -gt 0 ]] || return 1
    local admit_elapsed
    admit_elapsed="$(
      PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
        "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_session_runtime.lifecycle import elapsed_wall_sec
print(int(elapsed_wall_sec()))
" 2>/dev/null || echo 0
    )"
    [[ "${admit_elapsed}" =~ ^[0-9]+$ ]] || admit_elapsed=0
    [[ "${admit_elapsed}" -ge "${drift_cap}" || "${waited}" -ge "${drift_cap}" ]]
  }
  _attach_drift_cap_fail_msg() {
    if [[ "${active_leases}" -gt 0 ]]; then
      echo "epoch drift attach cap ${drift_cap}s exceeded (${active_leases} active leases defer shared reload) — keep this session; retry attach after leases drain; do not stop other pytest"
    else
      echo "epoch drift attach cap ${drift_cap}s exceeded with no active leases — run ./myrm verify-api --ensure-backend when wave idle; do not stop other pytest"
    fi
  }
  if _attach_drift_cap_exceeded; then
    echo "${health}" >&2
    fail "$(_attach_drift_cap_fail_msg)"
  fi
  while true; do
    wait_sec="$(_bootstrap_attach_remaining_sec)"
    if _attach_drift_cap_exceeded; then
      echo "${health}" >&2
      fail "$(_attach_drift_cap_fail_msg)"
    fi
    if [[ "${wait_sec}" -le 0 ]]; then
      echo "${health}" >&2
      fail "parallel attach health snapshot did not recover within monotonic BOOTSTRAP budget — wait for shared hot recovery; do not stop other pytest; solo warmup: ./myrm ready --chrome"
    fi
    if health="$("${PREFLIGHT_PY}" "${runtime_py}" \
      --auto-probe \
      --auto-hot \
      --ui "${UI_BASE}" \
      --api "${API_BASE}" \
      --attach-mode \
      "${require_ready}" 2>&1)"; then
      echo "CHROME_E2E_READY ui=${UI_BASE} api=${API_BASE} port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
      echo "${health}"
      _maybe_reseal_auth_template_after_attach
      return 0
    fi
    errors="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from runtime_identity import attach_endpoint_errors
print(', '.join(attach_endpoint_errors('${UI_BASE}', '${API_BASE}')))
")"
    if [[ "${errors}" == *"ui=half_dead"* || "${errors}" == *"ui=unreachable"* ]] \
      && [[ "${active_leases}" -le 0 ]] \
      && [[ "${waited}" -ge 30 ]] \
      && [[ $((waited % 30)) -eq 0 ]] \
      && [[ "${ui_heal_during_wait}" -lt 2 ]]; then
      ui_heal_during_wait=$((ui_heal_during_wait + 1))
      echo "CHROME_E2E_ATTACH_HEAL: ui stale during shared_hot wait — bounded frontend heal ${ui_heal_during_wait}/2 (R122)" >&2
      _heal_shared_ui_if_stale || true
      continue
    fi
    if [[ "${health}" == *"shellHot=false"* || "${health}" == *"clientHot=false"* ]] \
      && [[ "${require_ready}" == "--require-attach-ready" ]] \
      && [[ "${waited}" -ge 60 ]] \
      && [[ $((waited % 60)) -eq 0 ]] \
      && [[ "${mux_heal_during_wait}" -lt 2 ]]; then
      mux_heal_during_wait=$((mux_heal_during_wait + 1))
      echo "CHROME_E2E_ATTACH_HEAL: mux heal during shared_hot wait ${mux_heal_during_wait}/2 (R142)" >&2
      _heal_mux_request_timeout_drift || true
      _heal_mux_under_parallel_attach_load || true
      continue
    fi
    if [[ "${mux_heal_during_wait}" -lt 2 ]] \
      && [[ "${health}" == *"wsStampMatch=false"* ]] \
      && _mux_upstream_ready; then
      if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" && _mux_solo_gate_cluster_clear ]]; then
        mux_heal_during_wait=$((mux_heal_during_wait + 1))
        echo "CHROME_E2E_ATTACH_HEAL: solo ws restamp during attach wait ${mux_heal_during_wait}/2 (R255)" >&2
        _stamp_mux_ws_url || true
        _stamp_mux_daemon_ws_url || true
        continue
      fi
    fi
    wait_sec="$(_bootstrap_attach_remaining_sec)"
    if [[ "${waited}" -eq 0 || $((waited % 10)) -eq 0 ]]; then
      echo "CHROME_E2E_WAIT: $(_attach_wait_label) ${waited}s remaining=${wait_sec}s (leases=${active_leases}; monotonic BOOTSTRAP)" >&2
    fi
    _admit_poll_touch "CHROME_E2E_ATTACH_SHARED_HOT_WAIT"
    _admit_poll_budget_or_fail "CHROME_E2E_ATTACH_SHARED_HOT_WAIT" || return $?
    sleep "${poll_sec}"
    waited=$((SECONDS - wait_started))
  done
}

_wait_shared_ui_reachable() {
  local shared_ui="$1"
  local wait_sec="${MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC:-180}"
  local poll_sec="${MYRM_CHROME_E2E_SHARED_UI_POLL_SEC:-2}"
  [[ "${wait_sec}" =~ ^[0-9]+$ ]] || wait_sec=180
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  local waited=0
  while true; do
    if curl -sf --max-time 10 "${shared_ui}/" >/dev/null; then
      ok "shared UI ${shared_ui}"
      return 0
    fi
    if [[ "${waited}" -ge 30 && $((waited % 30)) -eq 0 ]]; then
      _heal_dead_shared_ui_port
    fi
    if [[ "${waited}" -ge "${wait_sec}" ]]; then
      fail "shared UI not reachable at ${shared_ui} within ${wait_sec}s — run: ./myrm ready --chrome"
    fi
    if [[ "${waited}" -eq 0 || $((waited % 10)) -eq 0 ]]; then
      echo "CHROME_E2E_WAIT: shared UI recovering ${waited}/${wait_sec}s (${shared_ui})" >&2
    fi
    _admit_poll_touch "CHROME_E2E_SHARED_UI_REACHABLE_WAIT"
    _admit_poll_budget_or_fail "CHROME_E2E_SHARED_UI_REACHABLE_WAIT" || return $?
    sleep "${poll_sec}"
    waited=$((waited + poll_sec))
  done
}

_heal_dead_shared_ui_port() {
  _heal_shared_ui_if_stale || true
}

_shared_stack_endpoints_ok() {
  local shared_ui="${E2E_UI_BASE:-${UI_BASE:-http://127.0.0.1:3000}}"
  curl -sf --max-time 10 "${shared_ui}/" >/dev/null \
    && curl -sf --max-time 10 "${SHARED_API_BASE}/api/v1/health" >/dev/null
}

_shared_stack_recovery_required() {
  local min_leases="${MYRM_E2E_SHARED_STACK_GATE_MIN_LEASES:-4}"
  local active_leases
  active_leases="$(_parallel_attach_active_leases)"
  [[ "${active_leases}" -ge "${min_leases}" ]] || return 1
  [[ "${MYRM_E2E_MODEL_SEED_FAILED:-0}" == "1" ]] && ! _shared_stack_endpoints_ok && return 0
  ! _shared_stack_endpoints_ok
}

_wait_shared_stack_healthy_before_ready() {
  _shared_stack_recovery_required || return 0
  local wait_sec poll_sec waited=0 wait_started=$SECONDS
  local active_leases ui_heal_during_wait=0 ui_heal_cap=2
  active_leases="$(_parallel_attach_active_leases)"
  wait_sec="$(_attach_parallel_wait_sec)"
  poll_sec="${MYRM_CHROME_E2E_SHARED_UI_POLL_SEC:-2}"
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  if [[ "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    ui_heal_cap=$((2 + active_leases / 3))
    if [[ "${ui_heal_cap}" -gt 6 ]]; then
      ui_heal_cap=6
    fi
  fi
  echo "CHROME_E2E_WAIT: shared stack recovery gate (leases=${active_leases}; seed_failed=${MYRM_E2E_MODEL_SEED_FAILED:-0})" >&2
  while true; do
    waited=$((SECONDS - wait_started))
    if _shared_stack_endpoints_ok; then
      if [[ "${MYRM_E2E_MODEL_SEED_FAILED:-0}" != "1" ]]; then
        ok "shared stack healthy before READY"
        return 0
      fi
      _maybe_seed_providers || true
      if [[ "${MYRM_E2E_MODEL_SEED_FAILED:-0}" != "1" ]]; then
        ok "shared stack healthy before READY (model seed recovered)"
        return 0
      fi
      # R214: idempotent seed may time out under parallel load while :3000/:8080 stay healthy.
      MYRM_E2E_MODEL_SEED_FAILED=0
      ok "shared stack healthy before READY (endpoints ok; parallel seed timeout non-fatal)"
      return 0
    fi
    if [[ "${waited}" -ge "${wait_sec}" ]]; then
      fail "shared stack not healthy within ${wait_sec}s (leases=${active_leases}; seed_failed=${MYRM_E2E_MODEL_SEED_FAILED:-0}) — do not stop other pytest; retry ADMIT or ./myrm ui-heal when idle"
    fi
    if [[ "${waited}" -ge 30 && $((waited % 30)) -eq 0 ]]; then
      echo "E2E_SHARED_STACK_RECOVERY_WAIT: shared :3000/:8080 or model seed not ready ${waited}/${wait_sec}s (leases=${active_leases}; do not stop other pytest)" >&2
      if [[ "${ui_heal_during_wait}" -lt "${ui_heal_cap}" ]]; then
        ui_heal_during_wait=$((ui_heal_during_wait + 1))
        _heal_shared_ui_if_stale || true
      fi
    fi
    _admit_poll_touch "E2E_SHARED_STACK_RECOVERY_WAIT"
    _admit_poll_budget_or_fail "E2E_SHARED_STACK_RECOVERY_WAIT" || return $?
    sleep "${poll_sec}"
  done
}

_private_backend_attach_path() {
  local shared_ui="${E2E_UI_BASE:-http://127.0.0.1:3000}"
  ok "private backend attach deferred (SHPOIB bootstrap will bind private pool)"
  _wait_shared_ui_reachable "${shared_ui}"
  _seed_providers_for_runtime
  _wait_shared_stack_healthy_before_ready || return $?
  myrm_chrome_e2e_cdp_healthy || fail "Myrm E2E Chrome CDP not reachable — run: ./myrm ready --chrome"
  ok "Myrm E2E Chrome port=${MYRM_CHROME_E2E_PORT}"
  local mux_pid_file="${CDMCP_MUX_STATE_DIR:-$(real_user_home)/.local/state/cdmcp-mux}/daemon.pid"
  if [[ -f "${mux_pid_file}" ]]; then
    local mux_pid
    mux_pid="$(tr -d '[:space:]' < "${mux_pid_file}")"
    if [[ -n "${mux_pid}" ]] && kill -0 "${mux_pid}" 2>/dev/null; then
      ok "cdmcp-mux daemon pid=${mux_pid}"
    fi
  fi
  echo "CHROME_E2E_READY ui=${shared_ui} api=${API_BASE} port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
}

_ensure_stack_epoch_file() {
  local epoch_file backend_pid
  epoch_file="$(_stack_epoch_file)"
  if [[ -f "${epoch_file}" ]]; then
    return 0
  fi
  if ! curl -sf --max-time 5 "${API_BASE}/api/v1/health" >/dev/null 2>&1; then
    return 0
  fi
  backend_pid=""
  backend_pid="$(read_backend_dev_pid 2>/dev/null || true)"
  _bump_stack_epoch "${backend_pid}" "${SERVER_DIR}" >/dev/null || true
}

# 0. API-only SHPOIB (signoff clarify pool / cron LIVE): seed private API only — never probe shared :3000.
if [[ "${MYRM_E2E_API_ONLY:-}" == "1" && "${MYRM_PRIVATE_BACKEND:-}" == "1" ]]; then
  curl -sf --max-time 10 "${API_BASE}/api/v1/health" >/dev/null \
    || fail "private backend not reachable at ${API_BASE}"
  _maybe_seed_providers
  ok "private backend api-only ${API_BASE}"
  echo "CHROME_E2E_READY ui=${UI_BASE} api=${API_BASE} api_only=1"
  exit 0
fi

_preflight_readiness_gate() {
  if [[ "${MYRM_E2E_LAUNCH_FORCE:-}" == "1" ]]; then
    return 0
  fi
  if [[ "${MYRM_E2E_LAUNCH_DECISION_PINNED:-}" == "1" ]]; then
    echo "CHROME_E2E_ADMISSION_PINNED: skip duplicate workspace readiness; continue health probes" >&2
    return 0
  fi
  local py_out rc=0
  py_out="$(
    PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
      "${PREFLIGHT_PY}" -m e2e_readiness emit 2>&1
  )" || rc=$?
  echo "${py_out}" >&2
  if [[ "${rc}" -eq 2 ]]; then
    fail "cluster readiness FAIL — run ./myrm e2e-context; do not stop other pytest"
  fi
}

# A dead shared backend must be healed before the unified readiness predicate:
# otherwise the predicate correctly reports BLOCKED and makes its own recovery
# path unreachable. The policy is backend-only + cross-process flock, so peers,
# frontend, Chrome, pages and ownership remain untouched.
if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]] \
  && [[ "${MYRM_PRIVATE_BACKEND:-}" != "1" ]] \
  && ! _smp_shared_api_http_ok \
  && [[ -f "${SCRIPT_DIR}/dev-stack.sh" ]]; then
  echo "CHROME_E2E_ATTACH_HEAL: pre-readiness shared api crash heal" >&2
  _smp_attach_backend_crash_heal "${MONOREPO_ROOT}" "${SCRIPT_DIR}/dev-stack.sh"
fi

_preflight_readiness_gate
_preflight_progress "readiness"

# Repair an existing runtime-mismatched template before isolated context attach;
# missing/expired templates remain an explicit setup requirement.
if [[ "${MYRM_E2E_API_ONLY:-}" != "1" ]]; then
  _prepare_auth_template_before_attach
fi

# 1. Dev servers (Next.js cold compile can exceed 3s)
# R202: mux-heal-only signoff must not block on attach endpoint wait + frontend dogpile.
if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" && "${MYRM_PREFLIGHT_SKIP_ATTACH_WAIT:-}" != "1" && "${MYRM_CHROME_E2E_MUX_HEAL_ONLY:-}" != "1" ]]; then
  _bootstrap_attach_begin "$(_parallel_attach_active_leases)"
  if [[ "${MYRM_E2E_EPOCH_PIN:-0}" == "1" ]] && _attach_epoch_pin_drop_stale_when_shared_aligned; then
    echo "CHROME_E2E_ATTACH: shared epoch aligned — drop stale epoch pin api=${API_BASE}" >&2
    unset MYRM_E2E_EPOCH_PIN
    export E2E_API_BASE="${API_BASE}"
  fi
  _attach_api="$(_attach_api_base)"
  if [[ "${MYRM_E2E_EPOCH_PIN:-0}" == "1" ]]; then
    echo "CHROME_E2E_ATTACH: epoch pin ADMIT wait uses api=${_attach_api} (skip shared :8080 unreachable gate)" >&2
  fi
  attach_errors="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from runtime_identity import attach_wait_errors
print(', '.join(attach_wait_errors('${UI_BASE}', '${_attach_api}')))
")"
  if [[ -n "${attach_errors}" && "${MYRM_E2E_EPOCH_PIN:-0}" == "1" && "${attach_errors}" == *"api=unreachable"* ]]; then
    _epoch_pin_reseed_verify_api && _attach_api="$(_attach_api_base)" || true
    if [[ "${_attach_api}" != "${SHARED_API_BASE}" ]] \
      && curl -sf --max-time 8 "${SHARED_API_BASE%/}/api/v1/health" >/dev/null 2>&1 \
      && curl -sf --max-time 8 "${UI_BASE}/" >/dev/null 2>&1; then
      echo "CHROME_E2E_ATTACH: epoch pin early fallback to shared api=${SHARED_API_BASE} (isolated ${_attach_api} unreachable)" >&2
      unset MYRM_E2E_EPOCH_PIN
      export E2E_API_BASE="${SHARED_API_BASE}"
      _attach_api="${SHARED_API_BASE}"
      attach_errors=""
    elif curl -sf --max-time 8 "${_attach_api%/}/api/v1/health" >/dev/null 2>&1 \
      && curl -sf --max-time 8 "${UI_BASE}/" >/dev/null 2>&1; then
      echo "CHROME_E2E_ATTACH: epoch pin fast ADMIT — pin api + UI reachable (skip BOOTSTRAP api wait)" >&2
      attach_errors=""
    fi
  fi
  if [[ -n "${attach_errors}" ]]; then
    if ! _wait_attach_endpoints_under_parallel_load "${attach_errors}"; then
      attach_msg="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from runtime_identity import format_attach_endpoint_failure
print(format_attach_endpoint_failure([p.strip() for p in '''${attach_errors}'''.split(',') if p.strip()]))
")"
      fail "${attach_msg} — first Agent must run: ./myrm ready --chrome"
    fi
  fi
elif [[ "${MYRM_CHROME_E2E_ATTACH}" != "1" && "${MYRM_MUX_FORCE_ATTACH_RESTART:-}" != "1" ]] \
  && ! curl -sf --max-time 30 "$UI_BASE" >/dev/null; then
  if [[ -f "${AGENT_ROOT}/scripts/dev/dev-stack.sh" ]]; then
    echo "CHROME_E2E_WARN: frontend down — attach or ensure via supervisor" >&2
    bash "${AGENT_ROOT}/scripts/dev/dev-stack.sh" attach \
      || bash "${AGENT_ROOT}/scripts/dev/dev-stack.sh" ensure \
      || true
  fi
  curl -sf --max-time 30 "$UI_BASE" >/dev/null || fail "Frontend not reachable at $UI_BASE — run: myrm start"
fi
if [[ "${MYRM_CHROME_E2E_ATTACH}" != "1" ]] && ! curl -sf --max-time 10 "$API_BASE/api/v1/health" >/dev/null; then
  if [[ -f "${AGENT_ROOT}/scripts/dev/dev-stack.sh" ]]; then
    echo "CHROME_E2E_WARN: backend down — attach or ensure via supervisor" >&2
    bash "${AGENT_ROOT}/scripts/dev/dev-stack.sh" attach \
      || bash "${AGENT_ROOT}/scripts/dev/dev-stack.sh" ensure \
      || true
  fi
  curl -sf --max-time 10 "$API_BASE/api/v1/health" >/dev/null || fail "Backend not reachable at $API_BASE — run: cd open-perplexity && ./myrm ready"
fi
ok "dev servers :${FRONTEND_PORT}/${MYRM_BACKEND_PORT:-8080}"
_preflight_progress "dev_servers"

# 1b. Shared-stack attach is read-only; private-backend pools seed into E2E_API_BASE.
if [[ "${MYRM_CHROME_E2E_ATTACH}" != "1" ]] || [[ "${MYRM_PRIVATE_BACKEND:-}" == "1" ]]; then
  _seed_providers_for_runtime
  _wait_shared_stack_healthy_before_ready || exit $?
fi

# 1c. API-only private backend (cron policy LIVE): no Chrome/CDP/mux required.
if [[ "${MYRM_E2E_API_ONLY:-}" == "1" && "${MYRM_PRIVATE_BACKEND:-}" == "1" ]]; then
  curl -sf --max-time 10 "${API_BASE}/api/v1/health" >/dev/null \
    || fail "private backend not reachable at ${API_BASE}"
  ok "private backend api-only ${API_BASE}"
  echo "CHROME_E2E_READY ui=${UI_BASE} api=${API_BASE} api_only=1"
  exit 0
fi

# 2. Legacy second Chrome / debug launchers (attach reuses :9333 SSOT — skip under parallel E2E)
if [[ "${MYRM_CHROME_E2E_ATTACH:-}" != "1" ]] && pgrep -lf 'MyrmChromeMcp' >/dev/null 2>&1; then
  fail "MyrmChromeMcp Chrome detected — quit it; use ./myrm ready --chrome (Myrm E2E profile on :9333)"
fi

# 3. Ensure dedicated E2E Chrome (no Allow — launched with --remote-debugging-port)
[[ -f "${ENSURE_CHROME}" ]] || fail "Missing ${ENSURE_CHROME}"

_ensure_browser_pool_chrome() {
  local port="$1"
  local data_dir ensure_one_out=""
  data_dir="$("${PREFLIGHT_PY}" -c "
import os, sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_browser_pool import resolve_chrome_data_dir
print(resolve_chrome_data_dir())
")"
  export MYRM_CHROME_E2E_PORT="${port}"
  export MYRM_CHROME_E2E_DATA_DIR="${data_dir}"
  export CHROME_DATA_DIR="${data_dir}"
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
    if myrm_chrome_e2e_cdp_healthy; then
      ensure_one_out="MYRM_CHROME_E2E_ATTACH: existing CDP port=${port}"
    else
      echo "CHROME_E2E_ATTACH_HEAL: shared Chrome/CDP collapsed — recover exact :${port} namespace without waiting for peers" >&2
      if ! ensure_one_out="$(bash "${ENSURE_CHROME}" 2>&1)"; then
        echo "${ensure_one_out}" >&2
        fail "Myrm E2E Chrome crash recovery failed on port ${port}"
      fi
      ensure_one_out+=$'\n'"CHROME_E2E_CDP_RECOVERED: port=${port}"
    fi
  elif ! ensure_one_out="$(bash "${ENSURE_CHROME}" 2>&1)"; then
    echo "${ensure_one_out}" >&2
    fail "Myrm E2E Chrome failed to start on port ${port} — see MYRM_CHROME_E2E_FAIL above"
  fi
  echo "${ensure_one_out}"
  ok "Myrm E2E Chrome port=${port} profile=${data_dir}"
}

ensure_out=""
ensure_out="$(_ensure_browser_pool_chrome "${MYRM_CHROME_E2E_PORT:-9333}")"
echo "${ensure_out}"
_preflight_progress "chrome_cdp"
if [[ "${ensure_out}" == *"CHROME_E2E_CDP_RECOVERED:"* ]]; then
  export MYRM_CHROME_E2E_CDP_RECOVERED=1
fi
CHROME_E2E_CLI_EARLY="${SCRIPT_DIR}/chrome-e2e/cli.sh"
if [[ -f "${CHROME_E2E_CLI_EARLY}" ]]; then
  bash "${CHROME_E2E_CLI_EARLY}" ensure-surface >/dev/null 2>&1 || true
fi

# G4/R271: heuristic blank prune removed — idle hygiene via coordinator reap (SSOT §18.7.2).

ACTIVE_PORT_FILE="${MYRM_CHROME_E2E_ACTIVE_PORT_FILE}"

# 4. mux daemon (parallel Agent tabs) — socket anchored on the fixed real-home
# state dir (not TMPDIR): the daemon may be started by a sibling process with a
# different TMPDIR, which would silently split the daemon/probe pair.
MUX_STATE_DIR="${CDMCP_MUX_STATE_DIR:-$(real_user_home)/.local/state/cdmcp-mux}"
MUX_REQUEST_TIMEOUT_MS="${CDMCP_MUX_REQUEST_TIMEOUT_MS:-180000}"
export CDMCP_MUX_REQUEST_TIMEOUT_MS="${MUX_REQUEST_TIMEOUT_MS}"
MUX_TIMEOUT_STAMP="${MUX_STATE_DIR}/request-timeout-ms"
MUX_DAEMON_TIMEOUT_STAMP="${MUX_STATE_DIR}/request-timeout-ms-at-daemon-start"
MUX_PID_FILE="${MUX_STATE_DIR}/daemon.pid"
MUX_LOG_FILE="${MUX_STATE_DIR}/mux.log"
MUX_START_LOCK_DIR="${MUX_STATE_DIR}/daemon.start.lock"
MUX_SOCKET="${CDMCP_MUX_SOCKET:-${MUX_STATE_DIR}/cdmcp-mux.sock}"
MUX_USING=0
if [[ -f "${MUX_PID_FILE}" ]]; then
  MUX_USING=1
fi

_mux_owned_pids() {
  if [[ -f "${MUX_PID_FILE}" ]]; then
    local pid
    pid="$(tr -d '[:space:]' <"${MUX_PID_FILE}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      # daemon.pid is the ownership SSOT; stale extra FDs on the same socket
      # must not be counted as additional owned daemons.
      echo "${pid}"
      return 0
    fi
  fi
  if command -v lsof >/dev/null 2>&1 && [[ -S "${MUX_SOCKET}" ]]; then
    lsof -t -- "${MUX_SOCKET}" 2>/dev/null || true
  fi
}

_mux_daemon_count() {
  _mux_owned_pids | sort -u | sed '/^$/d' | wc -l | tr -d '[:space:]'
}

_kill_owned_mux_daemon() {
  local pids pid
  pids="$(_mux_owned_pids | sort -u | tr '\n' ' ')"
  if [[ -n "${pids// }" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    for _ in $(seq 1 20); do
      [[ "$(_mux_daemon_count)" == "0" ]] && break
      sleep 0.1
    done
    while IFS= read -r pid; do
      [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && kill -9 "${pid}" 2>/dev/null || true
    done < <(_mux_owned_pids | sort -u)
  fi
  [[ "$(_mux_daemon_count)" == "0" ]] && rm -f "${MUX_PID_FILE}"
}

_stop_mux_daemon() {
  _kill_owned_mux_daemon
}

_start_mux_daemon() {
  mkdir -p "${MUX_STATE_DIR}"
  if ! mkdir "${MUX_START_LOCK_DIR}" 2>/dev/null; then
    if [[ "$(_mux_daemon_count)" != "0" ]]; then
      return 0
    fi
    rmdir "${MUX_START_LOCK_DIR}" 2>/dev/null || true
    mkdir "${MUX_START_LOCK_DIR}" 2>/dev/null || return 0
  fi
  # The preflight shell exits immediately after readiness. Detached stdio is
  # required so the shared mux survives that shell and remains available to
  # every later Chrome DevTools MCP client.
  nohup env \
    CHROME_DATA_DIR="${MYRM_CHROME_E2E_DATA_DIR}" \
    MYRM_CHROME_E2E_DATA_DIR="${MYRM_CHROME_E2E_DATA_DIR}" \
    MYRM_CHROME_E2E_PORT="${MYRM_CHROME_E2E_PORT}" \
    CDMCP_MUX_STATE_DIR="${MUX_STATE_DIR}" \
    CDMCP_MUX_SOCKET="${MUX_SOCKET}" \
    CDMCP_MUX_REQUEST_TIMEOUT_MS="${MUX_REQUEST_TIMEOUT_MS}" \
    MCP_MUX_UPSTREAM_STDERR="${MCP_MUX_UPSTREAM_STDERR:-1}" \
    node "${MUX_BIN}" daemon \
    >>"${MUX_LOG_FILE}" 2>&1 < /dev/null &
  local i
  for i in $(seq 1 15); do
    if [[ -f "${MUX_PID_FILE}" ]] && kill -0 "$(tr -d '[:space:]' < "${MUX_PID_FILE}")" 2>/dev/null; then
      mkdir -p "${MUX_STATE_DIR}"
      _stamp_mux_request_timeout
      _stamp_mux_daemon_request_timeout
      _stamp_mux_daemon_ws_url || true
      rmdir "${MUX_START_LOCK_DIR}" 2>/dev/null || true
      return 0
    fi
    sleep 1
  done
  rmdir "${MUX_START_LOCK_DIR}" 2>/dev/null || true
}

MUX_WS_STAMP="${MUX_STATE_DIR}/upstream-ws-url"
MUX_DAEMON_WS_STAMP="${MUX_STATE_DIR}/upstream-ws-url-at-daemon-start"

_current_cdp_ws_url() {
  MYRM_CHROME_E2E_PORT="${MYRM_CHROME_E2E_PORT}" "${PREFLIGHT_PY}" - <<'PY'
import json
import os
import urllib.request

port = os.environ.get("MYRM_CHROME_E2E_PORT", "9333")
with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as resp:
    data = json.load(resp)
ws = data.get("webSocketDebuggerUrl")
if not isinstance(ws, str) or not ws.startswith("ws://"):
    raise SystemExit("missing webSocketDebuggerUrl")
print(ws)
PY
}

_mux_ws_stamp_matches() {
  [[ -f "${MUX_WS_STAMP}" ]] || return 1
  local current stored
  current="$(_current_cdp_ws_url 2>/dev/null)" || return 1
  stored="$(tr -d '[:space:]' < "${MUX_WS_STAMP}")"
  [[ -n "${stored}" && "${current}" == "${stored}" ]]
}

_stamp_mux_ws_url() {
  local current
  current="$(_current_cdp_ws_url)" || return 1
  mkdir -p "${MUX_STATE_DIR}"
  printf '%s\n' "${current}" >"${MUX_WS_STAMP}"
}

_stamp_mux_daemon_ws_url() {
  local current
  current="$(_current_cdp_ws_url 2>/dev/null)" || return 1
  mkdir -p "${MUX_STATE_DIR}"
  printf '%s\n' "${current}" >"${MUX_DAEMON_WS_STAMP}"
}

_mux_daemon_ws_matches() {
  [[ -f "${MUX_DAEMON_WS_STAMP}" ]] || return 1
  local current stored
  current="$(_current_cdp_ws_url 2>/dev/null)" || return 1
  stored="$(tr -d '[:space:]' < "${MUX_DAEMON_WS_STAMP}")"
  [[ -n "${stored}" && "${current}" == "${stored}" ]]
}

_mux_upstream_ready() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  [[ -f "${MUX_BIN}" ]] || return 1
  local status_json ready
  status_json="$(node "${MUX_BIN}" status 2>/dev/null)" || return 1
  ready="$("${PREFLIGHT_PY}" -c "
import json, sys
try:
    d = json.loads(sys.argv[1])
    print('1' if d.get('upstreamReady') else '0')
except Exception:
    print('0')
" "${status_json}" 2>/dev/null)" || ready=0
  [[ "${ready}" == "1" ]]
}

_mux_context_count() {
  local status_json
  status_json="$(node "${MUX_BIN}" status 2>/dev/null)" || return 1
  "${PREFLIGHT_PY}" -c "
import json, sys
data = json.loads(sys.argv[1])
contexts = data.get('contexts')
print(len(contexts) if isinstance(contexts, list) else 0)
" "${status_json}"
}

_mux_attach_timeout_restart_allowed() {
  [[ "${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-}" == "1" ]] || return 1
  [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]] || return 1
  _mux_parallel_load_blocks_global_restart && return 1
  _mux_upstream_ready && _mux_ws_stamp_matches
}

_mux_parallel_load_blocks_global_restart() {
  # P0-A: fail-closed — if detection fails (non-numeric), block restart to protect peers
  local contexts active_leases
  contexts="$(_mux_context_count 2>/dev/null || echo unknown)"
  [[ ! "${contexts}" =~ ^[0-9]+$ ]] && return 0
  [[ "${contexts}" -gt 0 ]] && return 0
  active_leases="$(_mux_parallel_active_leases 2>/dev/null || echo unknown)"
  [[ ! "${active_leases}" =~ ^[0-9]+$ ]] && return 0
  [[ "${active_leases}" -gt 0 ]] && return 0
  return 1
}

_mux_solo_gate_cluster_clear() {
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
from mux_load import solo_gate_cluster_clear
import sys
sys.exit(0 if solo_gate_cluster_clear() else 1)
" 2>/dev/null
}

_mux_ws_restamp_solo_heal() {
  local label="$1"
  echo "CHROME_E2E_SOLO_WS_RESTAMP: ${label}" >&2
  _stamp_mux_ws_url || return 1
  _stamp_mux_daemon_ws_url || true
  if _mux_ws_stamp_matches && _mux_daemon_ws_matches && _mux_upstream_ready; then
    ok "cdmcp-mux solo ws restamp (${label})"
    return 0
  fi
  return 1
}

_mux_restart_allowed() {
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
    if [[ "${MYRM_E2E_P0A_GATE:-}" == "1" ]] && _mux_solo_gate_cluster_clear; then
      :
    else
      return 1
    fi
  fi
  _mux_parallel_load_blocks_global_restart && return 1
  if [[ "${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-}" == "1" ]]; then
    return 0
  fi
  bash "${SCRIPT_DIR}/wave.sh" check-stack-write >/dev/null 2>&1
}

_mux_timeout_restart_allowed() {
  [[ "${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-}" == "1" ]] || return 1
  _mux_parallel_load_blocks_global_restart && return 1
  bash "${SCRIPT_DIR}/wave.sh" check-stack-write >/dev/null 2>&1
}

_wait_mux_upstream_self_heal() {
  local i
  for i in $(seq 1 "${MYRM_MUX_SELF_HEAL_WAIT_SEC:-15}"); do
    if _mux_upstream_ready; then
      return 0
    fi
    sleep 1
  done
  return 1
}

_restart_mux_safely() {
  local reason="$1"
  local allowed=0
  if _mux_restart_allowed; then
    allowed=1
  elif [[ "${reason}" == *"timeout"* ]] && _mux_timeout_restart_allowed; then
    allowed=1
  elif [[ "${reason}" == *"timeout"* ]] && _mux_attach_timeout_restart_allowed; then
    allowed=1
  fi
  if [[ "${allowed}" -eq 0 ]]; then
    local contexts="unknown"
    contexts="$(_mux_context_count 2>/dev/null || echo unknown)"
    fail "mux restart blocked (${reason}); contexts=${contexts}, attach=${MYRM_CHROME_E2E_ATTACH}, or Wave pins runtime"
  fi
  echo "CHROME_E2E_WARN: restarting owned mux namespace (${reason})" >&2
  _stop_mux_daemon
  _start_mux_daemon
}

_ensure_mux_upstream() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  if _mux_ws_stamp_matches && _mux_daemon_ws_matches && _mux_upstream_ready; then
    return 0
  fi
  # R255: solo gate/signoff — restamp CDP ws drift before attach fail-closed or blocked restart.
  if ! _mux_ws_stamp_matches && _mux_upstream_ready && _mux_solo_gate_cluster_clear; then
    if [[ "${E2E_SIGNOFF:-}" == "1" || "${MYRM_E2E_P0A_GATE:-}" == "1" ]]; then
      _mux_ws_restamp_solo_heal "signoff-or-p0a-gate upstreamReady" && return 0
    fi
    if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
      _mux_ws_restamp_solo_heal "attach solo cluster ws drift" && return 0
    fi
  fi
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
    fail "mux not ready for parallel attach (upstreamReady or CDP ws drift) — first Agent must run: ./myrm ready --chrome"
  fi
  if _mux_ws_stamp_matches; then
    echo "CHROME_E2E_WAIT: mux upstreamReady=false — waiting for daemon self-heal" >&2
    if _wait_mux_upstream_self_heal; then
      ok "cdmcp-mux upstream self-healed without daemon restart"
      return 0
    fi
    _restart_mux_safely "upstream self-heal timeout"
  else
    echo "CHROME_E2E_WARN: Chrome CDP WebSocket drifted — daemon options require a new endpoint" >&2
    # R94/R255: signoff or solo gate — restamp ws without restart when cluster is solo-clear.
    if _mux_upstream_ready \
      && { [[ "${E2E_SIGNOFF:-}" == "1" ]] || [[ "${MYRM_E2E_P0A_GATE:-}" == "1" ]]; } \
      && _mux_solo_gate_cluster_clear; then
      _mux_ws_restamp_solo_heal "solo cluster upstreamReady" && return 0
    fi
    if [[ "${E2E_SIGNOFF:-}" == "1" ]] && _mux_upstream_ready; then
      echo "CHROME_E2E_SIGNOFF_MUX_WS_RESTAMP: upstreamReady with parallel contexts — restamp ws without restart" >&2
      _stamp_mux_ws_url || true
      _stamp_mux_daemon_ws_url || true
      ok "cdmcp-mux signoff ws restamp (upstreamReady=1)"
      return 0
    fi
    _restart_mux_safely "CDP WebSocket drift"
  fi
  local i
  for i in $(seq 1 15); do
    sleep 1
    if _mux_upstream_ready; then
      _stamp_mux_ws_url || true
      _stamp_mux_daemon_ws_url || true
      ok "cdmcp-mux upstream reconnected"
      return 0
    fi
  done
  fail "cdmcp-mux upstreamReady still false — Cmd+Q Cursor, then: ./myrm ready --chrome"
}

_mux_timeout_stamp_matches() {
  [[ -f "${MUX_TIMEOUT_STAMP}" ]] || return 1
  local stored
  stored="$(tr -d '[:space:]' < "${MUX_TIMEOUT_STAMP}")"
  [[ "${stored}" == "${MUX_REQUEST_TIMEOUT_MS}" ]]
}

_stamp_mux_request_timeout() {
  mkdir -p "${MUX_STATE_DIR}"
  printf '%s\n' "${MUX_REQUEST_TIMEOUT_MS}" >"${MUX_TIMEOUT_STAMP}"
}

_stamp_mux_daemon_request_timeout() {
  mkdir -p "${MUX_STATE_DIR}"
  printf '%s\n' "${MUX_REQUEST_TIMEOUT_MS}" >"${MUX_DAEMON_TIMEOUT_STAMP}"
}

_mux_daemon_timeout_matches() {
  [[ -f "${MUX_DAEMON_TIMEOUT_STAMP}" ]] || return 1
  local stored
  stored="$(tr -d '[:space:]' < "${MUX_DAEMON_TIMEOUT_STAMP}")"
  [[ "${stored}" == "${MUX_REQUEST_TIMEOUT_MS}" ]]
}

_mux_parallel_active_leases() {
  _wave_active_lease_count "${MONOREPO_ROOT}" 2>/dev/null || echo 0
}

_mux_probe_timeout_sec() {
  local active_leases probe_timeout
  active_leases="$(_mux_parallel_active_leases)"
  probe_timeout=8
  if [[ "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    probe_timeout=$((8 + active_leases * 3))
    if [[ "${probe_timeout}" -gt 45 ]]; then
      probe_timeout=45
    fi
  fi
  echo "${probe_timeout}"
}

_mux_request_timeout_effective() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  local probe_timeout
  probe_timeout="$(_mux_probe_timeout_sec)"
  "${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/mux_responsive_probe.py" \
    --expected-ms "${MUX_REQUEST_TIMEOUT_MS}" \
    --state-dir "${MUX_STATE_DIR}" \
    --socket "${MUX_SOCKET}" \
    --probe-timeout-sec "${probe_timeout}"
}

_mux_daemon_pid_alive() {
  [[ -f "${MUX_PID_FILE}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' < "${MUX_PID_FILE}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

_mux_parallel_attach_health_ok() {
  _mux_upstream_ready && _mux_ws_stamp_matches && _mux_daemon_pid_alive
}

_heal_mux_under_parallel_attach_load() {
  [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]] || return 1
  local active_leases attempt
  active_leases="$(_mux_parallel_active_leases)"
  [[ "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]] || return 1
  # R123++: under parallel Wave leases, tools/list can queue behind peer tabs.
  # Trust upstream+ws+pid before expensive probes so attach clears mux_begin quickly.
  if _mux_parallel_attach_health_ok; then
    echo "CHROME_E2E_WARN: mux parallel attach fast-path — skip timeout probe (${active_leases} active leases)" >&2
    return 0
  fi
  for attempt in 1 2; do
    if _mux_request_timeout_effective; then
      return 0
    fi
    echo "CHROME_E2E_WARN: mux probe slow (${active_leases} active leases) attempt ${attempt}/2" >&2
    sleep $((attempt * 2))
    if _mux_parallel_attach_health_ok; then
      echo "CHROME_E2E_WARN: mux probe timeout under parallel load — skip restart (${active_leases} active leases)" >&2
      return 0
    fi
  done
  if _mux_parallel_attach_health_ok; then
    echo "CHROME_E2E_WARN: mux probe timeout under parallel load — skip restart (${active_leases} active leases)" >&2
    return 0
  fi
  return 1
}

_heal_mux_request_timeout_drift() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  local active_leases
  active_leases="$(_mux_parallel_active_leases)"
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" && "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    if _mux_parallel_attach_health_ok; then
      echo "CHROME_E2E_WARN: mux parallel attach fast-path — skip timeout probe (${active_leases} active leases)" >&2
      return 0
    fi
  fi
  if _mux_request_timeout_effective; then
    return 0
  fi
  if _heal_mux_under_parallel_attach_load; then
    return 0
  fi
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" && "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    if _mux_parallel_attach_health_ok; then
      echo "CHROME_E2E_WARN: mux heal restart suppressed during attach (${active_leases} active leases)" >&2
      return 0
    fi
  fi
  # Probe failed — heal/restart (fail-closed for stale 55s upstream; BUG-DG-2026-07-21-001).
  if ! _mux_daemon_pid_alive; then
    return 0
  fi
  if _mux_timeout_restart_allowed || _mux_restart_allowed; then
    _restart_mux_safely "request timeout drift (${MUX_REQUEST_TIMEOUT_MS}ms)"
  elif _mux_attach_timeout_restart_allowed; then
    _restart_mux_safely "attach request timeout drift (${MUX_REQUEST_TIMEOUT_MS}ms)"
  elif _mux_upstream_ready && _mux_ws_stamp_matches; then
    fail "mux request timeout drift (${MUX_REQUEST_TIMEOUT_MS}ms) — daemon probe failed; attach restart not allowed"
  elif _mux_parallel_load_blocks_global_restart; then
    echo "CHROME_E2E_WARN: mux heal restart blocked — parallel contexts or wave leases active" >&2
    return 0
  else
    _restart_mux_safely "request timeout drift (${MUX_REQUEST_TIMEOUT_MS}ms)"
  fi
  if ! _mux_request_timeout_effective; then
    fail "mux timeout probe still failing after heal (${MUX_REQUEST_TIMEOUT_MS}ms)"
  fi
}

_ensure_mux_daemon() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  [[ -f "${MUX_BIN}" ]] || fail "Missing mux bin ${MUX_BIN} — run: bash scripts/dev/install-cdmcp-mux-autoconnect.sh"
  if [[ -f "${MUX_PID_FILE}" ]]; then
    local pid
    pid="$(tr -d '[:space:]' < "${MUX_PID_FILE}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      if ! _mux_request_timeout_effective; then
        _heal_mux_request_timeout_drift
      fi
      return 0
    fi
  fi
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
    fail "cdmcp-mux daemon not running during attach — first Agent must run: ./myrm ready --chrome"
  fi
  echo "CHROME_E2E_WARN: starting cdmcp-mux daemon for preflight" >&2
  _start_mux_daemon
  local i
  for i in $(seq 1 15); do
    if [[ -f "${MUX_PID_FILE}" ]] && kill -0 "$(tr -d '[:space:]' < "${MUX_PID_FILE}")" 2>/dev/null; then
      ok "cdmcp-mux daemon auto-started"
      return 0
    fi
    sleep 1
  done
  fail "cdmcp-mux daemon failed to start — run: node scripts/dev/cdmcp-mux-autoconnect/bin/cdmcp-mux-autoconnect.mjs daemon"
}

_recover_mux_after_cdp_restart() {
  [[ -f "${MUX_BIN}" ]] || fail "Missing mux bin ${MUX_BIN} during Chrome crash recovery"
  MUX_USING=1
  if _mux_daemon_pid_alive; then
    local attempt
    for attempt in 1 2 3; do
      if _mux_upstream_ready; then
        _stamp_mux_ws_url || true
        _stamp_mux_daemon_ws_url || true
        ok "cdmcp-mux reattached after Chrome crash without restart"
        return 0
      fi
      sleep 1
    done
    echo "CHROME_E2E_ATTACH_HEAL: mux upstream stayed down after Chrome recovery — restart exact owned namespace" >&2
    _stop_mux_daemon
  fi
  _start_mux_daemon
  local attempt
  for attempt in $(seq 1 15); do
    if _mux_daemon_pid_alive && _mux_upstream_ready; then
      _stamp_mux_ws_url || true
      _stamp_mux_daemon_ws_url || true
      ok "cdmcp-mux recovered after Chrome crash"
      return 0
    fi
    sleep 1
  done
  fail "cdmcp-mux did not recover after Chrome/CDP restart"
}

_ensure_browser_orchestrator_after_data_plane() {
  [[ "${MYRM_BROWSER_ORCHESTRATOR:-}" == "1" ]] || return 0
  local orchestrator_ensure="${MONOREPO_ROOT}/scripts/dev/ensure-browser-orchestrator.sh"
  [[ -f "${orchestrator_ensure}" ]] || return 0
  local ensure_rc=0
  if bash "${orchestrator_ensure}"; then
    return 0
  else
    ensure_rc=$?
  fi
  if [[ "${ensure_rc}" -ne 75 ]]; then
    fail "browser-orchestrator daemon required after Chrome/CDP/mux readiness"
  fi
  echo "CHROME_E2E_INFRA_RACE_HEAL: CDP collapsed after preflight — recover Chrome→mux→orchestrator" >&2
  bash "${ENSURE_CHROME}" \
    || fail "Chrome/CDP recovery failed after orchestrator CDP_UNAVAILABLE"
  export MYRM_CHROME_E2E_CDP_RECOVERED=1
  _recover_mux_after_cdp_restart
  bash "${orchestrator_ensure}" \
    || fail "browser-orchestrator failed after Chrome/CDP race recovery"
}

if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
  # R73-B: mux-only must exit before attach crash/drift heal (parallel signoff stack heal).
  if [[ "${MYRM_CHROME_E2E_MUX_HEAL_ONLY:-}" == "1" ]]; then
    if [[ "${MYRM_CHROME_E2E_CDP_RECOVERED:-}" == "1" ]]; then
      _recover_mux_after_cdp_restart
    else
      _heal_mux_request_timeout_drift
    fi
    _ensure_browser_orchestrator_after_data_plane
    ok "mux heal-only complete (attach mode, timeout=${MUX_REQUEST_TIMEOUT_MS}ms)"
    exit 0
  fi
  if [[ "${MYRM_MUX_FORCE_ATTACH_RESTART:-}" == "1" ]]; then
    if _mux_parallel_load_blocks_global_restart; then
      echo "CHROME_E2E_WARN: force attach restart blocked — parallel contexts or wave leases active" >&2
      exit 1
    fi
    _restart_mux_safely "attach new_page timeout (forced open_mcp_page heal)"
    ok "mux daemon force-restarted (attach new_page heal)"
    exit 0
  fi
  attach_parallel_leases="$(_wave_active_lease_count "${MONOREPO_ROOT}" 2>/dev/null || echo 0)"
  if [[ "${attach_parallel_leases}" =~ ^[0-9]+$ && "${attach_parallel_leases}" -gt 0 ]]; then
    echo "CHROME_E2E_ATTACH: parallel leases=${attach_parallel_leases} — keep healthy pinned backend; defer source-drift reload" >&2
  fi
  if [[ -f "${SCRIPT_DIR}/dev-stack.sh" ]]; then
    # Crash recovery is independent of source promotion and remains available
    # under parallel load. Both helpers are idempotent when :8080 is healthy;
    # drift handling records metadata only and never restarts the pinned backend.
    _smp_attach_backend_crash_heal "${MONOREPO_ROOT}" "${SCRIPT_DIR}/dev-stack.sh"
    _smp_attach_backend_drift_heal "${MONOREPO_ROOT}" "${SERVER_DIR}" "${SCRIPT_DIR}/dev-stack.sh"
  fi
  _preflight_progress "mux_begin"
  _heal_mux_request_timeout_drift
  _preflight_progress "mux_ready"
  if [[ "${MYRM_PRIVATE_BACKEND:-}" == "1" ]]; then
    _private_backend_attach_path
    _ensure_browser_orchestrator_after_data_plane
    exit 0
  fi
  _attach_fast_path
  _preflight_progress "attach_health"
  _ensure_browser_orchestrator_after_data_plane
  _preflight_progress "orchestrator"
  exit 0
fi

_ensure_mux_daemon

VANILLA_MCP_COUNT=0
if pgrep -f 'npm exec chrome-devtools-mcp' >/dev/null 2>&1; then
  VANILLA_MCP_COUNT="$(pgrep -f 'npm exec chrome-devtools-mcp' | wc -l | tr -d ' ')"
fi
if [[ "${MUX_USING}" -eq 1 ]]; then
  if [[ "${VANILLA_MCP_COUNT}" -gt 0 ]]; then
    if [[ "${MYRM_BROWSER_ORCHESTRATOR:-}" == "1" ]]; then
      echo "CHROME_E2E_WARN: legacy vanilla chrome-devtools-mcp (${VANILLA_MCP_COUNT}) ignored — formal E2E uses browser orchestrator RPC-only" >&2
    else
      fail "Legacy vanilla chrome-devtools-mcp still running (${VANILLA_MCP_COUNT}) — Cmd+Q Cursor; Agent MCP must use ChromeAgent :9410 (./myrm doctor --mcp-isolation --strict-live)"
    fi
  fi
  if [[ ! -f "${MUX_PID_FILE}" ]]; then
    fail "cdmcp-mux daemon not running — run: ./myrm ready --chrome"
  fi
  mux_pid="$(tr -d '[:space:]' < "${MUX_PID_FILE}")"
  if ! kill -0 "${mux_pid}" 2>/dev/null; then
    fail "cdmcp-mux daemon pid ${mux_pid} not alive — Cmd+Q Cursor and reopen"
  fi
  _ensure_mux_upstream
  mux_count="$(_mux_daemon_count)"
  if [[ "${mux_count}" != "1" ]]; then
    if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
      fail "mux daemon count=${mux_count} during attach — first Agent: ./myrm ready --chrome (attach must not kill mux)"
    fi
    _restart_mux_safely "expected one owned daemon, found ${mux_count}"
    sleep 1
    _ensure_mux_upstream
    mux_count="$(_mux_daemon_count)"
    [[ "${mux_count}" == "1" ]] || fail "mux daemon count=${mux_count} after reconcile — Cmd+Q Cursor, then: ./myrm ready --chrome"
  fi
  ok "cdmcp-mux daemon pid=${mux_pid} (parallel Agent tabs OK)"
else
  if [[ "${VANILLA_MCP_COUNT}" -gt 1 ]]; then
    fail "Too many vanilla chrome-devtools-mcp processes (${VANILLA_MCP_COUNT}) — Cmd+Q Cursor windows using Agent browser MCP"
  fi
  if [[ "${VANILLA_MCP_COUNT}" -eq 1 ]]; then
    echo "CHROME_E2E_WARN: vanilla chrome-devtools-mcp detected — Agent MCP should use --auto-connect; E2E uses ./myrm ready --chrome" >&2
  fi
fi

_print_e2e_health_json() {
  local runtime_py="${SCRIPT_DIR}/lib/runtime_identity.py"
  local require_ready="${1:-0}"
  local shell_hot="false" client_hot="false"
  [[ -f "${runtime_py}" ]] || fail "Missing runtime_identity.py at ${runtime_py}"
  if [[ "$(_frontend_shell_hot_status)" == "yes" ]]; then
    shell_hot="true"
  fi
  if [[ "$(_frontend_client_hot_status)" == "yes" ]]; then
    client_hot="true"
  fi
  local health_args=(
    --auto-probe
    --ui "${UI_BASE}"
    --api "${API_BASE}"
  )
  [[ "${shell_hot}" == "true" ]] && health_args+=(--shell-hot)
  [[ "${client_hot}" == "true" ]] && health_args+=(--client-hot)
  [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]] && health_args+=(--attach-mode)
  if [[ "${require_ready}" == "1" ]]; then
    health_args+=("$(_attach_health_require_args)")
  fi
  "${PREFLIGHT_PY}" "${runtime_py}" "${health_args[@]}"
}

if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
  _heal_shared_ui_if_stale || true
  if [[ "$(_frontend_client_hot_status)" != "yes" ]]; then
    fail "client_hot missing during attach — first Agent must finish ./myrm ready --chrome"
  fi
  echo "CHROME_E2E_READY ui=$UI_BASE api=$API_BASE port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
  CHROME_E2E_CLI="${SCRIPT_DIR}/chrome-e2e/cli.sh"
  if [[ -f "${CHROME_E2E_CLI}" ]]; then
    bash "${CHROME_E2E_CLI}" transition preflight-done "${SAVED_FRONTMOST_PID}" >/dev/null 2>&1 || true
  fi
  _print_e2e_health_json
  exit 0
fi

# 5. CDP WebSocket (Chrome 150+ may omit DevToolsActivePort — use /json/version fallback)
raw_port="${MYRM_CHROME_E2E_PORT}"
ws_path=""
if [[ -f "$ACTIVE_PORT_FILE" ]]; then
  raw_port=$(sed -n '1p' "$ACTIVE_PORT_FILE" | tr -d '[:space:]')
  ws_path=$(sed -n '2p' "$ACTIVE_PORT_FILE" | tr -d '[:space:]')
  if [[ -z "$raw_port" || -z "$ws_path" ]]; then
    fail "Invalid DevToolsActivePort content"
  fi
  ok "DevToolsActivePort port=${raw_port}"
else
  if ! myrm_chrome_e2e_cdp_healthy; then
    fail "CDP not reachable on port ${MYRM_CHROME_E2E_PORT} — run: ./myrm ready --chrome"
  fi
  ok "CDP /json/version port=${MYRM_CHROME_E2E_PORT} (no DevToolsActivePort file)"
fi

if ! command -v "${PREFLIGHT_PY}" >/dev/null 2>&1; then
  fail "python3 required for CDP WebSocket check — install Python 3 or run: cd myrm-agent-server && uv sync"
fi
if [[ -n "${ws_path}" ]]; then
  ws_uri="ws://127.0.0.1:${raw_port}${ws_path}"
else
  ws_uri="$("${PREFLIGHT_PY}" - <<PY
import json
import urllib.request
data = json.load(urllib.request.urlopen("http://127.0.0.1:${MYRM_CHROME_E2E_PORT}/json/version", timeout=5))
print(data["webSocketDebuggerUrl"])
PY
)"
fi
export WS_URI="${ws_uri}"
"${PREFLIGHT_PY}" - <<'PY' || fail "CDP WebSocket unreachable — run: ./myrm ready --chrome"
import asyncio
import os
import sys
try:
    import websockets
except ImportError:
    print("websockets package required in server venv — run: cd myrm-agent-server && uv sync", file=sys.stderr)
    sys.exit(1)
async def main() -> None:
    uri = os.environ["WS_URI"]
    async with websockets.connect(uri, open_timeout=10):
        pass
asyncio.run(main())
PY
ok "CDP WebSocket ${ws_uri}"

# 7. Client hydration warmup (Turbopack chunk graph — not covered by curl shell_hot)
if ! _warmup_frontend_client; then
  fail "frontend client_hot warmup failed — see STACK_FAIL above"
fi
ok "frontend client_hot"

# Client warmup can take long enough for a damaged upstream MCP process to
# disappear. Re-check immediately before declaring the stack ready so callers
# never receive a stale READY signal.
if [[ "${MUX_USING}" -eq 1 ]]; then
  _ensure_mux_upstream
fi

# 8. Stale chrome-devtools-mcp from old Cursor sessions
if pgrep -fl "chrome-devtools-mcp" >/dev/null 2>&1; then
  while read -r line; do
    pid=$(echo "$line" | awk '{print $1}')
    if [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]]; then
      etime=$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ')
      if [[ "$etime" =~ ^[0-9]+-[0-9]+: ]]; then
        echo "CHROME_E2E_WARN: stale chrome-devtools-mcp pid=$pid etime=$etime — Cmd+Q restart Cursor before MCP E2E" >&2
      fi
    fi
  done < <(pgrep -lf "chrome-devtools-mcp" 2>/dev/null || true)
fi

echo "CHROME_E2E_READY ui=$UI_BASE api=$API_BASE port=$raw_port profile=${MYRM_CHROME_E2E_DATA_DIR}"
CHROME_E2E_CLI="${SCRIPT_DIR}/chrome-e2e/cli.sh"
if [[ -f "${CHROME_E2E_CLI}" ]]; then
  bash "${CHROME_E2E_CLI}" transition preflight-done "${SAVED_FRONTMOST_PID}" >/dev/null 2>&1 || true
fi
if [[ "${MYRM_CHROME_E2E_ATTACH}" != "1" ]]; then
  _ensure_stack_epoch_file
fi
export_myrm_next_dist_dir
FRONTEND_LOCK="$(resolve_frontend_lock_path "${FRONTEND_DIR}")"

# TAB-5: idle blank prune SSOT is coordinator IdleHygieneScheduler (reap/finish/teardown).
# Preflight must not run parallel prune hooks — they raced BODY leases and masked orphan storms.

if [[ "${MYRM_BROWSER_ORCHESTRATOR:-}" == "1" ]]; then
  _ensure_browser_orchestrator_after_data_plane
  if [[ "${MYRM_CHROME_E2E_ATTACH:-}" != "1" ]] && declare -f _mux_daemon_count >/dev/null 2>&1; then
    mux_count="$(_mux_daemon_count 2>/dev/null || echo 0)"
    if [[ "${mux_count}" != "1" ]]; then
      _restart_mux_safely "orchestrator preflight: expected one mux daemon, found ${mux_count}"
      sleep 1
      mux_count="$(_mux_daemon_count 2>/dev/null || echo 0)"
      [[ "${mux_count}" == "1" ]] || fail "mux daemon count=${mux_count} after reconcile — Cmd+Q Cursor, then: ./myrm ready --chrome"
    fi
  fi
fi

health_attempt=0
while [[ "${health_attempt}" -lt 3 ]]; do
  if _print_e2e_health_json 1; then
    exit 0
  fi
  health_attempt=$((health_attempt + 1))
  if [[ "${health_attempt}" -lt 3 ]]; then
    echo "CHROME_E2E_WARN: health snapshot retry ${health_attempt}/3" >&2
    sleep 2
  fi
done
fail "final runtime health snapshot rejected — retry: ./myrm ready --chrome"
