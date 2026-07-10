#!/usr/bin/env bash
# Install platform-matched @next/swc-* when Next.js optional dep was skipped (WASM fallback = 80s+ compiles).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
resolve_agent_paths "${REPO_ROOT}"

_swc_pkg=""
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) _swc_pkg="@next/swc-darwin-arm64" ;;
  Darwin-x86_64) _swc_pkg="@next/swc-darwin-x64" ;;
  Linux-arm64 | Linux-aarch64) _swc_pkg="@next/swc-linux-arm64-gnu" ;;
  Linux-x86_64) _swc_pkg="@next/swc-linux-x64-gnu" ;;
esac

if [[ -z "${_swc_pkg}" ]]; then
  exit 0
fi

cd "${FRONTEND_DIR}"

if [[ -d "node_modules/${_swc_pkg}" ]]; then
  echo "✓ ${_swc_pkg} present"
  exit 0
fi

if ! command -v bun >/dev/null 2>&1; then
  echo "WARN: bun not found; cannot install ${_swc_pkg}" >&2
  exit 0
fi

_next_ver="$(bun -e "process.stdout.write(require('./package.json').dependencies.next.replace(/^\\^|~/, ''))")"
echo "📦 Installing ${_swc_pkg}@${_next_ver} (Next.js native SWC — avoids WASM slow compile)..."
bun install "${_swc_pkg}@${_next_ver}" --no-save
echo "✓ ${_swc_pkg} installed"
