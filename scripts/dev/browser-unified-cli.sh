#!/usr/bin/env bash
# Unified Browser Management CLI for Myrm — Zero Mental Overhead.
#
# Subcommands:
#   status           Clean summary of all browser instances (Agent :9410 & E2E :9333).
#   stop             Cascade stop all background browsers, orchestrators and proxies.
#   open             Launch or reveal a visible foreground browser window on desktop.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/chrome_agent_cli.sh
source "${SCRIPT_DIR}/lib/chrome_agent_cli.sh"
CHROME_E2E_CLI="${SCRIPT_DIR}/chrome-e2e/myrm-chrome-e2e.sh"

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

# Tabs of the CDP endpoint on port $1: its `page` targets only (service workers, iframes, workers and
# browser UI are listed beside them but are not tabs). `unknown` when the endpoint cannot list targets.
_page_count() {
  local list_json
  list_json="$(curl -sf --max-time 1 "http://127.0.0.1:$1/json/list" 2>/dev/null)" || { echo "unknown"; return 0; }
  python3 -c "import json, sys; print(sum(t.get('type') == 'page' for t in json.loads(sys.argv[1])))" "${list_json}" 2>/dev/null || echo "unknown"
}

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
    agent_tabs="$(_page_count 9410)"
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
    e2e_tabs="$(_page_count 9333)"
  fi
  echo -e "  Status: ${e2e_status} | PID: ${e2e_pid} | Active Tabs: ${e2e_tabs}"
  echo "--------------------------------------------------------"
}

cmd_stop() {
  local agent_cli
  echo "Stopping all Myrm browser instances and background daemons..."

  # Stop Agent LaunchAgent (the rest still stops when the CLI is missing; the lookup says so on stderr)
  if agent_cli="$(chrome_agent_cli)"; then
    "${agent_cli}" stop >/dev/null 2>&1 || true
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
  local agent_cli
  agent_cli="$(chrome_agent_cli)" || exit 1
  "${agent_cli}" install >/dev/null 2>&1 || true
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
    echo "Usage: ./myrm-dev browser {status|stop|open}" >&2
    echo "  status  Summary of all running browser instances" >&2
    echo "  stop    Cascade stop all browsers and clear Dock" >&2
    echo "  open    Launch/reveal visible browser window on desktop" >&2
    exit 1
    ;;
esac
