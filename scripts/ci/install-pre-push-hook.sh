#!/usr/bin/env bash
# Install myrm-agent pre-push hook (architecture gates). Idempotent.
set -euo pipefail

AGENT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MARKER="# myrm-agent-architecture-gates"
GATES_SCRIPT="${AGENT_ROOT}/myrm-agent-server/scripts/ci/run_architecture_gates.sh"

if ! git -C "${AGENT_ROOT}" rev-parse --git-dir >/dev/null 2>&1; then
  echo "ERROR: ${AGENT_ROOT} is not inside a git repository." >&2
  exit 1
fi

if [[ ! -x "${GATES_SCRIPT}" ]]; then
  echo "ERROR: missing executable ${GATES_SCRIPT}" >&2
  exit 1
fi

GIT_DIR="$(cd "$(git -C "${AGENT_ROOT}" rev-parse --git-dir)" && pwd)"
HOOKS_DIR="${GIT_DIR}/hooks"
HOOK_PATH="${HOOKS_DIR}/pre-push"

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
exec bash "${GATES_SCRIPT}"
EOF

chmod +x "${HOOK_PATH}"
echo "Installed myrm-agent pre-push hook: ${HOOK_PATH}"
