#!/usr/bin/env bash
# Dev stack lifecycle — ensure/attach/reset/status for the local stack (default ports: dev_state_paths.sh).
# Mutations delegate to stack_supervisor daemon; only its direct child may enter internals.
# Usage: dev-stack.sh ensure|attach|reset|status
#   ensure  — mkdir atomic lock + start stack if unhealthy (idempotent)
#   attach  — wait for healthy stack, zero start/kill side effects
#   reset   — stop backend + frontend (only legal kill entry)
#   status  — JSON-ish health snapshot
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=lib/stack_stage.sh
source "${SCRIPT_DIR}/lib/stack_stage.sh"
_stack_stage enter
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
# shellcheck source=lib/backend_bg.sh
source "${SCRIPT_DIR}/lib/backend_bg.sh"
# shellcheck source=lib/frontend-warmup.sh
source "${SCRIPT_DIR}/lib/frontend-warmup.sh"
# shellcheck source=lib/stack-epoch.sh
source "${SCRIPT_DIR}/lib/stack-epoch.sh"
# shellcheck source=lib/dev_state_paths.sh
source "${SCRIPT_DIR}/lib/dev_state_paths.sh"
resolve_agent_paths "${REPO_ROOT}"
_stack_stage libs_loaded

STATE_DIR="$(dev_state_dir)"
BACKEND_PORT="${MYRM_BACKEND_PORT:-${PORT:-$(dev_default_backend_port)}}"
FRONTEND_PORT="${MYRM_FRONTEND_PORT:-$(dev_default_frontend_port)}"
APP_URL="${E2E_UI_BASE:-http://127.0.0.1:${FRONTEND_PORT}}"
# Private SHPOIB backends must probe their assigned port — inherited shared
# E2E_API_BASE (the shared port) makes ensure succeed against the wrong API while :18080
# lacks identity, triggering orphan reclaim loops.
if [[ "${MYRM_PRIVATE_BACKEND:-}" == "1" || "${MYRM_E2E_PRIVATE_BACKEND:-}" == "1" ]] \
  || [[ "${MYRM_DEV_STATE_DIR:-}" != "$(_real_home_default_state_dir)" ]]; then
  API_BASE="http://127.0.0.1:${BACKEND_PORT}"
else
  API_BASE="${E2E_API_BASE:-http://127.0.0.1:${BACKEND_PORT}}"
fi
API_HEALTH="${API_BASE}/api/v1/health"

BACKEND_PID="${MYRM_BACKEND_PID_FILE:-${STATE_DIR}/backend.pid}"
BACKEND_LOG="${MYRM_BACKEND_LOG_FILE:-${STATE_DIR}/backend.log}"
BACKEND_IDENTITY="${MYRM_BACKEND_IDENTITY_FILE:-${STATE_DIR}/backend-process.json}"
FRONTEND_PID="${MYRM_FRONTEND_PID_FILE:-${STATE_DIR}/frontend.pid}"
FRONTEND_LOG="${MYRM_FRONTEND_LOG_FILE:-${STATE_DIR}/frontend.log}"
export STATE_DIR PORT="${BACKEND_PORT}" MYRM_BACKEND_PORT="${BACKEND_PORT}" MYRM_DEV_STATE_DIR="${STATE_DIR}"
# Private backend-only pools reuse the shared UI while owning a private backend
# port. The UI bakes its /api/v1 upstream at spawn time, so any frontend (re)start from
# such a pool must keep pointing at the shared backend — never at the pool's private one.
if [[ "${FRONTEND_PORT}" == "$(dev_shared_frontend_port)" ]] \
  && [[ "${MYRM_PRIVATE_BACKEND:-}" == "1" || "${MYRM_E2E_PRIVATE_BACKEND:-}" == "1" ]]; then
  FRONTEND_API_PORT="$(dev_shared_backend_port)"
else
  FRONTEND_API_PORT="${BACKEND_PORT}"
fi
export MYRM_FRONTEND_PORT="${FRONTEND_PORT}" API_PORT="${BACKEND_PORT}"
export E2E_UI_BASE="${APP_URL}" E2E_API_BASE="${API_BASE}"
export MYRM_BACKEND_PID_FILE="${BACKEND_PID}" MYRM_BACKEND_LOG_FILE="${BACKEND_LOG}"
export MYRM_BACKEND_IDENTITY_FILE="${BACKEND_IDENTITY}"
export MYRM_RUNTIME_NAMESPACE="${MYRM_RUNTIME_NAMESPACE:-shared}"

ENSURE_FRONTEND_WAIT_SEC="${MYRM_STACK_FRONTEND_WAIT_SEC:-180}"
# Wait budget must cover a full ensure (frontend cold compile) plus lock handoff.
ATTACH_WAIT_SEC="${MYRM_STACK_ATTACH_WAIT_SEC:-$((ENSURE_FRONTEND_WAIT_SEC + 60))}"

mkdir -p "${STATE_DIR}"

_resolve_bun() {
  if command -v bun >/dev/null 2>&1; then
    command -v bun
    return 0
  fi
  local candidate
  for candidate in "${HOME}/.bun/bin/bun" /opt/homebrew/bin/bun /usr/local/bin/bun; do
    if [[ -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

MYRM_BUN="$(_resolve_bun || true)"
if [[ -n "${MYRM_BUN}" ]]; then
  MYRM_BUN_DIR="$(dirname "${MYRM_BUN}")"
  export PATH="${MYRM_BUN_DIR}:${PATH}"
fi

export_myrm_next_dist_dir
if [[ "${STATE_DIR}" != "$(_real_home_default_state_dir)" ]]; then
  export MYRM_FRONTEND_DEV_WEBPACK="${MYRM_FRONTEND_DEV_WEBPACK:-0}"
fi
mkdir -p "${FRONTEND_DIR}/${MYRM_NEXT_DIST_DIR}"
FRONTEND_LOCK="$(resolve_frontend_lock_path "${FRONTEND_DIR}")"

_lock_dir="${STATE_DIR}/ensure.lock.d"

# Command implementations live in lib/dev_stack/*.sh: definition-only files sourced into this shell,
# so every global assigned above is shared.
# shellcheck source=lib/dev_stack/locks.sh
source "${SCRIPT_DIR}/lib/dev_stack/locks.sh"
# shellcheck source=lib/dev_stack/health.sh
source "${SCRIPT_DIR}/lib/dev_stack/health.sh"
# shellcheck source=lib/dev_stack/listeners.sh
source "${SCRIPT_DIR}/lib/dev_stack/listeners.sh"
# shellcheck source=lib/dev_stack/frontend_heal.sh
source "${SCRIPT_DIR}/lib/dev_stack/frontend_heal.sh"
# shellcheck source=lib/dev_stack/frontend_supervisor.sh
source "${SCRIPT_DIR}/lib/dev_stack/frontend_supervisor.sh"
# shellcheck source=lib/dev_stack/stack_commands.sh
source "${SCRIPT_DIR}/lib/dev_stack/stack_commands.sh"
# shellcheck source=lib/dev_stack/private_backend.sh
source "${SCRIPT_DIR}/lib/dev_stack/private_backend.sh"
# shellcheck source=lib/dev_stack/partial_commands.sh
source "${SCRIPT_DIR}/lib/dev_stack/partial_commands.sh"

usage() {
  echo "Usage: dev-stack.sh ensure|attach|reset|status|backend-only ensure|backend-only stop|frontend-only ensure|frontend-only clear-pause|frontend-only restart-report [--mark]" >&2
}

_supervisor_delegate_or_fail() {
  local cmd="$1"
  if bash "${SCRIPT_DIR}/stack-supervisor.sh" rpc "${cmd}"; then
    return 0
  fi
  echo "STACK_FAIL: supervisor rpc ${cmd} failed — run: bash ${SCRIPT_DIR}/stack-supervisor.sh start && cd open-perplexity && ./myrm-dev ready" >&2
  exit 1
}

_supervisor_internal_call() {
  local supervisor_pid_file="${STATE_DIR}/supervisor.pid" supervisor_pid=""
  [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" ]] || return 1
  [[ -f "${supervisor_pid_file}" ]] || return 1
  supervisor_pid="$(tr -d '[:space:]' <"${supervisor_pid_file}")"
  [[ "${supervisor_pid}" =~ ^[0-9]+$ ]] || return 1
  [[ "${supervisor_pid}" == "${PPID}" ]] || return 1
  dev_pid_alive "${supervisor_pid}"
}

# A stack command ends the process with its own status, so `main` never falls through to a second dispatch.
_run_and_exit() {
  "$@"
  exit $?
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    ensure)
      if _supervisor_internal_call || [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" ]]; then _run_and_exit cmd_ensure; fi
      _supervisor_delegate_or_fail ensure
      ;;
    attach)
      # Read plane: attach only observes/waits for health and must never queue
      # behind supervisor mutations such as ensure/reset.
      cmd_attach
      ;;
    reset)
      if _supervisor_internal_call || [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" ]]; then _run_and_exit cmd_reset; fi
      _supervisor_delegate_or_fail reset
      ;;
    status)
      # Read plane: status is side-effect free and must remain available while
      # a long ensure is in flight; routing it through RPC caused false hangs.
      cmd_status
      ;;
    backend-only)
      local subcmd="${2:-}"
      case "${subcmd}" in
        ensure)
          if _supervisor_internal_call || [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" || "${MYRM_WAVE_GATE_BYPASS:-}" == "1" ]]; then
            _run_and_exit cmd_backend_only_ensure
          fi
          echo "STACK_FAIL: backend-only ensure requires MYRM_SUPERVISOR_BYPASS=1 or MYRM_WAVE_GATE_BYPASS=1" >&2
          exit 1
          ;;
        stop)
          if _supervisor_internal_call || [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" || "${MYRM_WAVE_GATE_BYPASS:-}" == "1" ]]; then
            _run_and_exit cmd_backend_only_stop
          fi
          echo "STACK_FAIL: backend-only stop requires MYRM_SUPERVISOR_BYPASS=1 or MYRM_WAVE_GATE_BYPASS=1" >&2
          exit 1
          ;;
        *)
          echo "Unknown backend-only command: ${subcmd}" >&2
          usage
          exit 1
          ;;
      esac
      ;;
    frontend-only)
      local subcmd="${2:-}"
      case "${subcmd}" in
        clear-pause)
          "${PREFLIGHT_PY:-python3}" "${SCRIPT_DIR}/lib/e2e_core/frontend_dev_pause.py" clear
          exit $?
          ;;
        restart-report)
          # Read plane: journal kills vs SIGTERMs in frontend.log; "--mark" restarts the window.
          _frontend_lifecycle report --state-dir "${STATE_DIR}" --log-file "${FRONTEND_LOG}" \
            ${3:+"$3"}
          exit $?
          ;;
        ensure)
          if _supervisor_internal_call || [[ "${MYRM_FRONTEND_ENSURE_INNER:-}" == "1" ]]; then
            _run_and_exit cmd_frontend_only_ensure
          fi
          if [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" || "${MYRM_E2E_SHPOIB:-}" == "1" ]]; then
            local monorepo_root heal_py heal_rc
            monorepo_root="$(cd "${REPO_ROOT}/.." && pwd)"
            heal_py="${SCRIPT_DIR}/lib/e2e_core/warm_ui_heal.py"
            if [[ -f "${heal_py}" ]]; then
              heal_rc=0
              "${PREFLIGHT_PY:-python3}" "${heal_py}" attach "${monorepo_root}" || heal_rc=$?
              exit "${heal_rc}"
            fi
            _run_and_exit cmd_frontend_only_ensure
          fi
          echo "STACK_FAIL: frontend-only ensure requires MYRM_SUPERVISOR_BYPASS=1 or MYRM_E2E_SHPOIB=1" >&2
          exit 1
          ;;
        *)
          echo "Unknown frontend-only command: ${subcmd}" >&2
          usage
          exit 1
          ;;
      esac
      ;;
    ""|-h|--help) usage; exit 1 ;;
    *)
      echo "Unknown command: ${cmd}" >&2
      usage
      exit 1
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
