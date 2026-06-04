#!/usr/bin/env bash
# Install myrm-agent pre-push hook (architecture gates). Idempotent.
set -euo pipefail

AGENT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOKS_DIR="${AGENT_ROOT}/.git/hooks"
HOOK_PATH="${HOOKS_DIR}/pre-push"
MARKER="# myrm-agent-architecture-gates"

if [[ ! -d "${AGENT_ROOT}/.git" ]]; then
  echo "ERROR: ${AGENT_ROOT} is not a git repository root." >&2
  exit 1
fi

if [[ -f "${HOOK_PATH}" ]] && grep -q "${MARKER}" "${HOOK_PATH}" 2>/dev/null; then
  echo "pre-push hook already installed"
  exit 0
fi

mkdir -p "${HOOKS_DIR}"
if [[ -f "${HOOK_PATH}" ]]; then
  cp "${HOOK_PATH}" "${HOOK_PATH}.bak.$(date +%s)"
fi

cat > "${HOOK_PATH}" <<EOF
#!/usr/bin/env bash
${MARKER}
set -euo pipefail
exec bash myrm-agent-server/scripts/ci/run_architecture_gates.sh
EOF

chmod +x "${HOOK_PATH}"
echo "Installed ${HOOK_PATH}"
