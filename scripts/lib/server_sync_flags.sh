#!/usr/bin/env bash
# Shared uv sync flags for OSS dev setup and Desktop release bundles.
# Installs all optional extras except GPL/heavy bundles excluded from commercial Desktop.
# See myrm-agent-server/pyproject.toml and scripts/ci/desktop-release/sync-server-venv.sh.

SERVER_UV_SYNC_FLAGS=(
  --all-extras
  --no-extra matrix-e2ee
  --no-extra voice-tts
  --no-extra wechat-silk
)

# Same GPL/heavy exclusions without skipping matrix-e2ee (MYRM_HARNESS_SKIP_MATRIX_E2EE=0).
SERVER_UV_SYNC_FLAGS_WITH_MATRIX_E2EE=(
  --all-extras
  --no-extra voice-tts
  --no-extra wechat-silk
)
