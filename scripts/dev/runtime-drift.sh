#!/usr/bin/env bash
# Mechanical RUNTIME_DRIFT check — compare live stack identity to a snapshot runtimeId.
# Exit 0: match; exit 2: drift (RUNTIME_DRIFT); exit 1: usage/error.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVER_DIR="${AGENT_ROOT}/myrm-agent-server"
RUNTIME_PY="${SCRIPT_DIR}/lib/runtime_identity.py"
PY="${SERVER_DIR}/.venv/bin/python"
if [[ ! -x "${PY}" ]]; then
  PY="python3"
fi

EXPECTED=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --expect)
      [[ $# -ge 2 ]] || {
        echo "RUNTIME_DRIFT_FAIL: --expect requires a value" >&2
        exit 1
      }
      EXPECTED="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: ./myrm runtime-drift --expect <runtimeId>"
      echo "  Compare current dev stack runtimeId to the snapshot from CHROME_E2E_HEALTH_JSON."
      echo "  Exit 0 on match; exit 2 on RUNTIME_DRIFT."
      exit 0
      ;;
    *)
      echo "RUNTIME_DRIFT_FAIL: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${EXPECTED}" ]]; then
  echo "RUNTIME_DRIFT_FAIL: missing --expect <runtimeId>" >&2
  exit 1
fi

[[ -f "${RUNTIME_PY}" ]] || {
  echo "RUNTIME_DRIFT_FAIL: missing ${RUNTIME_PY}" >&2
  exit 1
}

exec "${PY}" "${RUNTIME_PY}" --drift --expect "${EXPECTED}"
