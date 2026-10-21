#!/usr/bin/env bash
# Cursor Agent MCP isolation doctor (§25.8) — ChromeAgent :9410 contract (not E2E :9333).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PREFLIGHT_PY="${AGENT_ROOT}/myrm-agent-server/.venv/bin/python"
if [[ ! -x "${PREFLIGHT_PY}" ]]; then
  PREFLIGHT_PY="python3"
fi

exec env PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
  "${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/e2e_core/cursor_mcp_isolation.py" "$@"
