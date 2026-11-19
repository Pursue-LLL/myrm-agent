#!/usr/bin/env bash
# Locates the machine-level ChromeAgent CLI.
#
# ChromeAgent (the :9410 browser service) is built, installed and upgraded by the standalone
# chrome-agent project; this repo only drives its `chrome-agent` CLI and consumes the :9410
# endpoint. The CLI is linked into the real user's ~/.local/bin, which a sandboxed HOME or PATH
# (e.g. Cursor's) can hide, so that location is tried before PATH.

# shellcheck source=dev_state_paths.sh
source "${BASH_SOURCE[0]%/*}/dev_state_paths.sh"

# Prints the CLI path; fails with an actionable message when the CLI is not installed.
chrome_agent_cli() {
  local cli
  cli="$(real_user_home)/.local/bin/chrome-agent"
  [[ -x "${cli}" ]] || cli="$(command -v chrome-agent || true)"
  if [[ -z "${cli}" ]]; then
    echo "MYRM_CHROME_AGENT_FAIL: chrome-agent CLI not found — ChromeAgent is installed from the standalone chrome-agent project: link its chrome-agent script to ~/.local/bin/chrome-agent, then run: chrome-agent upgrade" >&2
    return 1
  fi
  printf '%s' "${cli}"
}
