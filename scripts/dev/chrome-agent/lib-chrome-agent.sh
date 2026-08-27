#!/usr/bin/env bash
# ChromeAgent machine-level runtime library (POS: myrm dev tooling).
#
# Why a machine-level install: the Agent browser backend must not depend on any
# specific checkout surviving (delete/move the repo → LaunchAgent keeps serving).
# Source of truth stays in the repo (scripts/dev/chrome-agent/), and install
# copies a self-contained bundle to ~/.local/lib/myrm-chrome-agent. The
# LaunchAgent plist points only at the stable `current` symlink, so upgrades are
# atomic symlink flips with automatic rollback on health failure.
set -euo pipefail

CHROME_AGENT_LABEL="com.myrm.chrome-agent"
CHROME_AGENT_DEFAULT_PORT="9410"

# Resolve the real login home (bypasses sandboxed HOME such as Cursor's ~/.cursor2).
real_user_home() {
  local real_home
  real_home="$(python3 -c '
import os, pwd
try:
    print(pwd.getpwuid(os.getuid()).pw_dir)
except (KeyError, OSError):
    print(os.path.expanduser("~"))
' 2>/dev/null || true)"
  real_home="${real_home:-${HOME}}"
  printf '%s' "${real_home}"
}

chrome_agent_install_base() {
  printf '%s' "${MYRM_CHROME_AGENT_INSTALL_DIR:-$(real_user_home)/.local/lib/myrm-chrome-agent}"
}

chrome_agent_versions_dir() {
  printf '%s/versions' "$(chrome_agent_install_base)"
}

chrome_agent_current_link() {
  printf '%s/current' "$(chrome_agent_install_base)"
}

chrome_agent_installed_sha_file() {
  printf '%s/.installed-sha' "$(chrome_agent_install_base)"
}

chrome_agent_lock_dir() {
  printf '%s/.install.lock' "$(chrome_agent_install_base)"
}

chrome_agent_data_dir() {
  printf '%s' "${MYRM_CHROME_AGENT_DATA_DIR:-$(real_user_home)/Library/Application Support/Myrm/ChromeAgent}"
}

chrome_agent_log_file() {
  printf '%s' "${MYRM_CHROME_AGENT_LOG_FILE:-$(real_user_home)/.local/state/myrm-dev/chrome-agent-proxy.log}"
}

chrome_agent_login_log_file() {
  printf '%s' "${MYRM_CHROME_AGENT_LOGIN_LOG:-$(real_user_home)/.local/state/myrm-dev/chrome-agent-login.log}"
}

# Bundle source directory inside the repo (this script's sibling: chrome-agent/).
chrome_agent_repo_bundle_dir() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  printf '%s' "${script_dir}"
}

# Stable source identity: myrm-agent submodule HEAD short sha, falling back to a
# content hash when not inside a git checkout (e.g. exported source tarball).
chrome_agent_source_sha() {
  local repo_root bundle_dir
  bundle_dir="$(chrome_agent_repo_bundle_dir)"
  repo_root="$(cd "${bundle_dir}/../.." && pwd)"
  local sha=""
  if sha="$(git -C "${repo_root}" rev-parse --short HEAD 2>/dev/null)"; then
    printf '%s' "${sha}"
    return 0
  fi
  shasum -a 1 "${bundle_dir}"/pipe-cdp-proxy.mjs "${bundle_dir}"/chrome-arm64-launcher.sh \
    "${bundle_dir}"/package.json "${bundle_dir}"/package-lock.json 2>/dev/null \
    | awk '{ printf "%s", $1 }' | cut -c1-12
}

chrome_agent_installed_sha() {
  local file
  file="$(chrome_agent_installed_sha_file)"
  [[ -f "${file}" ]] || { printf ''; return 0; }
  tr -d '[:space:]' <"${file}"
}

chrome_agent_current_sha() {
  local link
  link="$(chrome_agent_current_link)"
  if [[ -L "${link}" ]]; then
    readlink "${link}" | sed -E 's#^.*/##'
  fi
}

chrome_agent_plist_path() {
  printf '%s/Library/LaunchAgents/%s.plist' "$(real_user_home)" "${CHROME_AGENT_LABEL}"
}

# --- atomic mkdir lock (macOS lacks flock(1)) ----------------------------------
# Lock dir contains the holder pid; stale holders (pid dead) are taken over.
chrome_agent_lock_acquire() {
  local lock_dir holder_pid now deadline
  lock_dir="$(chrome_agent_lock_dir)"
  mkdir -p "$(dirname "${lock_dir}")"
  deadline=$((SECONDS + 30))
  while :; do
    if mkdir "${lock_dir}" 2>/dev/null; then
      echo "$$" >"${lock_dir}/pid"
      return 0
    fi
    holder_pid="$(cat "${lock_dir}/pid" 2>/dev/null || echo '')"
    if [[ -n "${holder_pid}" ]] && ! kill -0 "${holder_pid}" 2>/dev/null; then
      rmdir "${lock_dir}" 2>/dev/null || rm -rf "${lock_dir}" 2>/dev/null || true
      continue
    fi
    if (( SECONDS >= deadline )); then
      echo "CHROME_AGENT_LOCK_TIMEOUT: another install/login is holding ${lock_dir}" >&2
      return 1
    fi
    sleep 0.2
  done
}

chrome_agent_lock_release() {
  rmdir "$(chrome_agent_lock_dir)" 2>/dev/null || true
}

# --- bundle sync ---------------------------------------------------------------
# A bundle is complete only when the proxy file exists and `ws` loads.
chrome_agent_bundle_valid() {
  local version_dir="$1" node_bin
  [[ -f "${version_dir}/pipe-cdp-proxy.mjs" ]] || return 1
  [[ -x "${version_dir}/chrome-arm64-launcher.sh" ]] || return 1
  node_bin="${MYRM_NODE_BIN:-$(command -v node || true)}"
  [[ -n "${node_bin}" && -x "${node_bin}" ]] || return 1
  if ! "${node_bin}" -e "require('${version_dir}/node_modules/ws')" >/dev/null 2>&1; then
    return 1
  fi
  return 0
}

# Sync repo bundle into versions/<sha> and make it complete (npm ci if needed).
# Always re-copy sources: the same git sha may carry uncommitted edits (live dev),
# so content must never be assumed current from the sha stamp alone.
chrome_agent_sync_bundle() {
  local sha bundle_dir version_dir
  sha="$(chrome_agent_source_sha)"
  bundle_dir="$(chrome_agent_repo_bundle_dir)"
  version_dir="$(chrome_agent_versions_dir)/${sha}"
  mkdir -p "${version_dir}"
  cp -p "${bundle_dir}"/pipe-cdp-proxy.mjs "${bundle_dir}"/chrome-arm64-launcher.sh \
    "${bundle_dir}"/package.json "${bundle_dir}"/package-lock.json "${version_dir}/"
  chmod +x "${version_dir}/chrome-arm64-launcher.sh"
  if [[ ! -d "${version_dir}/node_modules/ws" ]]; then
    (cd "${version_dir}" && npm ci --ignore-scripts --no-audit --no-fund >/dev/null 2>&1) \
      || { echo "CHROME_AGENT_NPM_FAIL: npm ci failed in ${version_dir}" >&2; return 1; }
  fi
  chrome_agent_bundle_valid "${version_dir}" \
    || { echo "CHROME_AGENT_BUNDLE_INVALID: ${version_dir} failed verification" >&2; return 1; }
  printf '%s' "${sha}"
}

# Atomically switch the `current` symlink; returns previous target for rollback.
chrome_agent_switch_current() {
  local sha="$1" link
  link="$(chrome_agent_current_link)"
  if [[ -L "${link}" ]]; then
    readlink "${link}"
  fi
  ln -sfn "$(chrome_agent_versions_dir)/${sha}" "${link}"
}

chrome_agent_proxy_status() {
  local port="${MYRM_CHROME_AGENT_PORT:-${CHROME_AGENT_DEFAULT_PORT}}"
  curl -sf --max-time 3 "http://127.0.0.1:${port}/proxy/status" 2>/dev/null \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("chromeRunning") else 1)' 2>/dev/null
}

chrome_agent_health() {
  chrome_agent_proxy_status
}

# --- LaunchAgent control -------------------------------------------------------
chrome_agent_write_plist() {
  local plist node_bin launcher log_file data_dir port initial_url
  plist="$(chrome_agent_plist_path)"
  node_bin="${MYRM_NODE_BIN:-$(command -v node || true)}"
  [[ -n "${node_bin}" && -x "${node_bin}" ]] || {
    echo "CHROME_AGENT_NODE_MISSING: node not found — set MYRM_NODE_BIN" >&2
    return 1
  }
  launcher="$(chrome_agent_current_link)/chrome-arm64-launcher.sh"
  log_file="$(chrome_agent_log_file)"
  data_dir="$(chrome_agent_data_dir)"
  port="${MYRM_CHROME_AGENT_PORT:-${CHROME_AGENT_DEFAULT_PORT}}"
  initial_url="${MYRM_CHROME_AGENT_INITIAL_URL:-about:blank}"
  mkdir -p "$(dirname "${plist}")" "$(dirname "${log_file}")" "${data_dir}"
  cat >"${plist}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${CHROME_AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${node_bin}</string>
    <string>$(chrome_agent_current_link)/pipe-cdp-proxy.mjs</string>
    <string>--port</string>
    <string>${port}</string>
    <string>--chrome-path</string>
    <string>${launcher}</string>
    <string>--user-data-dir</string>
    <string>${data_dir}</string>
    <string>--initial-url</string>
    <string>${initial_url}</string>
  </array>
  <key>KeepAlive</key>
  <true/>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${log_file}</string>
  <key>StandardErrorPath</key>
  <string>${log_file}</string>
    <key>EnvironmentVariables</key>
    <dict>
      <key>HOME</key>
      <string>$(real_user_home)</string>
      <key>MYRM_CHROME_AGENT_FOREGROUND</key>
      <string>${MYRM_CHROME_AGENT_FOREGROUND:-0}</string>
    </dict>
</dict>
</plist>
EOF
}

chrome_agent_launchagent_loaded() {
  launchctl print "gui/$(id -u)/${CHROME_AGENT_LABEL}" >/dev/null 2>&1
}

chrome_agent_launchagent_start() {
  local plist
  plist="$(chrome_agent_plist_path)"
  launchctl bootout "gui/$(id -u)/${CHROME_AGENT_LABEL}" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "${plist}"
  launchctl enable "gui/$(id -u)/${CHROME_AGENT_LABEL}" 2>/dev/null || true
}

# Wait up to 60s for health; used by install/upgrade/daemon.
chrome_agent_wait_health() {
  local i
  for _ in $(seq 1 60); do
    if chrome_agent_health; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# Chrome allows one live process per user-data-dir (SingletonLock). OAuth login
# opens a non-CDP window on the same profile; starting pipe-proxy before that
# window closes makes CDP Chrome exit immediately (see chrome-agent-proxy.log).
chrome_agent_profile_lock_pid() {
  local data_dir lock_link lock_name pid
  data_dir="$(chrome_agent_data_dir)"
  lock_link="${data_dir}/SingletonLock"
  [[ -L "${lock_link}" ]] || return 1
  lock_name="$(readlink "${lock_link}")"
  pid="${lock_name##*-}"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1
  printf '%s' "${pid}"
}

chrome_agent_pid_uses_cdp_pipe() {
  local pid="$1"
  ps -p "${pid}" -ww -o args= 2>/dev/null | grep -q 'remote-debugging-pipe'
}

chrome_agent_assert_profile_available_for_cdp() {
  local pid
  pid="$(chrome_agent_profile_lock_pid || true)"
  [[ -z "${pid}" ]] && return 0
  if chrome_agent_pid_uses_cdp_pipe "${pid}"; then
    return 0
  fi
  echo "MYRM_CHROME_AGENT_FAIL: login Chrome still holds profile (pid=${pid}) — finish X login, Cmd+W close the ChromeAgent window, then run: ./myrm ready --chrome-agent --daemon" >&2
  return 1
}

# Reject proxies pointing outside the machine-level install (stale repo paths).
chrome_agent_plist_points_to_install() {
  local plist
  plist="$(chrome_agent_plist_path)"
  [[ -f "${plist}" ]] || return 1
  grep -q "$(chrome_agent_install_base)/current/" "${plist}"
}
