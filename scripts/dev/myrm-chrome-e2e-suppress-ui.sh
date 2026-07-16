#!/usr/bin/env bash
# Deprecated wrapper — use chrome-e2e/cli.sh recover-focus.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/chrome-e2e/cli.sh" recover-focus
