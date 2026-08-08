#!/usr/bin/env bash
# Subprocess entry for timed shared UI heal (R158 — bash -c cannot see sourced functions).
set -euo pipefail
SCRIPT_DIR="${SCRIPT_DIR:?SCRIPT_DIR required}"
UI_BASE="${UI_BASE:-http://127.0.0.1:3000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
STATE_DIR="$(dev_state_dir)"
FRONTEND_DIR="${MYRM_FRONTEND_DIR:-$(cd "${SCRIPT_DIR}/../../myrm-agent-frontend" && pwd)}"
# shellcheck source=../myrm-chrome-e2e-lib.sh
source "${SCRIPT_DIR}/myrm-chrome-e2e-lib.sh"
# shellcheck source=dev_state_paths.sh
source "${SCRIPT_DIR}/lib/dev_state_paths.sh"
export_myrm_next_dist_dir
FRONTEND_LOCK="$(resolve_frontend_lock_path "${FRONTEND_DIR}")"
FRONTEND_LOG="${STATE_DIR}/frontend.log"
APP_URL="${UI_BASE}"
MYRM_DEV_STACK="${MYRM_DEV_STACK:-${SCRIPT_DIR}/dev-stack.sh}"
export MYRM_DEV_STACK
export MYRM_UI_HEAL_POST_ENSURE_MAX_SEC="${MYRM_UI_HEAL_POST_ENSURE_MAX_SEC:-120}"
export MYRM_STACK_FRONTEND_WAIT_SEC="${MYRM_STACK_FRONTEND_WAIT_SEC:-360}"
# shellcheck source=frontend-warmup.sh
source "${SCRIPT_DIR}/lib/frontend-warmup.sh"
_heal_shared_ui_if_stale
