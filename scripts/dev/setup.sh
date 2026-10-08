#!/usr/bin/env bash
# First-time dependency setup after cloning myrm-agent.
# The harness (myrm-agent-harness/) lives in this repository; uv sync installs it as an editable path source.
#
# Usage (from repo root):
#   ./scripts/dev/setup.sh
# Or: myrm setup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
# shellcheck source=../lib/server_sync_flags.sh
source "${REPO_ROOT}/scripts/lib/server_sync_flags.sh"
resolve_agent_paths "${REPO_ROOT}"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found. Install: https://docs.astral.sh/uv/" >&2
  exit 1
fi
if ! command -v bun >/dev/null 2>&1; then
  echo "ERROR: bun not found. Install: https://bun.sh" >&2
  exit 1
fi

cd "${SERVER_DIR}"
uv python install 3.13

echo "📦 Server: uv sync (editable in-repo harness)..."
uv sync "${SERVER_UV_SYNC_FLAGS[@]}"

echo "🌐 Installing browser runtime (patchright)..."
uv run patchright install chromium || echo "⚠️  Browser install failed (non-fatal). Run: uv run patchright install chromium"

echo "📦 Frontend: bun install..."
cd "${FRONTEND_DIR}"
bun install
bash "${SCRIPT_DIR}/ensure-next-native-swc.sh"

echo ""
echo "✅ Setup complete."
echo "  myrm dev    # backend :8080 only"
echo "  myrm start  # backend + frontend → http://localhost:3000"
