#!/usr/bin/env bash
# [INPUT] SERVER_DIR (POS: myrm-agent-server 根目录)
# [OUTPUT] start_myrm_server: exec run.py via .venv python or uv run
# [POS] 统一 OSS CLI 与 dev run_server 的启动策略，避免 uv 重解析。

start_myrm_server() {
  local server_dir="$1"
  shift
  cd "${server_dir}"
  export DEPLOY_MODE="${DEPLOY_MODE:-local}"
  export WEBUI_MODE="${WEBUI_MODE:-true}"

  local py=""
  if [[ -x "${server_dir}/.venv/bin/python" ]]; then
    py="${server_dir}/.venv/bin/python"
  elif [[ -x "${server_dir}/.venv/Scripts/python.exe" ]]; then
    py="${server_dir}/.venv/Scripts/python.exe"
  fi
  if [[ -n "${py}" ]]; then
    exec "${py}" run.py "$@"
  fi
  if command -v uv >/dev/null 2>&1; then
    exec uv run run.py "$@"
  fi
  echo "ERROR: neither ${server_dir}/.venv python nor uv found. Re-run scripts/install.sh" >&2
  exit 1
}
