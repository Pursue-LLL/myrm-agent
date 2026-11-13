#!/usr/bin/env bash
# Attach admission helpers: the ADMIT poll budget, the epoch-drift attach cap, the data-plane check and
# the readiness predicate and label a health snapshot is judged by before a parallel agent may attach.
# Sourced by chrome-e2e-preflight.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

_admit_poll_touch() {
  local node="$1"
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/e2e_core/admit_poll.py" touch --node "${node}" \
    2>/dev/null || true
}

_admit_poll_budget_or_fail() {
  local node="$1"
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/e2e_core/admit_poll.py" assert-budget --node "${node}"
}

_epoch_drift_shared_attach_cap_sec() {
  local shell_leases="${1:-0}"
  [[ "${shell_leases}" =~ ^[0-9]+$ ]] || shell_leases=0
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
import os
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.api_verify import epoch_drift_attach_cap_sec, resolve_e2e_api_context
shell_leases = int('${shell_leases}')
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
effective_leases = max(int(ctx.active_leases), shell_leases)
print(
    epoch_drift_attach_cap_sec(
        blocked=ctx.blocked,
        epoch_match=ctx.epoch_match,
        drift_pending=ctx.drift_pending,
        active_leases=effective_leases,
    )
)
" 2>/dev/null || echo 0
}

_ensure_plane_before_attach() {
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.plane_health import ensure_plane_before_probe, PlaneHealthState
snap = ensure_plane_before_probe()
if snap.state.value != PlaneHealthState.OBSERVABLE.value:
    print(
        f'CHROME_E2E_PLANE: state={snap.state.value} rule={snap.agent_rule}',
        file=sys.stderr,
        flush=True,
    )
    sys.exit(1)
" || fail "browser data plane not observable — run ./myrm-dev restart --chrome when wave idle (verify-api does not heal mux/orch/the shared API)"
}

_attach_health_require_args() {
  if [[ "${E2E_SIGNOFF:-}" == "1" ]]; then
    echo "--require-signoff-stream-ready"
    return 0
  fi
  # parallel attach with live UI/API — signoff-stream gate (no frontendEpoch SMP defer).
  if _shared_stack_endpoints_ok; then
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
