#!/usr/bin/env bash
# Backend :8080 + frontend dev server :3000 (both background).
# Usage: myrm start  →  dev-stack ensure (idempotent, mkdir lock serialized)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEV_STACK="${SCRIPT_DIR}/dev-stack.sh"

warn_if_multiple_mcp() {
  local mcp_n=0
  if pgrep -f 'npm exec chrome-devtools-mcp' >/dev/null 2>&1; then
    mcp_n="$(pgrep -f 'npm exec chrome-devtools-mcp' | wc -l | tr -d ' ')"
  fi
  if [[ "${mcp_n}" -gt 1 ]]; then
    echo "⚠️  CHROME_E2E_WARN: Too many chrome-devtools-mcp processes (${mcp_n}) — enable mux: scripts/dev/enable-chrome-devtools-mcp.sh" >&2
  fi
}

if [[ ! -f "${DEV_STACK}" ]]; then
  echo "ERROR: missing ${DEV_STACK}" >&2
  exit 1
fi

bash "${DEV_STACK}" ensure
echo "   Stop: myrm stop"
warn_if_multiple_mcp
