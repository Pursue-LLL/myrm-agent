#!/usr/bin/env bash
# Install macOS LaunchAgent for ChromeAgent pipe-proxy (KeepAlive, survives shell exit).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=lib/dev_state_paths.sh
source "${AGENT_ROOT}/scripts/dev/lib/dev_state_paths.sh"
export_spawn_home

MYRM_CHROME_AGENT_PORT="${MYRM_CHROME_AGENT_PORT:-9410}"
MYRM_CHROME_AGENT_DATA_DIR="${MYRM_CHROME_AGENT_DATA_DIR:-${HOME}/Library/Application Support/Myrm/ChromeAgent}"
MYRM_CHROME_AGENT_INITIAL_URL="${MYRM_CHROME_AGENT_INITIAL_URL:-about:blank}"
PROXY_DIR="${SCRIPT_DIR}/chrome-agent"
CHROME_LAUNCHER="$(cd "${PROXY_DIR}" && pwd)/chrome-arm64-launcher.sh"
LOG_FILE="${MYRM_CHROME_AGENT_LOG_FILE:-$(dev_state_dir)/chrome-agent-proxy.log}"
LABEL="com.myrm.chrome-agent"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

NODE_BIN="${MYRM_NODE_BIN:-$(command -v node || true)}"
[[ -n "${NODE_BIN}" && -x "${NODE_BIN}" ]] || {
  echo "MYRM_CHROME_AGENT_LAUNCHAGENT_FAIL: node not found" >&2
  exit 1
}

mkdir -p "$(dev_state_dir)" "${HOME}/Library/LaunchAgents" "${MYRM_CHROME_AGENT_DATA_DIR}"

if [[ ! -d "${PROXY_DIR}/node_modules/ws" ]]; then
  (cd "${PROXY_DIR}" && npm install --ignore-scripts)
fi

cat >"${PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${NODE_BIN}</string>
    <string>${PROXY_DIR}/pipe-cdp-proxy.mjs</string>
    <string>--port</string>
    <string>${MYRM_CHROME_AGENT_PORT}</string>
    <string>--chrome-path</string>
    <string>${CHROME_LAUNCHER}</string>
    <string>--user-data-dir</string>
    <string>${MYRM_CHROME_AGENT_DATA_DIR}</string>
    <string>--initial-url</string>
    <string>${MYRM_CHROME_AGENT_INITIAL_URL}</string>
  </array>
  <key>KeepAlive</key>
  <true/>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_FILE}</string>
  <key>StandardErrorPath</key>
  <string>${LOG_FILE}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST}"
launchctl enable "gui/$(id -u)/${LABEL}" 2>/dev/null || true

for _ in $(seq 1 30); do
  if curl -sf --max-time 3 "http://127.0.0.1:${MYRM_CHROME_AGENT_PORT}/proxy/status" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("chromeRunning") else 1)' \
    2>/dev/null; then
    echo "MYRM_CHROME_AGENT_LAUNCHAGENT_OK: ${LABEL} port=${MYRM_CHROME_AGENT_PORT} log=${LOG_FILE}"
    exit 0
  fi
  sleep 1
done

echo "MYRM_CHROME_AGENT_LAUNCHAGENT_FAIL: timeout — see ${LOG_FILE}" >&2
exit 1
