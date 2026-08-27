#!/usr/bin/env bash
# Unified Browser Management CLI for Myrm — Zero Mental Overhead.
#
# Subcommands:
#   status           Clean summary of all browser instances (Agent :9410 & E2E :9333).
#   stop             Cascade stop all background browsers, orchestrators and proxies.
#   open             Launch or reveal a visible foreground browser window on desktop.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROME_AGENT_CLI="${SCRIPT_DIR}/chrome-agent/myrm-chrome-agent.sh"
CHROME_E2E_CLI="${SCRIPT_DIR}/chrome-e2e/myrm-chrome-e2e.sh"

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

cmd_status() {
  echo -e "${BOLD}Myrm Browser Fleet Status${NC}"
  echo "--------------------------------------------------------"

  # 1. ChromeAgent (:9410)
  echo -e "${CYAN}${BOLD}[1] Agent Browser (MCP / Scraper · Port 9410)${NC}"
  local agent_status="DOWN"
  local agent_pid="none"
  local agent_tabs="0"
  if curl -sf --max-time 1 "http://127.0.0.1:9410/proxy/status" >/dev/null 2>&1; then
    agent_status="${GREEN}HEALTHY${NC}"
    local proxy_json
    proxy_json="$(curl -sf --max-time 1 "http://127.0.0.1:9410/proxy/status" 2>/dev/null || echo '{}')"
    agent_pid="$(python3 -c "import json, sys; d=json.loads(sys.argv[1]); print(d.get('chromePid', 'unknown'))" "${proxy_json}" 2>/dev/null || echo 'unknown')"
    agent_tabs="$(python3 -c "import json, sys; d=json.loads(sys.argv[1]); print(d.get('knownTargets', 0))" "${proxy_json}" 2>/dev/null || echo '0')"
  fi
  echo -e "  Status: ${agent_status} | PID: ${agent_pid} | Active Tabs: ${agent_tabs}"

  # 2. ChromeE2E (:9333)
  echo -e "\n${CYAN}${BOLD}[2] E2E Test Browser (Automated Tests · Port 9333)${NC}"
  local e2e_status="DOWN"
  local e2e_pid="none"
  local e2e_tabs="0"
  if curl -sf --max-time 1 "http://127.0.0.1:9333/json/version" >/dev/null 2>&1; then
    e2e_status="${GREEN}HEALTHY${NC}"
    e2e_pid="$(lsof -tiTCP:9333 -sTCP:LISTEN 2>/dev/null | head -1 || echo 'unknown')"
    local list_json
    list_json="$(curl -sf --max-time 1 "http://127.0.0.1:9333/json/list" 2>/dev/null || echo '[]')"
    e2e_tabs="$(python3 -c "import json, sys; d=json.loads(sys.argv[1]); print(len(d))" "${list_json}" 2>/dev/null || echo '0')"
  fi
  echo -e "  Status: ${e2e_status} | PID: ${e2e_pid} | Active Tabs: ${e2e_tabs}"
  echo "--------------------------------------------------------"
}

cmd_stop() {
  echo "Stopping all Myrm browser instances and background daemons..."

  # Stop Agent LaunchAgent
  if [[ -f "${CHROME_AGENT_CLI}" ]]; then
    bash "${CHROME_AGENT_CLI}" stop >/dev/null 2>&1 || true
  fi

  # Stop E2E stack (orchestrator + cdmcp + ChromeE2E)
  if [[ -f "${CHROME_E2E_CLI}" ]]; then
    bash "${CHROME_E2E_CLI}" stop >/dev/null 2>&1 || true
  fi

  # Final safety sweep for any orphan helpers or background processes
  for pid in $(ps aux | grep -E "ChromeAgent|ChromeE2E" | grep -v grep | awk '{print $2}'); do
    kill -9 "${pid}" 2>/dev/null || true
  done
  for pid in $(ps aux | grep -E "browser-orchestrator|cdmcp-mux" | grep -v grep | awk '{print $2}'); do
    kill -9 "${pid}" 2>/dev/null || true
  done

  echo -e "${GREEN}All browser instances and background daemons stopped. Dock cleared.${NC}"
}

cmd_open() {
  echo "Launching visible foreground browser window..."
  export MYRM_CHROME_AGENT_FOREGROUND=1
  if [[ -f "${CHROME_AGENT_CLI}" ]]; then
    bash "${CHROME_AGENT_CLI}" install >/dev/null 2>&1 || true
  fi
  if [[ "$(uname -s)" == "Darwin" ]]; then
    osascript -e 'tell application "Google Chrome" to activate' 2>/dev/null || true
  fi
  echo -e "${GREEN}Browser window opened and visible on desktop.${NC}"
}

case "${1:-status}" in
  status) cmd_status ;;
  stop) cmd_stop ;;
  open) cmd_open ;;
  *)
    echo "Usage: ./myrm browser {status|stop|open}" >&2
    echo "  status  Summary of all running browser instances" >&2
    echo "  stop    Cascade stop all browsers and clear Dock" >&2
    echo "  open    Launch/reveal visible browser window on desktop" >&2
    exit 1
    ;;
esac
