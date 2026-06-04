#!/usr/bin/env bash
# Server architecture gates (harness contract, imports, docs links).
# Full suite when harness is reachable (vortexai layout or PyPI); static subset otherwise.
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

_install_deps() {
  if _resolve_harness_root >/dev/null; then
    echo "Architecture gates: full install (local harness tree found)"
    uv sync --all-extras --group dev
    return 0
  fi
  if _harness_on_pypi; then
    echo "Architecture gates: install from PyPI"
    uv sync --frozen --all-extras --group dev
    return 0
  fi
  echo "Architecture gates: static subset only (no local harness, PyPI missing)" >&2
  uv sync --frozen --no-install-package myrm-agent-harness \
    --no-sources-package myrm-agent-harness --group dev 2>/dev/null \
    || uv sync --no-install-package myrm-agent-harness \
    --no-sources-package myrm-agent-harness --group dev
}

_run_pytest() {
  local -a args=(-m architecture -v --tb=short)
  if ! _resolve_harness_root >/dev/null && ! _harness_on_pypi; then
    args+=(
      --ignore=tests/architecture/test_sse_event_type_parity.py
      --ignore=tests/architecture/test_no_user_id.py
    )
  fi
  uv run pytest tests/architecture/ "${args[@]}"
}

_install_deps
_run_pytest
echo "OK: server architecture gates"
