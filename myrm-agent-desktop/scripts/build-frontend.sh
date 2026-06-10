#!/usr/bin/env bash
# Resolve myrm-agent-frontend from repo layout (cwd may be src-tauri or myrm-agent-desktop).
set -euo pipefail

MODE="${1:-build}"

if [[ -d ../myrm-agent-frontend ]]; then
  FRONTEND_DIR="$(cd ../myrm-agent-frontend && pwd)"
elif [[ -d ../../myrm-agent-frontend ]]; then
  FRONTEND_DIR="$(cd ../../myrm-agent-frontend && pwd)"
else
  echo "myrm-agent-frontend not found from $(pwd)" >&2
  exit 1
fi

cd "$FRONTEND_DIR"
if [[ "$MODE" == "dev" ]]; then
  exec bun run dev
fi
if [[ -d .next/standalone ]]; then
  echo "Frontend dist already present, skipping BUILD_MODE=tauri build."
  exit 0
fi
exec bun run build:tauri
