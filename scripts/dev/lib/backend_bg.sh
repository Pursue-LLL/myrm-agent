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
  local pid_file="${server_dir}/.myrm-dev-backend.pid"
  local log_file="${server_dir}/.myrm-dev-backend.log"
  local health_url="http://127.0.0.1:8080/api/v1/health"

  if [[ -f "${pid_file}" ]]; then
    local old_pid
    old_pid="$(cat "${pid_file}")"
    if kill -0 "${old_pid}" 2>/dev/null; then
      echo "Backend already running (pid ${old_pid})"
      _require_harness_editable_for_monorepo "${server_dir}"
      return 0
    fi
    rm -f "${pid_file}"
  fi

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

  export DEPLOY_MODE="${DEPLOY_MODE:-local}"
  export HOST="${HOST:-127.0.0.1}"
  export PORT="${PORT:-8080}"
  export SQLITE_POOL_SIZE="${SQLITE_POOL_SIZE:-15}"

  _require_harness_editable_for_monorepo "${server_dir}"

  cd "${server_dir}"
  nohup "${py}" run.py >>"${log_file}" 2>&1 &
  echo $! >"${pid_file}"

  for _ in $(seq 1 45); do
    if curl -sf "${health_url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "ERROR: backend not ready on :8080. See ${log_file}" >&2
  return 1
}
