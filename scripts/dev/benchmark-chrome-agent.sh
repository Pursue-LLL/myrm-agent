#!/usr/bin/env bash
# Benchmark ChromeAgent proxy latency + macOS focus (before/after tuning).
set -euo pipefail

MYRM_CHROME_AGENT_PORT="${MYRM_CHROME_AGENT_PORT:-9410}"
PROBES="${CHROME_AGENT_BENCH_PROBES:-10}"

frontmost_app() {
  osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' 2>/dev/null \
    || echo "UNKNOWN"
}

bench_curl() {
  local label="$1"
  local total_ms=0
  local i
  for i in $(seq 1 "${PROBES}"); do
    local start end elapsed
    start="$(python3 -c 'import time; print(int(time.time()*1000))')"
    curl -sf --max-time 10 "http://127.0.0.1:${MYRM_CHROME_AGENT_PORT}/json/list" >/dev/null
    end="$(python3 -c 'import time; print(int(time.time()*1000))')"
    elapsed=$((end - start))
    total_ms=$((total_ms + elapsed))
  done
  echo "BENCH_CURL label=${label} probes=${PROBES} total_ms=${total_ms} avg_ms=$((total_ms / PROBES))"
}

bench_focus() {
  osascript -e 'tell application "Cursor" to activate' >/dev/null 2>&1 || true
  sleep 0.3
  local before after
  before="$(frontmost_app)"
  bench_curl "focus-embedded" >/dev/null
  after="$(frontmost_app)"
  echo "BENCH_FOCUS before=${before} after=${after} probes=${PROBES}"
  if [[ "${after}" == "Google Chrome" && "${before}" != "Google Chrome" ]]; then
    echo "BENCH_FOCUS_FAIL: Chrome stole focus" >&2
    return 1
  fi
}

if ! curl -sf --max-time 3 "http://127.0.0.1:${MYRM_CHROME_AGENT_PORT}/proxy/status" >/dev/null; then
  echo "BENCH_FAIL: proxy :${MYRM_CHROME_AGENT_PORT} not reachable" >&2
  exit 1
fi

bench_curl "json-list"
bench_focus
