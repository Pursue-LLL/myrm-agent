#!/usr/bin/env bash
# Desktop release: production server venv for PyInstaller (no dev/test tools).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT/myrm-agent-server"

uv sync --frozen --all-extras --no-group dev --no-extra matrix-e2ee
uv pip install pyinstaller
