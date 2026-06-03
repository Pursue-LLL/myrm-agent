#!/usr/bin/env bash
# Install myrm-agent-harness into the server venv (auto-detects dev vs deploy).
#
# Modes (MYRM_HARNESS_INSTALL_MODE):
#   auto     - default: see _resolve_install_mode() below
#   pypi     - uv sync --frozen from PyPI (CI / OSS / Windows deploy after publish)
#   source   - build prod-like wheels from local harness for current platform
#   editable - editable install from MYRM_HARNESS_ROOT (monorepo local dev)
#
# Usage:
#   myrm setup                    # monorepo (editable when harness clone exists)
#   myrm harness install
#   MYRM_HARNESS_INSTALL_MODE=pypi myrm harness install
set -euo pipefail

MAINTAINER_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$(dirname "${MAINTAINER_DIR}")"
# shellcheck source=../lib/resolve_agent_root.sh
source "${SCRIPT_DIR}/lib/resolve_agent_root.sh"
# shellcheck source=../lib/resolve_monorepo_root.sh
source "${SCRIPT_DIR}/lib/resolve_monorepo_root.sh"

MONOREPO_ROOT="$(resolve_monorepo_root "${SCRIPT_DIR}/..")" || MONOREPO_ROOT=""
if [[ -n "${MONOREPO_ROOT}" ]]; then
  resolve_agent_paths "${MONOREPO_ROOT}"
else
  resolve_agent_paths "${SCRIPT_DIR}/.."
fi

SERVER_ROOT="${MYRM_SERVER_ROOT:-${SERVER_DIR}}"
HARNESS_ROOT="${MYRM_HARNESS_ROOT:-}"
SKIP_MATRIX_E2EE="${MYRM_HARNESS_SKIP_MATRIX_E2EE:-1}"

_resolve_platform_key() {
  case "$(uname -s)" in
    Linux)
      case "$(uname -m)" in
        aarch64|arm64) echo "linux-arm64" ;;
        *) echo "linux-x64" ;;
      esac
      ;;
    Darwin)
      case "$(uname -m)" in
        arm64) echo "darwin-arm64" ;;
        *) echo "darwin-x64" ;;
      esac
      ;;
    MINGW*|MSYS*|CYGWIN*)
      case "$(uname -m)" in
        aarch64|arm64) echo "win32-arm64" ;;
        *) echo "win32-x64" ;;
      esac
      ;;
    *)
      echo "Unsupported OS for harness source install: $(uname -s)" >&2
      exit 1
      ;;
  esac
}

_resolve_harness_root() {
  if [[ -n "${HARNESS_ROOT}" && -d "${HARNESS_ROOT}" ]]; then
    return 0
  fi
  local -a bases=()
  if [[ -n "${MONOREPO_ROOT}" ]]; then
    bases+=("${MONOREPO_ROOT}")
  fi
  bases+=("${AGENT_ROOT}" "${AGENT_ROOT}/..")
  local base
  for base in "${bases[@]}"; do
    if [[ -d "${base}/../myrm-agent-harness" ]]; then
      HARNESS_ROOT="$(cd "${base}/../myrm-agent-harness" && pwd)"
      return 0
    fi
    if [[ -d "${base}/myrm-agent-harness" ]]; then
      HARNESS_ROOT="$(cd "${base}/myrm-agent-harness" && pwd)"
      return 0
    fi
  done
  return 1
}

_resolve_install_mode() {
  if [[ "${MYRM_HARNESS_EDITABLE:-0}" == "1" ]]; then
    echo "editable"
    return 0
  fi
  local explicit="${MYRM_HARNESS_INSTALL_MODE:-auto}"
  if [[ "${explicit}" != "auto" ]]; then
    echo "${explicit}"
    return 0
  fi
  if [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "pypi"
    return 0
  fi
  if [[ "${MYRM_HARNESS_DEPLOY:-0}" == "1" ]]; then
    echo "source"
    return 0
  fi
  if _resolve_harness_root; then
    echo "editable"
    return 0
  fi
  echo "pypi"
}

_print_run_hint() {
  echo "Start: myrm start   (or myrm dev for backend only)"
}

_log_install_plan() {
  local mode="$1"
  local plat
  plat="$(_resolve_platform_key)"
  echo "📦 Platform: ${plat}"
  echo "📦 Harness install mode: ${mode} (MYRM_HARNESS_INSTALL_MODE=${MYRM_HARNESS_INSTALL_MODE:-auto})"
  case "${mode}" in
    editable) echo "   → local -e install; code changes apply after server restart" ;;
    source) echo "   → prod-like wheel for ${plat} from local harness build" ;;
    pypi) echo "   → PyPI frozen lock (CI / deploy / OSS)" ;;
  esac
}

_sync_server_deps() {
  local -a sync_args=(
    sync
    --frozen
    --all-extras
    --group
    dev
  )
  if [[ "${SKIP_MATRIX_E2EE}" == "1" ]]; then
    sync_args+=(--no-extra matrix-e2ee)
  fi
  uv "${sync_args[@]}"
}

_sync_server_deps_skip_harness() {
  local -a sync_args=(
    sync
    --frozen
    --no-install-package
    myrm-agent-harness
    --no-sources-package
    myrm-agent-harness
    --all-extras
    --group
    dev
  )
  if [[ "${SKIP_MATRIX_E2EE}" == "1" ]]; then
    sync_args+=(--no-extra matrix-e2ee)
  fi
  uv "${sync_args[@]}"
}

_verify_harness_distribution() {
  local verify_bin=""
  if [[ -x "${SERVER_ROOT}/.venv/bin/verify-harness-distribution" ]]; then
    verify_bin="${SERVER_ROOT}/.venv/bin/verify-harness-distribution"
  elif [[ -x "${SERVER_ROOT}/.venv/Scripts/verify-harness-distribution.exe" ]]; then
    verify_bin="${SERVER_ROOT}/.venv/Scripts/verify-harness-distribution.exe"
  else
    echo "verify-harness-distribution not found under ${SERVER_ROOT}/.venv" >&2
    exit 1
  fi
  "${verify_bin}"
}

_install_from_pypi() {
  echo "Installing server + harness from PyPI (uv sync --frozen)"
  if _sync_server_deps; then
    _verify_harness_distribution
    return 0
  fi
  if [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "uv sync --frozen failed in CI; refusing pip fallback." >&2
    echo "Run myrm harness sync-lock after PyPI publish." >&2
    exit 1
  fi
  echo "uv sync --frozen failed (PyPI packages may be missing); falling back to explicit pip install" >&2
  _sync_server_deps_skip_harness
  uv pip install "$(python3 docker/read_harness_pypi_spec.py)"
  _verify_harness_distribution
}

_install_from_source_build() {
  if ! _resolve_harness_root; then
    echo "Harness source not found. Clone private repo or use default PyPI install." >&2
    exit 1
  fi

  echo "Building production harness wheels from ${HARNESS_ROOT}"
  (
    cd "${HARNESS_ROOT}"
    uv sync --group build
    PY="${HARNESS_ROOT}/.venv/bin/python"
    [[ -x "${PY}" ]] || PY="${HARNESS_ROOT}/.venv/Scripts/python.exe"
    "${PY}" scripts/assemble_production.py
  )

  _sync_server_deps_skip_harness

  if [[ "$(uname -s)" == "Linux" ]]; then
    export TARGETPLATFORM="${TARGETPLATFORM:-linux/amd64}"
    chmod +x docker/install_harness_wheels.sh
    ./docker/install_harness_wheels.sh \
      "${HARNESS_ROOT}/build/core/wheels" \
      "${HARNESS_ROOT}/dist"
  else
    local plat core_dir core rel
    plat="$(_resolve_platform_key)"
    core_dir="${HARNESS_ROOT}/build/core/wheels/${plat}"
    core="$(ls "${core_dir}"/*.whl 2>/dev/null | head -n 1)"
    rel="$(ls "${HARNESS_ROOT}/dist"/myrm_agent_harness-*.whl 2>/dev/null | grep -v -- '-release\.whl$' | sort | tail -n 1)"
    if [[ -z "${core}" || -z "${rel}" ]]; then
      echo "Missing wheels under ${core_dir} or ${HARNESS_ROOT}/dist" >&2
      exit 1
    fi
    echo "Installing core=${core} release=${rel}"
    uv pip install "${core}" "${rel}"
    _verify_harness_distribution
  fi
}

cd "${SERVER_ROOT}"

INSTALL_MODE="$(_resolve_install_mode)"
_log_install_plan "${INSTALL_MODE}"

case "${INSTALL_MODE}" in
  editable)
    if ! _resolve_harness_root; then
      echo "Editable install requires a local harness clone (MYRM_HARNESS_ROOT)." >&2
      exit 1
    fi
    echo "Installing editable harness from ${HARNESS_ROOT}"
    _sync_server_deps_skip_harness
    uv pip install -e "${HARNESS_ROOT}[file-parsers,memory-sqlite,web,fastapi,retrieval,qdrant,image-processing,browser]"
    _verify_harness_distribution
    ;;
  pypi)
    _install_from_pypi
    ;;
  source)
    _install_from_source_build
    ;;
  release)
    echo "MYRM_HARNESS_INSTALL_MODE=release is removed; use pypi or auto." >&2
    exit 1
    ;;
  *)
    echo "Unknown MYRM_HARNESS_INSTALL_MODE=${INSTALL_MODE} (expected auto, pypi, source, or editable)" >&2
    exit 1
    ;;
esac

echo "Harness install OK (mode=${INSTALL_MODE})"
_print_run_hint
