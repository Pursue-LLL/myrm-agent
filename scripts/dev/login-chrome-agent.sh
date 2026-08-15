#!/usr/bin/env bash
# One-time X/OAuth login: launch ChromeAgent profile WITHOUT CDP automation flags.
# Google/X block sign-in when --remote-debugging-pipe is active.
# Holds the machine-level install lock while booting out the proxy so a
# concurrent install/upgrade cannot flip the bundle mid-login.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=chrome-agent/lib-chrome-agent.sh
source "${SCRIPT_DIR}/chrome-agent/lib-chrome-agent.sh"

MYRM_CHROME_AGENT_PORT="${MYRM_CHROME_AGENT_PORT:-${CHROME_AGENT_DEFAULT_PORT}}"
DATA_DIR="$(chrome_agent_data_dir)"
CHROME_APP="/Applications/Google Chrome.app"
LOGIN_URL="${1:-https://x.com/login}"
LOG_FILE="$(chrome_agent_login_log_file)"

fail() {
  echo "MYRM_CHROME_AGENT_LOGIN_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "MYRM_CHROME_AGENT_LOGIN_OK: $*"
}

[[ -d "${CHROME_APP}" ]] || fail "missing ${CHROME_APP}"

chrome_agent_lock_acquire || fail "another install/login is in progress"
trap chrome_agent_lock_release EXIT

echo "MYRM_CHROME_AGENT_LOGIN: stopping pipe-proxy (profile lock)..." >&2
launchctl bootout "gui/$(id -u)/${CHROME_AGENT_LABEL}" 2>/dev/null || true
pkill -f "pipe-cdp-proxy.mjs.*${MYRM_CHROME_AGENT_PORT}" 2>/dev/null || true

for _ in $(seq 1 20); do
  if ! lsof "${DATA_DIR}/SingletonLock" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if lsof "${DATA_DIR}/SingletonLock" >/dev/null 2>&1; then
  fail "ChromeAgent profile still locked — close every Google Chrome window, wait 5s, retry"
fi

mkdir -p "$(dirname "${LOG_FILE}")"

echo "MYRM_CHROME_AGENT_LOGIN: opening separate Chrome instance (no CDP, OAuth-safe)..." >&2
# -n: new instance even if daily Chrome is open; -a: use Chrome.app (arm64 on Apple Silicon).
open -na "${CHROME_APP}" --args \
  "--user-data-dir=${DATA_DIR}" \
  "--no-first-run" \
  "--no-default-browser-check" \
  "${LOGIN_URL}" \
  >>"${LOG_FILE}" 2>&1

sleep 2
osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 || true

ok "login window opened profile=${DATA_DIR} url=${LOGIN_URL}"
echo "MYRM_CHROME_AGENT_LOGIN: ① 在此窗口完成 X 登录  ② 关窗口(Cmd+W，勿 Cmd+Q)  ③ 运行: ./myrm ready --chrome-agent --daemon" >&2
