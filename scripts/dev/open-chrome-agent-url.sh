#!/usr/bin/env bash
# Open a URL in ChromeAgent via pipe-proxy CDP (not daily Chrome AppleScript).
set -euo pipefail

MYRM_CHROME_AGENT_PORT="${MYRM_CHROME_AGENT_PORT:-9410}"
URL="${1:-https://x.com/login}"
ACTIVATE="${CHROME_AGENT_ACTIVATE:-1}"

encoded_url="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "${URL}")"
curl -sf --max-time 15 \
  "http://127.0.0.1:${MYRM_CHROME_AGENT_PORT}/proxy/open?url=${encoded_url}&activate=${ACTIVATE}" \
  >/dev/null || {
  echo "MYRM_CHROME_AGENT_OPEN_FAIL: proxy :${MYRM_CHROME_AGENT_PORT} unreachable — run ./myrm ready --chrome-agent --daemon" >&2
  exit 1
}

echo "MYRM_CHROME_AGENT_OPEN_OK: url=${URL} activate=${ACTIVATE}"
