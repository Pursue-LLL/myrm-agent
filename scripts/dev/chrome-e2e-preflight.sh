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

MYRM_CHROME_E2E_ATTACH="${MYRM_CHROME_E2E_ATTACH:-0}"
export MYRM_CHROME_E2E_ATTACH
MYRM_BROWSER_ORCHESTRATOR="${MYRM_BROWSER_ORCHESTRATOR:-1}"
export MYRM_BROWSER_ORCHESTRATOR
MYRM_MUX_ALLOW_TIMEOUT_RESTART="${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-1}"
export MYRM_MUX_ALLOW_TIMEOUT_RESTART
# python -m e2e_core.bootstrap_deadline must share one holder key across subprocesses.
export MYRM_E2E_DEDUPE_HOLDER_PID="${MYRM_E2E_DEDUPE_HOLDER_PID:-$$}"
# launch-force maintainer override must use fast attach path (solo PASS ~212s);
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
from e2e_core.verify_backend_seed import ensure_verify_backend_seed
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
UI_BASE="${E2E_UI_BASE:-http://127.0.0.1:$(dev_default_frontend_port)}"
SHARED_API_BASE="${MYRM_SHARED_API_BASE:-http://127.0.0.1:$(dev_shared_backend_port)}"
API_BASE="${E2E_API_BASE:-${SHARED_API_BASE}}"
# Sandboxed HOME (e.g. Cursor's ~/.cursor-3) would split mux state, warm shells and
# harness data across two homes. Run the whole preflight under the real user home so
# every $HOME-derived path (cdmcp-mux state, frontend caches) stays on one SSOT dir.
export_spawn_home || exit 1
STATE_DIR="$(dev_state_dir)"
FRONTEND_DIR="${AGENT_ROOT}/myrm-agent-frontend"
export_myrm_next_dist_dir
FRONTEND_LOCK="$(resolve_frontend_lock_path "${FRONTEND_DIR}")"
FRONTEND_LOG="${STATE_DIR}/frontend.log"
APP_URL="${UI_BASE}"
FRONTEND_PORT="${MYRM_FRONTEND_PORT:-$(dev_default_frontend_port)}"
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

# shellcheck source=lib/chrome_e2e_preflight/attach_admission.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/attach_admission.sh"

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

# shellcheck source=lib/chrome_e2e_preflight/provider_seed.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/provider_seed.sh"

# shellcheck source=lib/chrome_e2e_preflight/attach_wait.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/attach_wait.sh"

# shellcheck source=lib/chrome_e2e_preflight/attach_fast_path.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/attach_fast_path.sh"

# shellcheck source=lib/chrome_e2e_preflight/shared_stack.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/shared_stack.sh"

# shellcheck source=lib/chrome_e2e_preflight/stage_stack_and_chrome.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/stage_stack_and_chrome.sh"

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
if [[ -f "${MUX_PID_FILE}" || -f "${MUX_BIN}" ]]; then
  MUX_USING=1
fi

# shellcheck source=lib/chrome_e2e_preflight/mux_daemon.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/mux_daemon.sh"

MUX_WS_STAMP="${MUX_STATE_DIR}/upstream-ws-url"
MUX_DAEMON_WS_STAMP="${MUX_STATE_DIR}/upstream-ws-url-at-daemon-start"

# shellcheck source=lib/chrome_e2e_preflight/mux_status.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/mux_status.sh"

# shellcheck source=lib/chrome_e2e_preflight/mux_restart.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/mux_restart.sh"

# shellcheck source=lib/chrome_e2e_preflight/mux_heal.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/mux_heal.sh"

# shellcheck source=lib/chrome_e2e_preflight/stage_attach_and_mux.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/stage_attach_and_mux.sh"

# shellcheck source=lib/chrome_e2e_preflight/stage_ready.sh
source "${SCRIPT_DIR}/lib/chrome_e2e_preflight/stage_ready.sh"
