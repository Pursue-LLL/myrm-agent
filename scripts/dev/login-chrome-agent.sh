#!/usr/bin/env bash
# One-time X/OAuth login: launch ChromeAgent profile WITHOUT CDP automation flags.
# Google/X block sign-in when --remote-debugging-pipe is active.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=lib/dev_state_paths.sh
source "${AGENT_ROOT}/scripts/dev/lib/dev_state_paths.sh"
export_spawn_home

MYRM_CHROME_AGENT_PORT="${MYRM_CHROME_AGENT_PORT:-9410}"
MYRM_CHROME_AGENT_DATA_DIR="${MYRM_CHROME_AGENT_DATA_DIR:-${HOME}/Library/Application Support/Myrm/ChromeAgent}"
CHROME_APP="/Applications/Google Chrome.app"
LABEL="com.myrm.chrome-agent"
LOGIN_URL="${1:-https://x.com/login}"
LOG_FILE="${MYRM_CHROME_AGENT_LOGIN_LOG:-$(dev_state_dir)/chrome-agent-login.log}"

fail() {
  echo "MYRM_CHROME_AGENT_LOGIN_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "MYRM_CHROME_AGENT_LOGIN_OK: $*"
}

[[ -d "${CHROME_APP}" ]] || fail "missing ${CHROME_APP}"

echo "MYRM_CHROME_AGENT_LOGIN: stopping pipe-proxy (profile lock)..." >&2
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
pkill -f "pipe-cdp-proxy.mjs.*${MYRM_CHROME_AGENT_PORT}" 2>/dev/null || true

for _ in $(seq 1 20); do
  if ! lsof "${MYRM_CHROME_AGENT_DATA_DIR}/SingletonLock" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if lsof "${MYRM_CHROME_AGENT_DATA_DIR}/SingletonLock" >/dev/null 2>&1; then
  fail "ChromeAgent profile still locked — close every Google Chrome window, wait 5s, retry"
fi

mkdir -p "$(dev_state_dir)"

echo "MYRM_CHROME_AGENT_LOGIN: opening separate Chrome instance (no CDP, OAuth-safe)..." >&2
# -n: new instance even if daily Chrome is open; -a: use Chrome.app (arm64 on Apple Silicon).
open -na "${CHROME_APP}" --args \
  "--user-data-dir=${MYRM_CHROME_AGENT_DATA_DIR}" \
  "--no-first-run" \
  "--no-default-browser-check" \
  "${LOGIN_URL}" \
  >>"${LOG_FILE}" 2>&1

sleep 2
osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 || true

ok "login window opened profile=${MYRM_CHROME_AGENT_DATA_DIR} url=${LOGIN_URL}"
echo "MYRM_CHROME_AGENT_LOGIN: ① 在此窗口完成 X 登录  ② 关窗口(Cmd+W，勿 Cmd+Q)  ③ 运行: ./myrm ready --chrome-agent --daemon" >&2
