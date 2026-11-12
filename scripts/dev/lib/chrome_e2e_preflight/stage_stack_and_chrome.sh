#!/usr/bin/env bash
# Preflight steps 0-3: the API-only SHPOIB exit, the unified readiness gate, the dev servers and the
# dedicated E2E Chrome (with the helper functions only these steps use).
# Sourced by chrome-e2e-preflight.sh at the point where this step starts. It runs in the entry's shell, so
# its globals, `fail` and `exit` are the entry's.
# shellcheck shell=bash
# shellcheck disable=SC2153  # UI_BASE is assigned by the entry
# shellcheck disable=SC2034  # ACTIVE_PORT_FILE is read by stage_ready.sh

# 0. API-only SHPOIB (signoff clarify pool / cron LIVE): seed private API only — never probe shared UI.
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
      "${PREFLIGHT_PY}" -m e2e_core.readiness emit 2>&1
  )" || rc=$?
  echo "${py_out}" >&2
  if [[ "${rc}" -eq 2 ]]; then
    fail "cluster readiness FAIL — run ./myrm-dev e2e-context; do not stop other pytest"
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
# mux-heal-only signoff must not block on attach endpoint wait + frontend dogpile.
if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" && "${MYRM_PREFLIGHT_SKIP_ATTACH_WAIT:-}" != "1" && "${MYRM_CHROME_E2E_MUX_HEAL_ONLY:-}" != "1" ]]; then
  _bootstrap_attach_begin "$(_parallel_attach_active_leases)"
  if [[ "${MYRM_E2E_EPOCH_PIN:-0}" == "1" ]] && _attach_epoch_pin_drop_stale_when_shared_aligned; then
    echo "CHROME_E2E_ATTACH: shared epoch aligned — drop stale epoch pin api=${API_BASE}" >&2
    unset MYRM_E2E_EPOCH_PIN
    export E2E_API_BASE="${API_BASE}"
  fi
  _attach_api="$(_attach_api_base)"
  if [[ "${MYRM_E2E_EPOCH_PIN:-0}" == "1" ]]; then
    echo "CHROME_E2E_ATTACH: epoch pin ADMIT wait uses api=${_attach_api} (skip shared API unreachable gate)" >&2
  fi
  attach_errors="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.endpoint_health import attach_wait_errors
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
      API_BASE="${SHARED_API_BASE}"
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
from e2e_core.endpoint_health import format_attach_endpoint_failure
print(format_attach_endpoint_failure([p.strip() for p in '''${attach_errors}'''.split(',') if p.strip()]))
")"
      if [[ "${attach_errors}" == *"api=foreign_listener"* ]]; then
        fail "${attach_msg}"
      fi
      fail "${attach_msg} — first Agent must run: ./myrm-dev ready --chrome"
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
  curl -sf --max-time 10 "$API_BASE/api/v1/health" >/dev/null || fail "Backend not reachable at $API_BASE — run: cd open-perplexity && ./myrm-dev ready"
fi
ok "dev servers :${FRONTEND_PORT}/${MYRM_BACKEND_PORT:-$(dev_default_backend_port)}"
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

# 3. Ensure dedicated E2E Chrome (no Allow — launched with --remote-debugging-port)
[[ -f "${ENSURE_CHROME}" ]] || fail "Missing ${ENSURE_CHROME}"

_ensure_browser_pool_chrome() {
  local port="$1"
  local data_dir ensure_one_out=""
  data_dir="$("${PREFLIGHT_PY}" -c "
import os, sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.browser_pool import resolve_chrome_data_dir
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

# G4/: heuristic blank prune removed — idle hygiene via coordinator reap (SSOT §18.7.2).

ACTIVE_PORT_FILE="${MYRM_CHROME_E2E_ACTIVE_PORT_FILE}"
