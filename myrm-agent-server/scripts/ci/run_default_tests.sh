#!/usr/bin/env bash
# Default server pytest suite (unit + API integration; excludes @pytest.mark.e2e).
# Requires local harness (vortexai layout) or PyPI-published harness for the pinned version.
set -euo pipefail

SERVER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${SERVER_ROOT}"

# shellcheck source=lib_harness_deps.sh
source "${SERVER_ROOT}/scripts/ci/lib_harness_deps.sh"

_run_pytest() {
  # pyproject addopts already applies: -m 'not e2e' --timeout=300
  local pytest_args=(-n0 --tb=short -q)
  if [[ -x "${SERVER_ROOT}/.venv/bin/python" ]]; then
    "${SERVER_ROOT}/.venv/bin/python" -m pytest "${pytest_args[@]}"
  else
    uv run pytest "${pytest_args[@]}"
  fi
}

myrm_ci_install_server_deps --reuse-venv
_run_pytest
echo "OK: server default pytest suite"
