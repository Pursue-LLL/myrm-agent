#!/usr/bin/env bash
# Server architecture gates (harness contract, imports, docs links).
# Requires local harness (vortexai layout) or PyPI-published harness for the pinned version.
set -euo pipefail

SERVER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${SERVER_ROOT}"

# shellcheck source=lib_harness_deps.sh
source "${SERVER_ROOT}/scripts/ci/lib_harness_deps.sh"

_run_pytest() {
  local pytest_args=(tests/architecture/ -m architecture -v --tb=short -n0)
  if [[ -x "${SERVER_ROOT}/.venv/bin/python" ]]; then
    "${SERVER_ROOT}/.venv/bin/python" -m pytest "${pytest_args[@]}"
  else
    uv run pytest "${pytest_args[@]}"
  fi
}

_run_fractal_docs() {
  local py="${SERVER_ROOT}/.venv/bin/python"
  if [[ ! -x "${py}" ]]; then
    py="python3"
    if command -v uv >/dev/null 2>&1; then
      _fractal() { uv run python "$@"; }
    else
      _fractal() { "${py}" "$@"; }
    fi
  else
    _fractal() { "${py}" "$@"; }
  fi
  _fractal "${SERVER_ROOT}/scripts/check_fractal_docs.py"
  _fractal "${SERVER_ROOT}/scripts/check_fractal_docs.py" \
    --strict-headers \
    --header-baseline "${SERVER_ROOT}/tests/architecture/data/fractal_header_baseline.txt"
  _fractal "${SERVER_ROOT}/scripts/check_fractal_docs.py" --no-stub
  _fractal "${SERVER_ROOT}/scripts/check_file_line_budget.py"
}

myrm_ci_install_server_deps --reuse-venv
_run_fractal_docs
_run_pytest
echo "OK: server architecture gates"
