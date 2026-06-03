#!/usr/bin/env bash
# First-time setup for vortexai / open-perplexity monorepo (submodules + editable harness).
set -euo pipefail

MAINTAINER_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$(dirname "${MAINTAINER_DIR}")"
# shellcheck source=../lib/resolve_agent_root.sh
source "${SCRIPT_DIR}/lib/resolve_agent_root.sh"
# shellcheck source=../lib/resolve_monorepo_root.sh
source "${SCRIPT_DIR}/lib/resolve_monorepo_root.sh"

MONOREPO_ROOT="$(resolve_monorepo_root "${SCRIPT_DIR}/..")" || {
  echo "ERROR: run ./myrm setup from vortexai root (MYRM_MONOREPO_ROOT or parent .gitmodules)." >&2
  exit 1
}

export MYRM_MONOREPO_ROOT="${MONOREPO_ROOT}"
cd "${MONOREPO_ROOT}"

if [[ -f .gitmodules ]]; then
  git submodule sync myrm-agent 2>/dev/null || true
  git submodule update --init myrm-agent
fi

"${MAINTAINER_DIR}/install_harness_dev.sh"

resolve_agent_paths "${MONOREPO_ROOT}"
if command -v bun >/dev/null 2>&1 && [[ -f "${FRONTEND_DIR}/package.json" ]]; then
  (cd "${FRONTEND_DIR}" && bun install)
fi

echo "Done → ./myrm start"
