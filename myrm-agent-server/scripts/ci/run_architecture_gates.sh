#!/usr/bin/env bash
# Server architecture gates (harness contract, imports, docs links).
# The harness comes from the sibling ../myrm-agent-harness directory (editable path source).
set -euo pipefail

SERVER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${SERVER_ROOT}"

# shellcheck source=lib_harness_deps.sh
source "${SERVER_ROOT}/scripts/ci/lib_harness_deps.sh"

_run_pytest() {
  local num_workers="${PYTEST_ARCH_WORKERS:-4}"
  local pytest_args=(tests/architecture/ -m architecture --tb=short ${PYTEST_ARCH_ARGS:--n ${num_workers}})
  local monorepo_safe="${SERVER_ROOT}/../../scripts/dev/run-pytest-safe.sh"
  if [[ -x "${monorepo_safe}" && -x "${SERVER_ROOT}/.venv/bin/python" ]]; then
    bash "${monorepo_safe}" "${SERVER_ROOT}/.venv/bin/python" -m pytest "${pytest_args[@]}"
  elif [[ -x "${SERVER_ROOT}/.venv/bin/python" ]]; then
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
}

_run_md_refs() {
  local harness_root py
  harness_root="$(myrm_ci_resolve_harness_root)"
  py="${SERVER_ROOT}/.venv/bin/python"
  [[ -x "${py}" ]] || py="python3"
  "${py}" "${harness_root}/scripts/validate_arch_inventory.py" \
    --root "${SERVER_ROOT}" --md-refs
}

_run_import_resolvability() {
  local harness_root py
  harness_root="$(myrm_ci_resolve_harness_root)"
  py="${SERVER_ROOT}/.venv/bin/python"
  [[ -x "${py}" ]] || py="python3"
  "${py}" "${harness_root}/scripts/check_import_resolvability.py" \
    --package "myrm_agent_harness=${harness_root}/src/myrm_agent_harness" \
    --package "app=${SERVER_ROOT}/app" \
    --scan app
}

# Diff mode: only server units that are dead in the working tree and were not dead at the merge-base
# fail, so units already unwired on the base branch cannot block an unrelated change. Untracked files
# count as part of the working tree; the verdict covers committed changes only on a clean checkout (CI).
# An unresolvable base revision is an error.
_run_module_reachability() {
  local harness_root py
  if ! harness_root="$(myrm_ci_resolve_harness_root)"; then
    echo "CI module-reachability: harness source unavailable (PyPI mode); skipping module reachability check"
    return 0
  fi
  py="${SERVER_ROOT}/.venv/bin/python"
  [[ -x "${py}" ]] || py="python3"
  "${py}" "${harness_root}/scripts/check_module_reachability.py" \
    --server --server-root "${SERVER_ROOT}/app" \
    --base "${MYRM_REACHABILITY_BASE:-origin/main}"
}

_run_ruff() {
  if [[ -x "${SERVER_ROOT}/.venv/bin/ruff" ]]; then
    "${SERVER_ROOT}/.venv/bin/ruff" check .
  else
    uv run ruff check .
  fi
}

_run_pyright_unbound() {
  # Blocks the "name used before it exists" class (e.g. a local read before assignment).
  # Full pyright carries a large pre-existing baseline for other rules, so only the two
  # name-resolution rules are fatal here.
  if [[ "${CI:-}" != "true" && "${MYRM_PYRIGHT_GATE:-0}" != "1" ]]; then
    echo "CI pyright: skipped locally (set MYRM_PYRIGHT_GATE=1 or CI=true to run)"
    return 0
  fi
  local report
  report="$(mktemp -t pyright-unbound.XXXXXX.json)"
  if [[ -x "${SERVER_ROOT}/.venv/bin/pyright" ]]; then
    "${SERVER_ROOT}/.venv/bin/pyright" --project "${SERVER_ROOT}" --outputjson > "${report}" || true
  else
    (cd "${SERVER_ROOT}" && uv run pyright --outputjson > "${report}") || true
  fi
  local py="${SERVER_ROOT}/.venv/bin/python"
  [[ -x "${py}" ]] || py="python3"
  if ! "${py}" "${SERVER_ROOT}/scripts/ci/check_pyright_unbound.py" "${report}"; then
    rm -f "${report}"
    return 1
  fi
  rm -f "${report}"
}

_run_profile_capability_gate() {
  local py="${SERVER_ROOT}/.venv/bin/python"
  [[ -x "${py}" ]] || py="python3"
  "${py}" "${SERVER_ROOT}/scripts/ci/check_profile_capability_escalation.py"
}

_run_dependency_vuln_gate() {
  local gate="${SERVER_ROOT}/../../scripts/ci/check_workspace_dependency_vulns.py"
  local py
  if [[ ! -f "${gate}" ]]; then
    echo "CI dep-vuln-gate: workspace gate script not present (standalone checkout); skipping"
    return 0
  fi
  py="${SERVER_ROOT}/.venv/bin/python"
  [[ -x "${py}" ]] || py="python3"
  "${py}" "${gate}" --offline
}

_run_prometheus_rules_semantic_check() {
  if ! command -v promtool >/dev/null 2>&1; then
    echo "ERROR: promtool is required for architecture gates (Prometheus rules semantic checks)." >&2
    return 1
  fi
  promtool check rules "${SERVER_ROOT}/deployments/prometheus/rules.yml"
}

myrm_ci_install_server_deps --reuse-venv
_run_fractal_docs
_run_md_refs
_run_import_resolvability
_run_module_reachability
_run_profile_capability_gate
_run_dependency_vuln_gate
_run_ruff
_run_pyright_unbound
_run_prometheus_rules_semantic_check
_run_pytest
echo "OK: server architecture gates"
