#!/usr/bin/env bash
# Shared dependency install for server CI scripts.
# The harness lives in this repository (../myrm-agent-harness) and is resolved as an editable
# path source by uv.lock, so server CI always runs against the same commit as the harness.
# Caller must set SERVER_ROOT before sourcing.

myrm_ci_resolve_harness_root() {
  local candidate="${SERVER_ROOT}/../myrm-agent-harness"
  if [[ -f "${candidate}/pyproject.toml" ]]; then
    echo "$(cd "${candidate}" && pwd)"
    return 0
  fi
  echo "ERROR: harness not found at ${candidate}; expected the myrm-agent monorepo layout." >&2
  return 1
}

# Usage: myrm_ci_install_server_deps [--all-extras] [--reuse-venv]
myrm_ci_install_server_deps() {
  local use_all_extras=0
  local reuse_venv=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --all-extras) use_all_extras=1 ;;
      --reuse-venv) reuse_venv=1 ;;
      *) echo "Unknown option: $1" >&2; return 1 ;;
    esac
    shift
  done

  cd "${SERVER_ROOT}"
  myrm_ci_resolve_harness_root >/dev/null || return 1

  if [[ "${reuse_venv}" -eq 1 && -x "${SERVER_ROOT}/.venv/bin/python" ]]; then
    echo "CI deps: reusing existing .venv"
    return 0
  fi
  if [[ "${use_all_extras}" -eq 1 ]]; then
    uv sync --frozen --group dev --all-extras
  else
    uv sync --frozen --group dev
  fi
}
