#!/usr/bin/env bash
# Mechanical macOS focus check: CDP probes via ChromeAgent must not steal frontmost app.
set -euo pipefail

MYRM_CHROME_AGENT_PORT="${MYRM_CHROME_AGENT_PORT:-9410}"
PROBES="${CHROME_AGENT_FOCUS_PROBES:-10}"

frontmost_app() {
  osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' 2>/dev/null \
    || echo "UNKNOWN"
}

if ! curl -sf --max-time 3 "http://127.0.0.1:${MYRM_CHROME_AGENT_PORT}/proxy/status" >/dev/null; then
  echo "CHROME_AGENT_FOCUS_FAIL: ChromeAgent proxy not reachable on :${MYRM_CHROME_AGENT_PORT} — run ./myrm ready --chrome-agent" >&2
  exit 1
fi

# Ensure we measure focus theft, not "Chrome was already frontmost".
osascript -e 'tell application "Cursor" to activate' >/dev/null 2>&1 || true
sleep 0.4

before="$(frontmost_app)"
for _ in $(seq 1 "${PROBES}"); do
  curl -sf --max-time 5 "http://127.0.0.1:${MYRM_CHROME_AGENT_PORT}/json/list" >/dev/null
done
after="$(frontmost_app)"

if [[ "${after}" == "Google Chrome" && "${before}" != "Google Chrome" ]]; then
  echo "CHROME_AGENT_FOCUS_FAIL: Chrome stole focus (${before} -> ${after}) after ${PROBES} probes" >&2
  exit 1
fi

if [[ "${before}" != "${after}" ]]; then
  echo "CHROME_AGENT_FOCUS_WARN: frontmost changed (${before} -> ${after}) — not Chrome activation" >&2
fi

echo "CHROME_AGENT_FOCUS_OK: before=${before} after=${after} probes=${PROBES}"
