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
  python3 - <<'PY'
import urllib.error
import urllib.request

url = "https://pypi.org/pypi/myrm-agent-harness/0.1.0rc1/json"
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

_install_deps
_run_pytest
echo "OK: server architecture gates"
