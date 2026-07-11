#!/usr/bin/env bash
# Dev stack epoch — SSOT for backend generation (parallel Agent drift detection).
# Sourced by dev-stack.sh and backend_bg.sh; do not execute directly.
set -euo pipefail

_stack_epoch_state_dir() {
  echo "${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}"
}

_stack_epoch_file() {
  echo "$(_stack_epoch_state_dir)/stack-epoch.json"
}

_harness_fingerprint() {
  local server_dir="$1"
  local py="${server_dir}/.venv/bin/python"
  [[ -x "${py}" ]] || return 0
  cd "${server_dir}" && "${py}" -c "
import pathlib
try:
    import myrm_agent_harness
    from myrm_agent_harness._distribution import get_distribution_mode
    pkg = pathlib.Path(myrm_agent_harness.__file__).resolve().parent
    print(f'{get_distribution_mode().value}:{pkg}')
except Exception:
    print('unknown')
" 2>/dev/null || echo "unknown"
}

_bump_stack_epoch() {
  local backend_pid="${1:-}"
  local server_dir="${2:-}"
  local state_dir epoch_file next_epoch started_at harness_fp
  state_dir="$(_stack_epoch_state_dir)"
  epoch_file="$(_stack_epoch_file)"
  mkdir -p "${state_dir}"

  next_epoch=1
  if [[ -f "${epoch_file}" ]]; then
    next_epoch="$(python3 -c "
import json
from pathlib import Path
p = Path('${epoch_file}')
if p.is_file():
    data = json.loads(p.read_text())
    print(int(data.get('epoch', 0)) + 1)
else:
    print(1)
" 2>/dev/null || echo 1)"
  fi

  started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  harness_fp=""
  if [[ -n "${server_dir}" ]]; then
    harness_fp="$(_harness_fingerprint "${server_dir}")"
  fi

  python3 -c "
import json
from pathlib import Path
payload = {
    'epoch': int('${next_epoch}'),
    'backend_pid': int('${backend_pid}') if '${backend_pid}'.isdigit() else None,
    'started_at': '${started_at}',
    'harness_fingerprint': '${harness_fp}',
}
path = Path('${epoch_file}')
path.write_text(json.dumps(payload, indent=2) + '\n')
print(payload['epoch'])
"
}

_read_stack_epoch() {
  local epoch_file
  epoch_file="$(_stack_epoch_file)"
  [[ -f "${epoch_file}" ]] || return 1
  python3 -c "
import json, sys
from pathlib import Path
data = json.loads(Path('${epoch_file}').read_text())
print(data.get('epoch', ''))
" 2>/dev/null
}

_clear_stack_epoch() {
  rm -f "$(_stack_epoch_file)" 2>/dev/null || true
}
