#!/usr/bin/env bash
# Initialize / sync product-repo submodules under vortexai (monorepo root).
set -euo pipefail

MAINTAINER_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_DIR="$(dirname "${MAINTAINER_DIR}")"
# shellcheck source=../lib/resolve_monorepo_root.sh
source "${SCRIPT_DIR}/lib/resolve_monorepo_root.sh"

ROOT="${MYRM_MONOREPO_ROOT:-}"
if [[ -z "${ROOT}" ]]; then
  ROOT="$(resolve_monorepo_root "${SCRIPT_DIR}/..")" || true
fi
if [[ -z "${ROOT}" || ! -f "${ROOT}/.gitmodules" ]]; then
  echo "Missing monorepo root (.gitmodules). Run ./myrm submodules from vortexai root." >&2
  exit 1
fi

cd "${ROOT}"

echo "== Sync submodule URLs"
git submodule sync --recursive

echo "== Init + update submodules"
git submodule update --init --recursive

drift=0
while IFS= read -r _path; do
  [[ -z "${_path}" ]] && continue
  recorded="$(git rev-parse "HEAD:${_path}" 2>/dev/null || true)"
  checkout="$(git -C "${_path}" rev-parse HEAD 2>/dev/null || true)"
  if [[ -n "${recorded}" && -n "${checkout}" && "${recorded}" != "${checkout}" ]]; then
    echo "DRIFT ${_path}: recorded=${recorded:0:7} checkout=${checkout:0:7}" >&2
    drift=1
  fi
done < <(git config -f .gitmodules --get-regexp '^submodule\..*\.path$' | awk '{print $2}')

if [[ "${drift}" -eq 1 ]]; then
  echo "Submodule pointer drift. Commit/push in submodule, then bump pointer in vortexai." >&2
  exit 1
fi

echo ""
echo "Done. Product repos ready."
