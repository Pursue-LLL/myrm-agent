#!/usr/bin/env bash
# Live integration gate: cleanup pause blocks Agent paths and direct next dev.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FRONTEND_DIR="${REPO_ROOT}/myrm-agent-frontend"
PAUSE_PY="${SCRIPT_DIR}/lib/e2e_core/frontend_dev_pause.py"
DEV_STACK="${SCRIPT_DIR}/dev-stack.sh"
PAUSE_DIR="$(mktemp -d)"
PROBE_PORT="${MYRM_FRONTEND_DEV_PAUSE_PROBE_PORT:-13099}"

cleanup_probe() {
  export MYRM_FRONTEND_DEV_PAUSE_DIR="${PAUSE_DIR}"
  python3 "${PAUSE_PY}" clear >/dev/null 2>&1 || true
  lsof -iTCP:"${PROBE_PORT}" -sTCP:LISTEN -t 2>/dev/null | while read -r pid; do kill -TERM "${pid}" 2>/dev/null || true; done
  rm -rf "${PAUSE_DIR}" 2>/dev/null || true
}

trap cleanup_probe EXIT

export MYRM_FRONTEND_DEV_PAUSE_DIR="${PAUSE_DIR}"
PREFLIGHT_PY="${PREFLIGHT_PY:-python3}"

echo "FRONTEND_PAUSE_GATE: using isolated pause dir ${PAUSE_DIR}"

"${PREFLIGHT_PY}" "${PAUSE_PY}" write --seconds 600 --reason verify-gate >/dev/null
if ! "${PREFLIGHT_PY}" "${PAUSE_PY}" check >/dev/null; then
  echo "FRONTEND_PAUSE_GATE_FAIL: write/check paused" >&2
  exit 1
fi
echo "FRONTEND_PAUSE_GATE_OK: python write/check"

ensure_out="$(
  MYRM_FRONTEND_ENSURE_INNER=1 MYRM_FRONTEND_DEV_PAUSE_DIR="${PAUSE_DIR}" \
    bash "${DEV_STACK}" frontend-only ensure 2>&1
)" || ensure_rc=$?
ensure_rc="${ensure_rc:-0}"
if [[ "${ensure_rc}" -ne 0 ]] || ! grep -q 'STACK_FRONTEND_ONLY_ENSURE_SKIP' <<<"${ensure_out}"; then
  echo "FRONTEND_PAUSE_GATE_FAIL: dev-stack ensure did not SKIP" >&2
  echo "${ensure_out}" >&2
  exit 1
fi
echo "FRONTEND_PAUSE_GATE_OK: dev-stack frontend-only ensure SKIP"

heal_out="$(
  MYRM_SUPERVISOR_BYPASS=1 MYRM_E2E_SHPOIB=1 MYRM_FRONTEND_DEV_PAUSE_DIR="${PAUSE_DIR}" \
    bash "${DEV_STACK}" frontend-only ensure 2>&1
)" || heal_rc=$?
heal_rc="${heal_rc:-0}"
if [[ "${heal_rc}" -ne 0 ]] || ! grep -q 'paused_skip' <<<"${heal_out}"; then
  echo "FRONTEND_PAUSE_GATE_FAIL: warm_ui heal path did not paused_skip" >&2
  echo "${heal_out}" >&2
  exit 1
fi
echo "FRONTEND_PAUSE_GATE_OK: warm_ui attach paused_skip"

dev_out="$(
  cd "${FRONTEND_DIR}"
  MYRM_FRONTEND_DEV_PAUSE_DIR="${PAUSE_DIR}" MYRM_FRONTEND_PORT="${PROBE_PORT}" \
    bun run scripts/dev.ts 2>&1
)" || dev_rc=$?
dev_rc="${dev_rc:-0}"
if [[ "${dev_rc}" -ne 0 ]] || ! grep -qi 'paused\|refusing start' <<<"${dev_out}"; then
  echo "FRONTEND_PAUSE_GATE_FAIL: dev.ts did not refuse while paused" >&2
  echo "${dev_out}" >&2
  exit 1
fi
if lsof -iTCP:"${PROBE_PORT}" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "FRONTEND_PAUSE_GATE_FAIL: dev.ts left listener on :${PROBE_PORT}" >&2
  exit 1
fi
echo "FRONTEND_PAUSE_GATE_OK: dev.ts refuse + no listener"

next_log="$(mktemp)"
(
  cd "${FRONTEND_DIR}"
  MYRM_FRONTEND_DEV_PAUSE_DIR="${PAUSE_DIR}" \
    bunx next dev -p "${PROBE_PORT}"
) >"${next_log}" 2>&1 &
next_pid=$!
sleep 8
kill "${next_pid}" 2>/dev/null || true
wait "${next_pid}" 2>/dev/null || true
next_out="$(cat "${next_log}")"
rm -f "${next_log}"
if ! grep -qi 'paused\|refusing' <<<"${next_out}"; then
  echo "FRONTEND_PAUSE_GATE_FAIL: direct next dev was not blocked by next.config gate" >&2
  echo "${next_out}" >&2
  exit 1
fi
if lsof -iTCP:"${PROBE_PORT}" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "FRONTEND_PAUSE_GATE_FAIL: direct next dev left listener on :${PROBE_PORT}" >&2
  exit 1
fi
echo "FRONTEND_PAUSE_GATE_OK: direct bunx next dev blocked"

"${PREFLIGHT_PY}" "${PAUSE_PY}" clear >/dev/null
if "${PREFLIGHT_PY}" "${PAUSE_PY}" check >/dev/null 2>&1; then
  echo "FRONTEND_PAUSE_GATE_FAIL: clear-pause did not lift gate" >&2
  exit 1
fi
echo "FRONTEND_PAUSE_GATE_OK: clear-pause lifts gate"

echo "FRONTEND_PAUSE_GATE_OK: all integration checks passed"
