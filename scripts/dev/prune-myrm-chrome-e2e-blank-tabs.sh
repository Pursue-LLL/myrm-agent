#!/usr/bin/env bash
# Close stale infra-owned targets and unbound blank orphan CDP pages.
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

infra_out="$("${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/infra_browser_registry.py" \
  --prune \
  --cdp-port "${MYRM_CHROME_E2E_PORT}" 2>&1)" || {
  echo "${infra_out}" >&2
  exit 1
}
echo "${infra_out}"

HYGIENE_PY="${SCRIPT_DIR}/lib/browser_tab_hygiene.py"
if [[ -f "${HYGIENE_PY}" ]]; then
  threshold="${MYRM_CHROME_E2E_TAB_PRUNE_THRESHOLD:-20}"
  orphan_out="$("${PREFLIGHT_PY}" "${HYGIENE_PY}" \
    --prune-orphans \
    --threshold "${threshold}" \
    --cdp-port "${MYRM_CHROME_E2E_PORT}" 2>&1)" || {
    echo "CHROME_E2E_WARN: orphan tab prune failed — ${orphan_out}" >&2
    exit 0
  }
  echo "${orphan_out}"
fi
