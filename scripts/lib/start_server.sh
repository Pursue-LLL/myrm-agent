#!/usr/bin/env bash
# [INPUT] SERVER_DIR (POS: myrm-agent-server 根目录)
# [OUTPUT] start_myrm_server: exec run.py via .venv python or uv run
# [POS] 统一 OSS CLI 与 dev run_server 的启动策略，避免 uv 重解析。

start_myrm_server() {
  local server_dir="$1"
  shift
  cd "${server_dir}"
  export DEPLOY_MODE="${DEPLOY_MODE:-local}"

  local wants_webui=0
  for arg in "$@"; do
    [[ "$arg" == "--webui" ]] && wants_webui=1
  done
  # Default dev: API on 127.0.0.1:8080 — matches Next.js `bun run dev` proxy (API_PORT=8080).
  if [[ "${wants_webui}" -eq 0 ]]; then
    export HOST="${HOST:-127.0.0.1}"
    export PORT="${PORT:-8080}"
  fi

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
    exec uv run --no-sync run.py "$@"
  fi
  echo "ERROR: neither ${server_dir}/.venv python nor uv found. Re-run scripts/install.sh" >&2
  exit 1
}
