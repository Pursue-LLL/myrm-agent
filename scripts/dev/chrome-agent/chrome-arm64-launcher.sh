#!/usr/bin/env bash
# Force arm64 Chrome on Apple Silicon (avoid Rosetta x64 spawn instability).
set -euo pipefail
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
exec arch -arm64 "${CHROME}" "$@"
