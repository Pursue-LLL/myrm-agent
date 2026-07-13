#!/usr/bin/env bash
# Stable lease ownership shared by E2E helper scripts.
set -euo pipefail

_wave_lease_owner_dir() {
  echo "${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}/lease-owners"
}

_wave_new_agent_id() {
  local prefix="$1"
  if [[ -n "${MYRM_WAVE_AGENT_ID:-}" ]]; then
    echo "${MYRM_WAVE_AGENT_ID}"
    return 0
  fi
  python3 - "${prefix}" <<'PY'
import sys
import uuid

print(f"{sys.argv[1]}:{uuid.uuid4().hex}")
PY
}

_wave_owner_file() {
  local lease_id="$1"
  echo "$(_wave_lease_owner_dir)/${lease_id}.owner"
}

_wave_store_owner() {
  local lease_id="$1" agent_id="$2" owner_dir owner_file temporary
  owner_dir="$(_wave_lease_owner_dir)"
  owner_file="$(_wave_owner_file "${lease_id}")"
  temporary="${owner_file}.$$"
  mkdir -p "${owner_dir}"
  printf '%s\n' "${agent_id}" >"${temporary}"
  mv "${temporary}" "${owner_file}"
}

_wave_load_owner() {
  local lease_id="$1" owner_file
  owner_file="$(_wave_owner_file "${lease_id}")"
  if [[ ! -f "${owner_file}" ]]; then
    echo "LEASE_OWNER_STATE_MISSING: ${owner_file}" >&2
    return 1
  fi
  tr -d '[:space:]' <"${owner_file}"
}

_wave_open_if_needed() {
  local wave="$1" agent_id="$2" status_json
  status_json="$(bash "${wave}" status 2>/dev/null || true)"
  if [[ "${status_json}" != *'"status": "open"'* ]]; then
    bash "${wave}" --agent "${agent_id}" open >/dev/null
  fi
}

_wave_acquire_owned_lease() {
  local wave="$1" prefix="$2" lane="$3" namespace="${4:-}"
  local agent_id lease_json lease_id args
  agent_id="$(_wave_new_agent_id "${prefix}")"
  _wave_open_if_needed "${wave}" "${agent_id}"
  args=(--agent "${agent_id}" lease acquire "${lane}" --ttl "${MYRM_WAVE_HELPER_TTL_SEC:-900}")
  if [[ -n "${namespace}" ]]; then
    args+=(--namespace "${namespace}")
  fi
  lease_json="$(bash "${wave}" "${args[@]}")"
  lease_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["lease"]["leaseId"])' <<<"${lease_json}")"
  _wave_store_owner "${lease_id}" "${agent_id}"
  printf '%s\n' "${lease_id}"
}

_wave_release_owned_lease() {
  local wave="$1" lease_id="$2" agent_id owner_file
  [[ -n "${lease_id}" ]] || return 0
  agent_id="$(_wave_load_owner "${lease_id}")"
  bash "${wave}" --agent "${agent_id}" lease release "${lease_id}" >/dev/null
  owner_file="$(_wave_owner_file "${lease_id}")"
  rm -f "${owner_file}"
}
