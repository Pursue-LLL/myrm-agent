#!/usr/bin/env bash
# Install platform-matched @next/swc-* when Next.js optional dep was skipped (WASM fallback = 80s+ compiles).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
resolve_agent_paths "${REPO_ROOT}"

_resolve_bun() {
  if command -v bun >/dev/null 2>&1; then
    command -v bun
    return 0
  fi
  local candidate
  for candidate in "${HOME}/.bun/bin/bun" /opt/homebrew/bin/bun /usr/local/bin/bun; do
    if [[ -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

MYRM_BUN="$(_resolve_bun || true)"

_swc_pkg=""
if [[ -n "${MYRM_BUN}" ]]; then
  _runtime_platform="$("${MYRM_BUN}" -e 'process.stdout.write(`${process.platform}-${process.arch}`)')"
else
  _runtime_platform="$(uname -s)-$(uname -m)"
fi
case "${_runtime_platform}" in
  darwin-arm64 | Darwin-arm64) _swc_pkg="@next/swc-darwin-arm64" ;;
  darwin-x64 | Darwin-x86_64) _swc_pkg="@next/swc-darwin-x64" ;;
  linux-arm64 | Linux-arm64 | Linux-aarch64) _swc_pkg="@next/swc-linux-arm64-gnu" ;;
  linux-x64 | Linux-x86_64) _swc_pkg="@next/swc-linux-x64-gnu" ;;
esac

if [[ -z "${_swc_pkg}" ]]; then
  exit 0
fi

cd "${FRONTEND_DIR}"

if [[ -d "node_modules/${_swc_pkg}" ]] && compgen -G "node_modules/${_swc_pkg}/*.node" >/dev/null; then
  echo "✓ ${_swc_pkg} present"
  exit 0
fi

if [[ -d "node_modules/${_swc_pkg}" ]]; then
  echo "WARN: ${_swc_pkg} directory exists but native binary missing — reinstalling" >&2
  rm -rf "node_modules/${_swc_pkg}"
fi

if [[ -z "${MYRM_BUN}" ]]; then
  echo "WARN: bun not found; cannot install ${_swc_pkg}" >&2
  exit 0
fi

_next_ver="$("${MYRM_BUN}" -e "process.stdout.write(require('./package.json').dependencies.next.replace(/^\\^|~/, ''))")"
echo "📦 Installing ${_swc_pkg}@${_next_ver} (Next.js native SWC — avoids WASM slow compile)..."
"${MYRM_BUN}" install "${_swc_pkg}@${_next_ver}" --no-save
echo "✓ ${_swc_pkg} installed"
