#!/usr/bin/env bash
# Close stale infra-owned targets and unbound blank orphan CDP pages via Browser Orchestrator.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=myrm-chrome-e2e-lib.sh
source "${SCRIPT_DIR}/myrm-chrome-e2e-lib.sh"

if ! myrm_chrome_e2e_cdp_healthy; then
  echo "MYRM_CHROME_PRUNE_SKIP: CDP not ready on port ${MYRM_CHROME_E2E_PORT}"
  exit 0
fi

PREFLIGHT_PY="${SCRIPT_DIR}/../../myrm-agent-server/.venv/bin/python"
if [[ ! -x "${PREFLIGHT_PY}" ]]; then
  PREFLIGHT_PY="python3"
fi

ORCHESTRATOR_PY="${SCRIPT_DIR}/lib/idle_tab_hygiene.py"
export PYTHONPATH="${SCRIPT_DIR}/lib${PYTHONPATH:+:${PYTHONPATH}}"
orch_out="$("${PREFLIGHT_PY}" "${ORCHESTRATOR_PY}" 2>&1)" || {
  echo "CHROME_E2E_WARN: orchestrator prune failed — ${orch_out}" >&2
  exit 0
}
echo "${orch_out}"
