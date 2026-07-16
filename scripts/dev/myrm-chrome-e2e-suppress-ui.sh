#!/usr/bin/env bash
# Hide Myrm E2E Chrome UI and restore the previous frontmost app (macOS).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=myrm-chrome-e2e-lib.sh
source "${SCRIPT_DIR}/myrm-chrome-e2e-lib.sh"

myrm_chrome_e2e_suppress_ui "${MYRM_CHROME_E2E_SAVED_FRONTMOST_PID:-}"
