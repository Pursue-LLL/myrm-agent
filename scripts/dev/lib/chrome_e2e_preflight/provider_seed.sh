#!/usr/bin/env bash
# Model provider seeding: the shared stack seeds once, a private backend always seeds into its own api.
# Sourced by chrome-e2e-preflight.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash
# shellcheck disable=SC2034  # MYRM_E2E_MODEL_SEED_FAILED is read by shared_stack.sh

_maybe_seed_providers() {
  # fix: the DONE flag is for the SHARED stack only. A private-backend
  # preflight (SHPOIB bootstrap) targets E2E_API_BASE=:<private port> and must
  # always seed, otherwise the fresh private backend inherits stale providers
  # (e.g. stale provider quota) and live E2E fails silently.
  if [[ "${MYRM_E2E_MODEL_SEED_DONE:-0}" == "1" ]] \
    && [[ "${MYRM_PRIVATE_BACKEND:-0}" != "1" ]] \
    && _shared_stack_endpoints_ok; then
    echo "CHROME_E2E_WARN: skip redundant model seed (stack healthy)" >&2
    MYRM_E2E_MODEL_SEED_FAILED=0
    return 0
  fi
  MYRM_E2E_MODEL_SEED_FAILED=0
  if [[ -f "${SERVER_DIR}/.env.test" ]]; then
    if ! PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" "${PREFLIGHT_PY}" -c "
import sys
from pathlib import Path
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.env_test_shell_lint import assert_env_test_shell_safe
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
      if [[ "${MYRM_PRIVATE_BACKEND:-0}" == "1" ]] \
        || [[ "${MYRM_E2E_PRIVATE_BACKEND:-0}" == "1" ]]; then
        # SHPOIB private backends are fail-closed on seed failure; parallel
        # attach must not collapse retries to the shared-stack budget.
        flock_wait_sec="${MYRM_E2E_MODEL_SEED_FLOCK_WAIT_SEC:-30}"
        max_attempts="${MYRM_E2E_MODEL_SEED_RETRIES:-5}"
      else
        flock_wait_sec="${MYRM_E2E_MODEL_SEED_FLOCK_WAIT_SEC:-8}"
        max_attempts="${MYRM_E2E_MODEL_SEED_PARALLEL_RETRIES:-2}"
      fi
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
      echo "CHROME_E2E_WARN: model seed non-fatal under parallel load (shared stack healthy)" >&2
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
