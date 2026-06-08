#!/usr/bin/env bash
# Shared harness-aware dependency install for server CI scripts.
# Caller must set SERVER_ROOT before sourcing.

myrm_ci_resolve_harness_root() {
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

myrm_ci_harness_on_pypi() {
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
req = urllib.request.Request(url, headers={"User-Agent": "myrm-ci"})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        raise SystemExit(0 if resp.status == 200 else 1)
except urllib.error.HTTPError:
    raise SystemExit(1)
PY
}

myrm_ci_fail_no_harness_source() {
  echo "ERROR: Cannot run server CI without harness." >&2
  echo "  - Use vortexai layout (myrm-agent-harness/ beside myrm-agent) and run from monorepo, or" >&2
  echo "  - Publish harness to PyPI and refresh myrm-agent-server/uv.lock (./myrm harness sync-lock)." >&2
  exit 1
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

  if myrm_ci_resolve_harness_root >/dev/null; then
    echo "CI deps: local harness tree"
    if [[ "${reuse_venv}" -eq 1 && -x "${SERVER_ROOT}/.venv/bin/python" ]]; then
      echo "CI deps: reusing existing .venv"
      return 0
    fi
    if [[ "${use_all_extras}" -eq 1 ]]; then
      uv sync --group dev --all-extras
    else
      uv sync --group dev
    fi
    return 0
  fi

  if myrm_ci_harness_on_pypi; then
    echo "CI deps: PyPI harness"
    if ! uv sync --frozen --all-extras --group dev; then
      echo "ERROR: uv sync --frozen failed. Ensure uv.lock uses PyPI registry pins." >&2
      exit 1
    fi
    return 0
  fi

  myrm_ci_fail_no_harness_source
}
