#!/usr/bin/env bash
# Wave orchestrator CLI — open/close/status, lease acquire/release, STACK_WRITE gate.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVER_DIR="${AGENT_ROOT}/myrm-agent-server"
PY="${SERVER_DIR}/.venv/bin/python"
if [[ ! -x "${PY}" ]]; then
  PY="python3"
fi

export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"
exec "${PY}" -m wave_orchestrator.cli "$@"
