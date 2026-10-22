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

if [[ ! -f .next/standalone/myrm-agent-frontend/server.js ]]; then
  bun run build:tauri
fi

# Next standalone emits server.js but deliberately excludes .next/static and public.
# Without these, the app serves HTML whose JS/CSS chunks 404 and the WebView is black.
STANDALONE_DIR=".next/standalone/myrm-agent-frontend"
rm -rf "$STANDALONE_DIR/.next/static" "$STANDALONE_DIR/public"
mkdir -p "$STANDALONE_DIR/.next"
cp -R .next/static "$STANDALONE_DIR/.next/static"
cp -R public "$STANDALONE_DIR/public"

echo "Prepared standalone assets: .next/static and public"
