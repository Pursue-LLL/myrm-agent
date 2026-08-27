#!/usr/bin/env bash
# Machine-level ChromeAgent CLI — browser backend independent of any checkout.
#
# Subcommands:
#   install|upgrade  Sync repo bundle → ~/.local/lib/myrm-chrome-agent, flip
#                    `current` symlink atomically, install LaunchAgent, verify.
#   daemon           LaunchAgent start (alias of ./myrm ready --chrome-agent --daemon).
#   login            Open OAuth-safe login window (alias of --chrome-agent --login).
#   status           Read-only report of sha / current / LaunchAgent / health.
#   uninstall        Stop LaunchAgent and remove plist (keeps profile + versions).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-chrome-agent.sh
source "${SCRIPT_DIR}/lib-chrome-agent.sh"

fail() {
  echo "MYRM_CHROME_AGENT_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "MYRM_CHROME_AGENT_OK: $*"
}

cmd_status() {
  local base sha installed current loaded health plist
  base="$(chrome_agent_install_base)"
  sha="$(chrome_agent_source_sha 2>/dev/null || echo 'unknown')"
  installed="$(chrome_agent_installed_sha)"
  current="$(chrome_agent_current_sha)"
  if chrome_agent_launchagent_loaded; then loaded="loaded"; else loaded="not-loaded"; fi
  if chrome_agent_health; then health="healthy"; else health="unhealthy"; fi
  echo "CHROME_AGENT_STATUS: install_base=${base}"
  echo "CHROME_AGENT_STATUS: source_sha=${sha} installed_sha=${installed} current=${current}"
  echo "CHROME_AGENT_STATUS: launchagent=${loaded} health=${health}"
  plist="$(chrome_agent_plist_path)"
  if [[ -f "${plist}" ]]; then
    echo "CHROME_AGENT_STATUS: plist=${plist}"
    grep -A2 'ProgramArguments' "${plist}" | head -5 || true
  else
    echo "CHROME_AGENT_STATUS: plist=absent"
  fi
}

cmd_install() {
  local previous sha
  chrome_agent_lock_acquire || exit 1
  trap chrome_agent_lock_release EXIT
  sha="$(chrome_agent_sync_bundle)" || fail "bundle sync failed (sha=${sha:-''})"
  previous="$(chrome_agent_switch_current "${sha}")" || true
  chrome_agent_write_plist || fail "plist write failed"
  chrome_agent_launchagent_start
  if chrome_agent_wait_health; then
    printf '%s' "${sha}" >"$(chrome_agent_installed_sha_file)"
    ok "installed sha=${sha} port=${MYRM_CHROME_AGENT_PORT:-${CHROME_AGENT_DEFAULT_PORT}}"
    return 0
  fi
  # Rollback: restore previous symlink target when one existed.
  if [[ -n "${previous:-}" ]]; then
    ln -sfn "$(chrome_agent_versions_dir)/${previous}" "$(chrome_agent_current_link)"
    chrome_agent_launchagent_start
    chrome_agent_wait_health && ok "rolled back to sha=${previous}" || true
  fi
  fail "health check failed after install — see $(chrome_agent_log_file)"
}

cmd_stop() {
  launchctl bootout "gui/$(id -u)/${CHROME_AGENT_LABEL}" 2>/dev/null || true
  ok "stopped LaunchAgent service (plist preserved for next start)"
}

cmd_uninstall() {
  launchctl bootout "gui/$(id -u)/${CHROME_AGENT_LABEL}" 2>/dev/null || true
  rm -f "$(chrome_agent_plist_path)"
  ok "uninstalled LaunchAgent; profile + version bundles kept"
}

case "${1:-status}" in
  install|upgrade) cmd_install ;;
  daemon) exec "${SCRIPT_DIR}/../install-chrome-agent-launchagent.sh" ;;
  login) exec "${SCRIPT_DIR}/../login-chrome-agent.sh" ;;
  status) cmd_status ;;
  stop) cmd_stop ;;
  uninstall) cmd_uninstall ;;
  *)
    echo "Usage: myrm-chrome-agent.sh {install|upgrade|daemon|login|status|stop|uninstall}" >&2
    exit 1
    ;;
esac
