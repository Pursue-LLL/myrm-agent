#!/usr/bin/env bash
# Resolve AGENT_ROOT for vortexai (submodule) vs myrm-agent OSS bundle layouts.
# Usage: source this file, then: resolve_agent_paths "/path/to/repo/root"

resolve_agent_paths() {
  local project_root="$1"

  if [[ -f "${project_root}/myrm-agent/myrm-agent-server/run.py" ]]; then
    AGENT_ROOT="${project_root}/myrm-agent"
  elif [[ -f "${project_root}/myrm-agent-server/run.py" ]]; then
    AGENT_ROOT="${project_root}"
  else
    echo "ERROR: myrm-agent-server not found under ${project_root}" >&2
    echo "  vortexai: run git submodule update --init myrm-agent" >&2
    echo "  OSS: clone https://github.com/Pursue-LLL/myrm-agent.git" >&2
    return 1
  fi

  SERVER_DIR="${AGENT_ROOT}/myrm-agent-server"
  FRONTEND_DIR="${AGENT_ROOT}/myrm-agent-frontend"
  DESKTOP_DIR="${AGENT_ROOT}/myrm-agent-desktop"
  export AGENT_ROOT SERVER_DIR FRONTEND_DIR DESKTOP_DIR
}
