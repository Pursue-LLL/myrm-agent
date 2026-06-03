#!/usr/bin/env bash
# Backend only on :8080 (background).
# Usage: myrm dev
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
# shellcheck source=lib/backend_bg.sh
source "${SCRIPT_DIR}/lib/backend_bg.sh"
resolve_agent_paths "${REPO_ROOT}"

LOG_FILE="${SERVER_DIR}/.myrm-dev-backend.log"

if _start_backend_bg "${SERVER_DIR}"; then
  echo "✅ Backend http://127.0.0.1:8080 (log: ${LOG_FILE})"
  echo "   Open UI: myrm start   or   cd myrm-agent-frontend && bun run dev"
else
  exit 1
fi
