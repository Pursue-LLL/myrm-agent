#!/usr/bin/env bash
# Start myrm-agent-server on :8080 in background. Sets SERVER_DIR, writes pid/log under server dir.
set -euo pipefail

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
