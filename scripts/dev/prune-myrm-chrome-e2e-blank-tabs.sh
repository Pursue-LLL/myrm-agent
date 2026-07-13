#!/usr/bin/env bash
# Close only stale preflight-owned targets; unknown tabs are never guessed by URL.
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

exec "${PREFLIGHT_PY}" "${SCRIPT_DIR}/lib/cdp_transient_targets.py" \
  --prune \
  --cdp-port "${MYRM_CHROME_E2E_PORT}"
