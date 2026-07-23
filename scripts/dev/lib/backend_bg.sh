#!/usr/bin/env bash
# Start myrm-agent-server on :8080 in background. Sets SERVER_DIR, writes pid/log under server dir.
set -euo pipefail

_require_harness_editable_for_monorepo() {
  local server_dir="$1"
  local agent_root harness_src expected_src py mode pkg_dir

  if [[ "${MYRM_SKIP_HARNESS_EDITABLE_CHECK:-0}" == "1" ]]; then
    return 0
  fi

  agent_root="$(cd "${server_dir}/.." && pwd)"
  harness_src="$(cd "${agent_root}/.." 2>/dev/null && pwd)/myrm-agent-harness/src/myrm_agent_harness"
  if [[ ! -d "${harness_src}" ]]; then
    return 0
  fi
  expected_src="$(cd "${harness_src}" && pwd)"

  py=""
  if [[ -x "${server_dir}/.venv/bin/python" ]]; then
    py="${server_dir}/.venv/bin/python"
  elif [[ -x "${server_dir}/.venv/Scripts/python.exe" ]]; then
    py="${server_dir}/.venv/Scripts/python.exe"
  fi
  if [[ -z "${py}" ]]; then
    return 0
  fi

  if ! {
    read -r mode
    read -r pkg_dir
  } < <(
    cd "${server_dir}" && "${py}" -c "
import pathlib
import myrm_agent_harness
from myrm_agent_harness._distribution import get_distribution_mode
from myrm_agent_harness.agent.artifacts.ui_registry import bind_run_message_id  # noqa: F401
pkg = pathlib.Path(myrm_agent_harness.__file__).resolve().parent
print(get_distribution_mode().value)
print(pkg)
" 2>/dev/null
  ); then
    echo "ERROR: monorepo harness source present but myrm_agent_harness import failed." >&2
    echo "   Run: from open-perplexity root  ./myrm harness install  then retry." >&2
    echo "   If a stale backend is running:  myrm stop" >&2
    exit 1
  fi

  if [[ "${mode}" != "source" || "${pkg_dir}" != "${expected_src}" ]]; then
    echo "ERROR: Server venv harness is not monorepo editable source." >&2
    echo "   mode=${mode}  import=${pkg_dir}" >&2
    echo "   expected=${expected_src}" >&2
    echo "   pytest may pass while live agent-stream misses ui_update (stale wheel)." >&2
    echo "   Fix: from open-perplexity root run  ./myrm harness install  then  myrm stop  and restart." >&2
    echo "   PyPI consumer test only:  MYRM_SKIP_HARNESS_EDITABLE_CHECK=1 myrm dev" >&2
    exit 1
  fi
}

_start_backend_bg() {
  local server_dir="$1"
  local state_dir="${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}"
  local backend_port="${MYRM_BACKEND_PORT:-${PORT:-8080}}"
  local pid_file="${MYRM_BACKEND_PID_FILE:-${state_dir}/backend.pid}"
  local log_file="${MYRM_BACKEND_LOG_FILE:-${state_dir}/backend.log}"
  local identity_file="${MYRM_BACKEND_IDENTITY_FILE:-${state_dir}/backend-process.json}"
  local identity_helper
  identity_helper="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/process_identity.py"
  local runtime_id="${MYRM_RUNTIME_NAMESPACE:-shared}"
  local health_url="${E2E_API_BASE:-http://127.0.0.1:${backend_port}}/api/v1/health"
  mkdir -p "${state_dir}"

  local py=""
  if [[ -x "${server_dir}/.venv/bin/python" ]]; then
    py="${server_dir}/.venv/bin/python"
  elif [[ -x "${server_dir}/.venv/Scripts/python.exe" ]]; then
    py="${server_dir}/.venv/Scripts/python.exe"
  fi
  if [[ -z "${py}" ]]; then
    echo "ERROR: no .venv python. Run: myrm setup" >&2
    return 1
  fi

  if [[ -f "${pid_file}" ]]; then
    local old_pid
    old_pid="$(cat "${pid_file}")"
    if kill -0 "${old_pid}" 2>/dev/null; then
      if ! "${py}" "${identity_helper}" verify \
        --identity-file "${identity_file}" \
        --expected-pid "${old_pid}" \
        --expected-runtime-id "${runtime_id}" >/dev/null; then
        echo "ERROR: backend pid exists without matching process ownership: ${old_pid}" >&2
        return 1
      fi
      _require_harness_editable_for_monorepo "${server_dir}"
      local stack_epoch_lib stored_fp current_fp
      stack_epoch_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-epoch.sh"
      if [[ -f "${stack_epoch_lib}" ]]; then
        # shellcheck source=stack-epoch.sh
        source "${stack_epoch_lib}"
        if [[ ! -f "$(_stack_epoch_file)" ]]; then
          _bump_stack_epoch "${old_pid}" "${server_dir}" >/dev/null || true
        fi
        stored_fp="$(_read_stack_epoch_source_fingerprint)"
        current_fp="$(_backend_source_fingerprint "${server_dir}")"
        if [[ -n "${current_fp}" && ( -z "${stored_fp}" || "${stored_fp}" != "${current_fp}" ) ]]; then
          local monorepo_root agent_root active_leases policy_py defer_reason
          agent_root="$(cd "${server_dir}/.." && pwd)"
          monorepo_root="$(cd "${agent_root}/.." && pwd)"
          active_leases="$(_wave_active_lease_count "${monorepo_root}")"
          if [[ "${active_leases}" != "0" ]]; then
            policy_py="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack_mutation_policy.py"
            defer_reason="backend_source_drift"
            if [[ -z "${stored_fp}" ]]; then
              defer_reason="backend_source_fingerprint_missing"
            fi
            python3 "${policy_py}" record-pending \
              --state-dir "${state_dir}" \
              --reason "${defer_reason}" \
              --server-dir "${server_dir}" >/dev/null 2>&1 || true
            echo "CHROME_E2E_ATTACH: defer backend reload (${active_leases} active wave leases)" >&2
            echo "Backend already running (pid ${old_pid})"
            return 0
          fi
          if [[ -z "${stored_fp}" ]]; then
            echo "STACK_WARN: shared backend missing source_fingerprint — reloading pid=${old_pid}" >&2
          else
            echo "STACK_WARN: shared backend source drift detected — reloading pid=${old_pid}" >&2
          fi
          kill -TERM "${old_pid}" 2>/dev/null || true
          local wait_i
          for wait_i in $(seq 1 20); do
            kill -0 "${old_pid}" 2>/dev/null || break
            sleep 0.25
          done
          if kill -0 "${old_pid}" 2>/dev/null; then
            kill -KILL "${old_pid}" 2>/dev/null || true
          fi
          rm -f "${pid_file}" "${identity_file}"
        else
          echo "Backend already running (pid ${old_pid})"
          return 0
        fi
      else
        echo "Backend already running (pid ${old_pid})"
        return 0
      fi
    fi
    rm -f "${pid_file}"
    rm -f "${identity_file}"
  fi

  export DEPLOY_MODE="${DEPLOY_MODE:-local}"
  export HOST="${HOST:-127.0.0.1}"
  export PORT="${backend_port}"
  export SQLITE_POOL_SIZE="${SQLITE_POOL_SIZE:-15}"
  export MYRM_STACK_EPOCH_FILE="${MYRM_STACK_EPOCH_FILE:-${state_dir}/stack-epoch.json}"

  _require_harness_editable_for_monorepo "${server_dir}"

  cd "${server_dir}"
  # Dev log is append-only; truncate on fresh start to avoid unbounded growth.
  : >"${log_file}"
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "${py}" run.py >>"${log_file}" 2>&1 &
  else
    nohup "${py}" run.py >>"${log_file}" 2>&1 &
  fi
  local new_pid
  new_pid=$!
  echo "${new_pid}" >"${pid_file}"
  if ! "${py}" "${identity_helper}" record \
    --pid "${new_pid}" \
    --identity-file "${identity_file}" \
    --runtime-id "${runtime_id}" \
    --role backend \
    --expected-command-token run.py >/dev/null; then
    kill -TERM "${new_pid}" 2>/dev/null || true
    rm -f "${pid_file}" "${identity_file}"
    echo "ERROR: failed to record backend process ownership" >&2
    return 1
  fi

  local health_wait_sec=45
  if [[ "${MYRM_E2E_ISOLATED:-}" == "1" || "${MYRM_PRIVATE_BACKEND:-}" == "1" || "${MYRM_DEV_STATE_DIR:-}" != "${HOME}/.local/state/myrm-dev" ]]; then
    health_wait_sec="${MYRM_BACKEND_HEALTH_WAIT_SEC:-60}"
  fi

  for _ in $(seq 1 "${health_wait_sec}"); do
    if curl -sf "${health_url}" >/dev/null 2>&1; then
      local stack_epoch_lib
      stack_epoch_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-epoch.sh"
      if [[ -f "${stack_epoch_lib}" ]]; then
        # shellcheck source=stack-epoch.sh
        source "${stack_epoch_lib}"
        _bump_stack_epoch "${new_pid}" "${server_dir}" >/dev/null || true
      fi
      return 0
    fi
    sleep 1
  done

  echo "ERROR: backend not ready on :${backend_port}. See ${log_file}" >&2
  return 1
}
