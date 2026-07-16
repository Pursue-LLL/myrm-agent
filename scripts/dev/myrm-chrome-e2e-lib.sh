#!/usr/bin/env bash
# Shared Myrm E2E Chrome — thin re-export of chrome-e2e/ SSOT modules.
set -euo pipefail

_CHROME_E2E_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=chrome-e2e/runtime.sh
source "${_CHROME_E2E_LIB_DIR}/chrome-e2e/runtime.sh"
# shellcheck source=chrome-e2e/focus.sh
source "${_CHROME_E2E_LIB_DIR}/chrome-e2e/focus.sh"
# shellcheck source=chrome-e2e/lifecycle.sh
source "${_CHROME_E2E_LIB_DIR}/chrome-e2e/lifecycle.sh"

myrm_chrome_e2e_default_app() { chrome_e2e_default_app; }
myrm_chrome_e2e_launch_background() { chrome_e2e_launch_background; }
myrm_chrome_e2e_save_frontmost_pid() { chrome_e2e_focus_capture; }
myrm_chrome_e2e_owner_pid() { chrome_e2e_owner_pid; }
myrm_chrome_e2e_suppress_ui() { chrome_e2e_lifecycle_transition "mcp-page" "${1:-}"; }
myrm_chrome_e2e_cdp_healthy() { chrome_e2e_cdp_healthy; }
myrm_chrome_e2e_process_owns_port() { chrome_e2e_process_owns_port; }
