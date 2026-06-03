#!/usr/bin/env bash
# After harness publish to PyPI: refresh myrm-agent-server/uv.lock from registry.
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

python3 "${MAINTAINER_DIR}/check_harness_pypi.py"

cd "${SERVER_DIR}"
uv lock --upgrade-package myrm-agent-harness
echo "uv.lock updated from PyPI"
