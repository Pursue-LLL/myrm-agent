#!/usr/bin/env bash
# First-time dependency setup after cloning myrm-agent.
# Monorepo (sibling myrm-agent-harness): editable harness via install_harness.sh.
# OSS-only clone: PyPI harness via uv sync.
#
# Usage (from repo root):
#   ./scripts/dev/setup.sh
# Or: myrm setup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
resolve_agent_paths "${REPO_ROOT}"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found. Install: https://docs.astral.sh/uv/" >&2
  exit 1
fi
if ! command -v bun >/dev/null 2>&1; then
  echo "ERROR: bun not found. Install: https://bun.sh" >&2
  exit 1
fi

_resolve_monorepo_harness_installer() {
  local agent_root="$1"
  local parent harness_src installer
  parent="$(cd "${agent_root}/.." && pwd)"
  harness_src="${parent}/myrm-agent-harness/src/myrm_agent_harness"
  installer="${parent}/scripts/maintainer/install_harness.sh"
  if [[ -d "${harness_src}" && -f "${installer}" ]]; then
    echo "${installer}"
    return 0
  fi
  return 1
}

cd "${SERVER_DIR}"
uv python install 3.13

if harness_installer="$(_resolve_monorepo_harness_installer "${REPO_ROOT}")"; then
  echo "📦 Server: monorepo harness detected → editable install..."
  bash "${harness_installer}"
else
  echo "📦 Server: uv sync (PyPI harness)..."
  uv sync --all-extras
fi

echo "🌐 Installing browser runtime (patchright)..."
uv run patchright install chromium || echo "⚠️  Browser install failed (non-fatal). Run: uv run patchright install chromium"

echo "📦 Frontend: bun install..."
cd "${FRONTEND_DIR}"
bun install

echo ""
echo "✅ Setup complete."
echo "  myrm dev    # backend :8080 only"
echo "  myrm start  # backend + frontend → http://localhost:3000"
