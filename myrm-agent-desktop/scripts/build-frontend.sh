#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-build}"

DESKTOP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_ROOT/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/myrm-agent-frontend"

if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "myrm-agent-frontend not found at $FRONTEND_DIR" >&2
  exit 1
fi

cd "$FRONTEND_DIR"

if [[ "$MODE" == "dev" ]]; then
  exec bun run dev
fi

if [[ -f .next/standalone/myrm-agent-frontend/server.js ]]; then
  echo "Next standalone server already present, skipping build:tauri."
  exit 0
fi

exec bun run build:tauri
