#!/usr/bin/env bash
# Start myrm-agent-server without uv re-resolve when .venv exists.
#
# Usage (from myrm-agent repo root):
#   ./scripts/dev/run_server.sh              # dev API :8080 (pair with bun run dev)
#   ./scripts/dev/run_server.sh --webui      # standalone WebUI :25808
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
# shellcheck source=../lib/start_server.sh
source "${REPO_ROOT}/scripts/lib/start_server.sh"
resolve_agent_paths "${REPO_ROOT}"

if [[ -x "${SERVER_DIR}/.venv/bin/python" ]]; then
  echo "🚀 Starting server via ${SERVER_DIR}/.venv/bin/python (no uv re-resolve)"
elif [[ -x "${SERVER_DIR}/.venv/Scripts/python.exe" ]]; then
  echo "🚀 Starting server via ${SERVER_DIR}/.venv/Scripts/python.exe (no uv re-resolve)"
elif command -v uv >/dev/null 2>&1; then
  echo "🚀 No .venv yet — starting via uv run run.py"
else
  echo "ERROR: neither ${SERVER_DIR}/.venv nor uv found." >&2
  echo "  Run: ./scripts/dev/setup.sh  or  myrm setup" >&2
  exit 1
fi

start_myrm_server "${SERVER_DIR}" "$@"
