#!/usr/bin/env bash
# Chrome MCP E2E preflight — dedicated Myrm E2E Chrome (:9333, zero Allow).
# Exit 0 prints CHROME_E2E_READY; exit 1 prints actionable failures.
set -euo pipefail

UI_BASE="${E2E_UI_BASE:-http://127.0.0.1:3000}"
API_BASE="${E2E_API_BASE:-http://127.0.0.1:8080}"
MYRM_CHROME_E2E_ATTACH="${MYRM_CHROME_E2E_ATTACH:-0}"
export MYRM_CHROME_E2E_ATTACH
MYRM_MUX_ALLOW_TIMEOUT_RESTART="${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-1}"
export MYRM_MUX_ALLOW_TIMEOUT_RESTART

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=myrm-chrome-e2e-lib.sh
source "${SCRIPT_DIR}/myrm-chrome-e2e-lib.sh"

AGENT_ROOT="${MYRM_AGENT_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
MONOREPO_ROOT="${MYRM_MONOREPO_ROOT:-$(cd "${AGENT_ROOT}/.." && pwd)}"
STATE_DIR="${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}"
FRONTEND_DIR="${AGENT_ROOT}/myrm-agent-frontend"
# shellcheck source=lib/dev_state_paths.sh
source "${SCRIPT_DIR}/lib/dev_state_paths.sh"
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
  if [[ -f "${SERVER_DIR}/.env.test" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${SERVER_DIR}/.env.test"
    set +a
  fi
  if [[ -n "${BASIC_MODEL:-}" && -n "${BASIC_API_KEY:-}" ]]; then
    local attempt max_attempts=5 seed_out=""
    max_attempts="${MYRM_E2E_MODEL_SEED_RETRIES:-5}"
    for attempt in $(seq 1 "${max_attempts}"); do
      if seed_out="$(bun "${SCRIPT_DIR}/chrome-e2e-model-seed.mjs" 2>&1)"; then
        echo "${seed_out}"
        ok "model seed"
        return 0
      fi
      if [[ "${attempt}" -lt "${max_attempts}" ]]; then
        echo "CHROME_E2E_WARN: model seed attempt ${attempt}/${max_attempts} failed — retry in 2s: ${seed_out}" >&2
        sleep 2
      fi
    done
    echo "CHROME_E2E_WARN: model seed failed — ${seed_out}" >&2
    return 0
  fi
  echo "CHROME_E2E_WARN: skip model seed (set BASIC_MODEL and BASIC_API_KEY in .env.test)" >&2
}

_wait_attach_endpoints_under_parallel_load() {
  local initial_errors="$1"
  [[ -n "${initial_errors}" ]] || return 0
  local active_leases wait_sec poll_sec waited errors
  active_leases="$(_wave_active_lease_count "${MONOREPO_ROOT}")"
  [[ "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]] || return 1

  wait_sec="${MYRM_CHROME_E2E_ATTACH_WAIT_SEC:-180}"
  poll_sec="${MYRM_CHROME_E2E_ATTACH_POLL_SEC:-2}"
  [[ "${wait_sec}" =~ ^[0-9]+$ ]] || wait_sec=180
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  waited=0
  while true; do
    errors="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from runtime_identity import attach_endpoint_errors
print(', '.join(attach_endpoint_errors('${UI_BASE}', '${API_BASE}')))
")"
    [[ -z "${errors}" ]] && return 0
    if [[ "${waited}" -ge "${wait_sec}" ]]; then
      printf '%s\n' "${errors}" >&2
      return 1
    fi
    if [[ "${waited}" -eq 0 || $((waited % 10)) -eq 0 ]]; then
      echo "CHROME_E2E_WAIT: parallel attach waiting for ${errors} (${active_leases} active leases) ${waited}/${wait_sec}s" >&2
    fi
    sleep "${poll_sec}"
    waited=$((waited + poll_sec))
  done
}

_attach_fast_path() {
  local runtime_py="${SCRIPT_DIR}/lib/runtime_identity.py"
  local health="" waited=0
  local wait_sec="${MYRM_CHROME_E2E_ATTACH_WAIT_SEC:-180}"
  local poll_sec="${MYRM_CHROME_E2E_ATTACH_POLL_SEC:-2}"
  [[ "${wait_sec}" =~ ^[0-9]+$ ]] || wait_sec=180
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  while true; do
    if health="$("${PREFLIGHT_PY}" "${runtime_py}" \
      --auto-probe \
      --auto-hot \
      --require-attach-ready \
      --ui "${UI_BASE}" \
      --api "${API_BASE}" \
      --attach-mode 2>&1)"; then
      echo "CHROME_E2E_READY ui=${UI_BASE} api=${API_BASE} port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
      echo "${health}"
      return 0
    fi
    if [[ "${waited}" -ge "${wait_sec}" ]]; then
      echo "${health}" >&2
      fail "parallel attach health snapshot did not recover within ${wait_sec}s — first Agent must run: ./myrm ready --chrome"
    fi
    if [[ "${waited}" -eq 0 || $((waited % 10)) -eq 0 ]]; then
      echo "CHROME_E2E_WAIT: shared hot pool is recovering; read-only attach ${waited}/${wait_sec}s" >&2
    fi
    sleep "${poll_sec}"
    waited=$((waited + poll_sec))
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
    sleep "${poll_sec}"
    waited=$((waited + poll_sec))
  done
}

_heal_dead_shared_ui_port() {
  if curl -sf --max-time 5 "http://127.0.0.1:${FRONTEND_PORT}/" >/dev/null 2>&1; then
    return 0
  fi
  local stack="${AGENT_ROOT}/scripts/dev/dev-stack.sh"
  [[ -f "${stack}" ]] || return 1
  if lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "CHROME_E2E_HEAL: STACK_UI_HALF_DEAD :${FRONTEND_PORT} listening but HTTP unreachable — frontend-only cold start" >&2
  else
    echo "CHROME_E2E_HEAL: shared UI port :${FRONTEND_PORT} dead — frontend-only cold start" >&2
  fi
  MYRM_SUPERVISOR_BYPASS=1 MYRM_E2E_SHPOIB="${MYRM_E2E_SHPOIB:-1}" bash "${stack}" frontend-only ensure || true
}

_private_backend_attach_path() {
  local shared_ui="${E2E_UI_BASE:-http://127.0.0.1:3000}"
  if ! curl -sf --max-time 10 "${API_BASE}/api/v1/health" >/dev/null; then
    fail "private backend not reachable at ${API_BASE}"
  fi
  ok "private backend ${API_BASE}"
  _wait_shared_ui_reachable "${shared_ui}"
  _maybe_seed_providers
  myrm_chrome_e2e_cdp_healthy || fail "Myrm E2E Chrome CDP not reachable — run: ./myrm ready --chrome"
  ok "Myrm E2E Chrome port=${MYRM_CHROME_E2E_PORT}"
  local mux_pid_file="${CDMCP_MUX_STATE_DIR:-$HOME/.local/state/cdmcp-mux}/daemon.pid"
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

# 1. Dev servers (Next.js cold compile can exceed 3s)
if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
  attach_errors="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from runtime_identity import attach_endpoint_errors
print(', '.join(attach_endpoint_errors('${UI_BASE}', '${API_BASE}')))
")"
  if [[ -n "${attach_errors}" ]]; then
    if [[ "${MYRM_PRIVATE_BACKEND:-}" == "1" ]]; then
      # SHPOIB private pools: shared :3000 may flap under parallel chrome_e2e; wait once below.
      private_attach_errors=""
      part=""
      IFS=','
      for part in ${attach_errors}; do
        part="${part#"${part%%[![:space:]]*}"}"
        part="${part%"${part##*[![:space:]]}"}"
        [[ "${part}" == api=* ]] || continue
        if [[ -n "${private_attach_errors}" ]]; then
          private_attach_errors+=", ${part}"
        else
          private_attach_errors="${part}"
        fi
      done
      IFS=$' \t\n'
      attach_errors="${private_attach_errors}"
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
  fi
elif ! curl -sf --max-time 30 "$UI_BASE" >/dev/null; then
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

# 1b. Shared-stack attach is read-only; private-backend pools seed into E2E_API_BASE.
if [[ "${MYRM_CHROME_E2E_ATTACH}" != "1" ]] || [[ "${MYRM_PRIVATE_BACKEND:-}" == "1" ]]; then
  _maybe_seed_providers
fi

# 1c. API-only private backend (cron policy LIVE): no Chrome/CDP/mux required.
if [[ "${MYRM_E2E_API_ONLY:-}" == "1" && "${MYRM_PRIVATE_BACKEND:-}" == "1" ]]; then
  curl -sf --max-time 10 "${API_BASE}/api/v1/health" >/dev/null \
    || fail "private backend not reachable at ${API_BASE}"
  ok "private backend api-only ${API_BASE}"
  echo "CHROME_E2E_READY ui=${UI_BASE} api=${API_BASE} api_only=1"
  exit 0
fi

# 2. Legacy second Chrome / debug launchers
if pgrep -lf 'MyrmChromeMcp' >/dev/null 2>&1; then
  fail "MyrmChromeMcp Chrome detected — quit it; use ./myrm ready --chrome (Myrm E2E profile on :9333)"
fi

# 3. Ensure dedicated E2E Chrome (no Allow — launched with --remote-debugging-port)
[[ -f "${ENSURE_CHROME}" ]] || fail "Missing ${ENSURE_CHROME}"
ensure_out=""
if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
  myrm_chrome_e2e_cdp_healthy || fail "Myrm E2E Chrome CDP not reachable — first Agent must run: ./myrm ready --chrome"
  ensure_out="MYRM_CHROME_E2E_ATTACH: existing CDP port=${MYRM_CHROME_E2E_PORT}"
elif ! ensure_out="$(bash "${ENSURE_CHROME}" 2>&1)"; then
  echo "${ensure_out}" >&2
  fail "Myrm E2E Chrome failed to start — see MYRM_CHROME_E2E_FAIL above"
fi
echo "${ensure_out}"
ok "Myrm E2E Chrome port=${MYRM_CHROME_E2E_PORT}"
CHROME_E2E_CLI_EARLY="${SCRIPT_DIR}/chrome-e2e/cli.sh"
if [[ -f "${CHROME_E2E_CLI_EARLY}" ]]; then
  bash "${CHROME_E2E_CLI_EARLY}" ensure-surface >/dev/null 2>&1 || true
fi

PRUNE_SCRIPT="${SCRIPT_DIR}/prune-myrm-chrome-e2e-blank-tabs.sh"
if [[ -f "${PRUNE_SCRIPT}" ]]; then
  export MYRM_CHROME_E2E_PORT
  if prune_out="$(bash "${PRUNE_SCRIPT}" 2>&1)"; then
    echo "${prune_out}"
    ok "stale infra-owned tabs pruned"
  else
    echo "CHROME_E2E_WARN: prune failed — ${prune_out}" >&2
  fi
fi

ACTIVE_PORT_FILE="${MYRM_CHROME_E2E_ACTIVE_PORT_FILE}"

# 4. mux daemon (parallel Agent tabs)
MUX_STATE_DIR="${CDMCP_MUX_STATE_DIR:-$HOME/.local/state/cdmcp-mux}"
MUX_REQUEST_TIMEOUT_MS="${CDMCP_MUX_REQUEST_TIMEOUT_MS:-180000}"
export CDMCP_MUX_REQUEST_TIMEOUT_MS="${MUX_REQUEST_TIMEOUT_MS}"
MUX_TIMEOUT_STAMP="${MUX_STATE_DIR}/request-timeout-ms"
MUX_DAEMON_TIMEOUT_STAMP="${MUX_STATE_DIR}/request-timeout-ms-at-daemon-start"
MUX_PID_FILE="${MUX_STATE_DIR}/daemon.pid"
MUX_LOG_FILE="${MUX_STATE_DIR}/mux.log"
MUX_START_LOCK_DIR="${MUX_STATE_DIR}/daemon.start.lock"
MUX_SOCKET="${CDMCP_MUX_SOCKET:-${TMPDIR:-/tmp}/mux-$(id -u)/cdmcp-mux.sock}"
MUX_USING=0
if grep -q 'cdmcp-mux-autoconnect' "${HOME}/.cursor/mcp.json" 2>/dev/null \
  || grep -q 'cdmcp-mux-autoconnect' "${HOME}/.cursor-3.1.15/mcp.json" 2>/dev/null \
  || [[ -f "${MUX_PID_FILE}" ]]; then
  MUX_USING=1
fi

_mux_owned_pids() {
  if [[ -f "${MUX_PID_FILE}" ]]; then
    local pid
    pid="$(tr -d '[:space:]' <"${MUX_PID_FILE}")"
    [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && echo "${pid}"
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
  _mux_upstream_ready && _mux_ws_stamp_matches
}

_mux_restart_allowed() {
  [[ "${MYRM_CHROME_E2E_ATTACH}" != "1" ]] || return 1
  local contexts
  contexts="$(_mux_context_count 2>/dev/null)" || return 1
  if [[ "${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-}" == "1" ]]; then
    [[ "${contexts}" == "0" ]] || return 0
  fi
  [[ "${contexts}" == "0" ]] || return 1
  bash "${SCRIPT_DIR}/wave.sh" check-stack-write >/dev/null 2>&1
}

_mux_timeout_restart_allowed() {
  [[ "${MYRM_MUX_ALLOW_TIMEOUT_RESTART:-}" == "1" ]] || return 1
  local contexts
  contexts="$(_mux_context_count 2>/dev/null)" || return 1
  [[ "${contexts}" == "0" ]] || return 1
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

_heal_mux_under_parallel_attach_load() {
  [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]] || return 1
  local active_leases attempt
  active_leases="$(_mux_parallel_active_leases)"
  [[ "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]] || return 1
  for attempt in 1 2 3; do
    if _mux_request_timeout_effective; then
      return 0
    fi
    echo "CHROME_E2E_WARN: mux probe slow (${active_leases} active leases) attempt ${attempt}/3" >&2
    sleep $((attempt * 2))
  done
  if _mux_upstream_ready && _mux_ws_stamp_matches && _mux_daemon_pid_alive; then
    echo "CHROME_E2E_WARN: mux probe timeout under parallel load — skip restart (${active_leases} active leases)" >&2
    return 0
  fi
  return 1
}

_heal_mux_request_timeout_drift() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  if _mux_request_timeout_effective; then
    return 0
  fi
  if _heal_mux_under_parallel_attach_load; then
    return 0
  fi
  local active_leases
  active_leases="$(_mux_parallel_active_leases)"
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" && "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    if _mux_upstream_ready && _mux_ws_stamp_matches && _mux_daemon_pid_alive; then
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

if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
  if [[ -f "${SCRIPT_DIR}/dev-stack.sh" ]]; then
    _smp_apply_pending_drift_if_idle "${MONOREPO_ROOT}" "${SERVER_DIR}" "${SCRIPT_DIR}/dev-stack.sh" || true
    _smp_attach_backend_drift_heal "${MONOREPO_ROOT}" "${SERVER_DIR}" "${SCRIPT_DIR}/dev-stack.sh"
  fi
  _heal_mux_request_timeout_drift
  if [[ "${MYRM_CHROME_E2E_MUX_HEAL_ONLY:-}" == "1" ]]; then
    ok "mux heal-only complete (attach mode, timeout=${MUX_REQUEST_TIMEOUT_MS}ms)"
    exit 0
  fi
  if [[ "${MYRM_PRIVATE_BACKEND:-}" == "1" ]]; then
    _private_backend_attach_path
    exit 0
  fi
  _attach_fast_path
  exit 0
fi

_ensure_mux_daemon

VANILLA_MCP_COUNT=0
if pgrep -f 'npm exec chrome-devtools-mcp' >/dev/null 2>&1; then
  VANILLA_MCP_COUNT="$(pgrep -f 'npm exec chrome-devtools-mcp' | wc -l | tr -d ' ')"
fi
if [[ "${MUX_USING}" -eq 1 ]]; then
  if [[ "${VANILLA_MCP_COUNT}" -gt 0 ]]; then
    fail "Legacy vanilla chrome-devtools-mcp still running (${VANILLA_MCP_COUNT}) — Cmd+Q Cursor, run scripts/dev/enable-chrome-devtools-mcp.sh, reopen"
  fi
  if [[ ! -f "${MUX_PID_FILE}" ]]; then
    fail "cdmcp-mux daemon not running — open any Agent with chrome-devtools MCP once, or run: node scripts/dev/cdmcp-mux-autoconnect/bin/cdmcp-mux-autoconnect.mjs daemon"
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
    fail "Too many vanilla chrome-devtools-mcp processes (${VANILLA_MCP_COUNT}) — enable mux: scripts/dev/enable-chrome-devtools-mcp.sh"
  fi
  if [[ "${VANILLA_MCP_COUNT}" -eq 1 ]]; then
    echo "CHROME_E2E_WARN: vanilla chrome-devtools-mcp detected — parallel Agent tabs will collide; run scripts/dev/enable-chrome-devtools-mcp.sh" >&2
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
  [[ "${require_ready}" == "1" ]] && health_args+=(--require-attach-ready)
  "${PREFLIGHT_PY}" "${runtime_py}" "${health_args[@]}"
}

if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
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
