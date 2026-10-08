#!/usr/bin/env bash
# Desktop release: production server venv for PyInstaller (no dev/test tools).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=../../lib/server_sync_flags.sh
source "${ROOT}/scripts/lib/server_sync_flags.sh"
cd "$ROOT/myrm-agent-server"

# Exclude matrix-e2ee (crypto weight) and GPL optional extras from desktop/commercial bundles.
sync_flags=("${SERVER_UV_SYNC_FLAGS[@]}" --no-group dev)

# uv.lock resolves the harness as an editable path source; the bundle ships its wheel instead,
# so every harness dependency still comes from the lock while the harness itself is not editable.
uv sync --frozen "${sync_flags[@]}" --no-install-package myrm-agent-harness
wheel_dir="$(mktemp -d)"
trap 'rm -rf "${wheel_dir}"' EXIT
(cd "$ROOT/myrm-agent-harness" && uv build --wheel -o "${wheel_dir}")
uv pip install --no-deps "${wheel_dir}"/myrm_agent_harness-*.whl
uv pip install pyinstaller
