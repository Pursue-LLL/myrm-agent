#!/usr/bin/env bash
# ============================================================================
# MyrmAgent remote installer — canonical OSS one-liner entry.
#
#   curl -fsSL https://myrmagent.ai/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/Pursue-LLL/myrm-agent/main/scripts/install-remote.sh | bash
#
# Windows (PowerShell):
#   irm https://myrmagent.ai/install.ps1 | iex
#   irm https://raw.githubusercontent.com/Pursue-LLL/myrm-agent/main/scripts/install-remote.ps1 | iex
#
# Clones (or updates) this repo, then runs scripts/install.sh.
# ============================================================================

set -e

REPO_DIR="${MYRM_INSTALL_DIR:-$HOME/.myrm/myrm-agent}"
REPO_URL="${MYRM_REPO_URL:-https://github.com/Pursue-LLL/myrm-agent.git}"

if [[ -d "${REPO_DIR}/myrm-agent-server" ]]; then
  cd "${REPO_DIR}"
  if [[ -d .git ]]; then
    git pull --ff-only 2>/dev/null || true
  fi
else
  mkdir -p "$(dirname "${REPO_DIR}")"
  if [[ -d "${REPO_DIR}/.git" ]]; then
    cd "${REPO_DIR}"
    git pull --ff-only 2>/dev/null || true
  else
    git clone --depth 1 "${REPO_URL}" "${REPO_DIR}"
    cd "${REPO_DIR}"
  fi
fi

export PATH="${HOME}/.local/bin:${HOME}/.bun/bin:${HOME}/.cargo/bin:${PATH}"
exec bash scripts/install.sh
