#!/usr/bin/env bash
# Startup import gate: importing the HTTP application makes no outbound network call and stays within its module budget.
# Runs apart from the default suite so that a failure or timeout there cannot hide this gate.
set -euo pipefail

SERVER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${SERVER_ROOT}"

# shellcheck source=lib_harness_deps.sh
source "${SERVER_ROOT}/scripts/ci/lib_harness_deps.sh"

myrm_ci_install_server_deps --reuse-venv

pytest_args=(-n0 --tb=short -q tests/startup/test_import_budget.py)
if [[ -x "${SERVER_ROOT}/.venv/bin/python" ]]; then
  "${SERVER_ROOT}/.venv/bin/python" -m pytest "${pytest_args[@]}"
else
  uv run pytest "${pytest_args[@]}"
fi

echo "OK: startup import gate"
