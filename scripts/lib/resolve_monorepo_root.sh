#!/usr/bin/env bash
# Resolve vortexai / open-perplexity shell root (submodule parent). Optional for OSS-only clones.

resolve_monorepo_root() {
  local agent_root="${1:-}"

  if [[ -n "${MYRM_MONOREPO_ROOT:-}" && -f "${MYRM_MONOREPO_ROOT}/.gitmodules" ]]; then
    echo "${MYRM_MONOREPO_ROOT}"
    return 0
  fi

  if [[ -n "${agent_root}" && -f "${agent_root}/../.gitmodules" ]]; then
    echo "$(cd "${agent_root}/.." && pwd)"
    return 0
  fi

  if [[ -f "${agent_root}/.gitmodules" ]]; then
    echo "${agent_root}"
    return 0
  fi

  return 1
}
