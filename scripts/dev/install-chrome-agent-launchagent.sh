#!/usr/bin/env bash
# Install/start the ChromeAgent LaunchAgent (KeepAlive, survives shell exit).
# Delegates to the machine-level installer so the plist always points at
# ~/.local/lib/myrm-chrome-agent/current (checkout-independent).
# Invoked via: ./myrm ready --chrome-agent --daemon
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/chrome-agent/myrm-chrome-agent.sh" install
