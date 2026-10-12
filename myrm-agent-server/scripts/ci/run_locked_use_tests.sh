#!/usr/bin/env bash
# Focused regression for Locked Use / Privacy Curtain server orchestration.
set -euo pipefail

SERVER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${SERVER_ROOT}"

# shellcheck source=lib_harness_deps.sh
source "${SERVER_ROOT}/scripts/ci/lib_harness_deps.sh"

myrm_ci_install_server_deps --reuse-venv

pytest_args=(-n0 --tb=short -q tests/services/locked_use/ tests/core/infra/health/test_desktop_locked_use_diagnostic.py)
if [[ -x "${SERVER_ROOT}/.venv/bin/python" ]]; then
  "${SERVER_ROOT}/.venv/bin/python" -m pytest "${pytest_args[@]}"
else
  uv run pytest "${pytest_args[@]}"
fi

echo "OK: locked_use pytest suite"
