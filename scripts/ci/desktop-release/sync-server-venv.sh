#!/usr/bin/env bash
# Desktop release: production server venv for PyInstaller (no dev/test tools).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT/myrm-agent-server"

sync_flags=(--all-extras --no-group dev --no-extra matrix-e2ee)
if [[ "${GITHUB_ACTIONS:-}" == "true" && "${MYRM_HARNESS_INSTALL_MODE:-}" == "pypi" ]]; then
  # uv.lock may pin Tsinghua mirror wheel URLs; GHA runners must use PyPI.org (mirror 403 on harness).
  echo "[sync-server-venv] CI pypi mode: resolve from https://pypi.org/simple"
  UV_DEFAULT_INDEX="https://pypi.org/simple" uv sync "${sync_flags[@]}" --default-index https://pypi.org/simple
else
  uv sync --frozen "${sync_flags[@]}"
fi
uv pip install pyinstaller
