#!/usr/bin/env bash
# Server architecture gates (harness contract, imports, docs links).
# Requires local harness (vortexai layout) or PyPI-published harness for the pinned version.
set -euo pipefail

SERVER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${SERVER_ROOT}"

_resolve_harness_root() {
  local candidate
  for candidate in \
    "${MYRM_HARNESS_ROOT:-}" \
    "${SERVER_ROOT}/../../myrm-agent-harness" \
    "${SERVER_ROOT}/../myrm-agent-harness"; do
    if [[ -n "${candidate}" && -f "${candidate}/pyproject.toml" ]]; then
      echo "$(cd "${candidate}" && pwd)"
      return 0
    fi
  done
  return 1
}

_harness_on_pypi() {
  python3 - <<PY
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

server_root = Path("${SERVER_ROOT}")
spec_script = server_root / "docker" / "read_harness_pypi_spec.py"
result = subprocess.run([sys.executable, str(spec_script)], check=True, capture_output=True, text=True)
spec = result.stdout.strip()
if "==" not in spec:
    raise SystemExit(1)
version = spec.rsplit("==", maxsplit=1)[-1]
url = f"https://pypi.org/pypi/myrm-agent-harness/{version}/json"
req = urllib.request.Request(url, headers={"User-Agent": "myrm-arch-gates"})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        raise SystemExit(0 if resp.status == 200 else 1)
except urllib.error.HTTPError:
    raise SystemExit(1)
PY
}

_fail_no_harness_source() {
  echo "ERROR: Cannot run full architecture gates without harness." >&2
  echo "  - Use vortexai layout (myrm-agent-harness/ beside myrm-agent) and run from monorepo, or" >&2
  echo "  - Publish harness to PyPI and refresh myrm-agent-server/uv.lock (./myrm harness sync-lock)." >&2
  exit 1
}

_install_deps() {
  if _resolve_harness_root >/dev/null; then
    echo "Architecture gates: dev install (local harness tree found)"
    # Architecture tests do not need matrix-e2ee / data-viz native wheels; skip --all-extras.
    if [[ -x "${SERVER_ROOT}/.venv/bin/python" ]]; then
      echo "Architecture gates: reusing existing .venv"
      return 0
    fi
    uv sync --group dev
    return 0
  fi
  if _harness_on_pypi; then
    echo "Architecture gates: install from PyPI"
    if ! uv sync --frozen --all-extras --group dev; then
      echo "ERROR: uv sync --frozen failed. Ensure uv.lock uses PyPI registry pins." >&2
      exit 1
    fi
    return 0
  fi
  _fail_no_harness_source
}

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

_install_deps
_run_fractal_docs
_run_pytest
echo "OK: server architecture gates"
