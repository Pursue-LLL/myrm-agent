#!/usr/bin/env bash
# Cursor Agent MCP isolation doctor (§25.8) — daily Chrome auto-connect contract.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PREFLIGHT_PY="${AGENT_ROOT}/myrm-agent-server/.venv/bin/python"
if [[ ! -x "${PREFLIGHT_PY}" ]]; then
  PREFLIGHT_PY="python3"
fi

exec "${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/cursor_mcp_isolation.py" "$@"
