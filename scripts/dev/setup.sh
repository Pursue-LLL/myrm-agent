#!/usr/bin/env bash
# First-time dependency setup after cloning myrm-agent (harness from PyPI).
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

echo "📦 Server: uv sync (PyPI harness)..."
cd "${SERVER_DIR}"
uv python install 3.13
uv sync --all-extras

echo "📦 Frontend: bun install..."
cd "${FRONTEND_DIR}"
bun install

echo ""
echo "✅ Setup complete."
echo "  myrm dev && cd myrm-agent-frontend && bun run dev"
echo "  (Foreground backend: myrm start | All-in-one: myrm start --standalone)"
