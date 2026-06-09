#!/usr/bin/env bash
# Local pytest entrypoint tuned for low memory (~300MB single worker vs N×350MB with xdist).
# Matches CI: scripts/ci/run_default_tests.sh uses -n0; pyproject addopts already apply -m 'not e2e'.
set -euo pipefail

SERVER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${SERVER_ROOT}"

WORKERS="${PYTEST_XDIST_WORKERS:-0}"
if [[ "${WORKERS}" == "0" ]]; then
  XDIST_ARGS=(-n0)
else
  # Cap parallel workers; avoid -n auto on many-core machines (each worker ~350MB RSS).
  XDIST_ARGS=(-n "${WORKERS}")
fi

if [[ -x "${SERVER_ROOT}/.venv/bin/python" ]]; then
  exec "${SERVER_ROOT}/.venv/bin/python" -m pytest "${XDIST_ARGS[@]}" --tb=short -q "$@"
else
  exec uv run pytest "${XDIST_ARGS[@]}" --tb=short -q "$@"
fi
