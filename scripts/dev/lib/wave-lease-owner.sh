#!/usr/bin/env bash
# Stable lease ownership shared by E2E helper scripts.
set -euo pipefail

_wave_new_agent_id() {
  local prefix="$1"
  if [[ -n "${MYRM_WAVE_AGENT_ID:-}" ]]; then
    echo "${MYRM_WAVE_AGENT_ID}"
    return 0
  fi
  echo "${prefix}:parent-${PPID}"
}

_wave_reap_stale_lease_state() {
  local wave="$1"
  bash "${wave}" reap >/dev/null 2>&1 || true
  local dev_dir
  dev_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)/scripts/dev"
  if [[ -f "${dev_dir}/isolated_runtime.py" ]]; then
    python3 "${dev_dir}/isolated_runtime.py" prune >/dev/null 2>&1 || true
  fi
}

_wave_open_if_needed() {
  local wave="$1" agent_id="$2" status_json open_output
  status_json="$(bash "${wave}" status 2>/dev/null || true)"
  if [[ "${status_json}" == *'"status": "open"'* ]]; then
    echo "existing"
    return 0
  fi
  if ! open_output="$(bash "${wave}" --agent "${agent_id}" open 2>&1)"; then
    if [[ "${open_output}" == *"WAVE_ALREADY_OPEN:"* ]]; then
      echo "existing"
      return 0
    fi
    printf '%s\n' "${open_output}" >&2
    return 1
  fi
  echo "opened"
}

_wave_acquire_owned_lease() {
  local wave="$1" prefix="$2" lane="$3" namespace="${4:-}"
  local agent_id lease_json lease_id open_state close_output args
  agent_id="$(_wave_new_agent_id "${prefix}")"
  open_state="$(_wave_open_if_needed "${wave}" "${agent_id}")"
  args=(--agent "${agent_id}" lease acquire "${lane}" --ttl "${MYRM_WAVE_HELPER_TTL_SEC:-900}")
  if [[ -n "${namespace}" ]]; then
    args+=(--namespace "${namespace}")
  fi
  if ! lease_json="$(bash "${wave}" "${args[@]}" 2>&1)"; then
    if [[ "${open_state}" == "opened" ]] && ! close_output="$(bash "${wave}" --agent "${agent_id}" close 2>&1)"; then
      printf 'WAVE_ACQUIRE_CLEANUP_FAIL: %s\n' "${close_output}" >&2
    fi
    printf '%s\n' "${lease_json}" >&2
    return 1
  fi
  lease_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["lease"]["leaseId"])' <<<"${lease_json}")"
  printf '%s\n' "${lease_id}"
}

_wave_acquire_owned_lease_with_wait() {
  local wave="$1" prefix="$2" lane="$3" namespace="${4:-}"
  local wait_sec="${MYRM_E2E_LEASE_WAIT_SEC:-900}"
  local poll_sec="${MYRM_E2E_LEASE_POLL_SEC:-15}"
  local started_at="$SECONDS"
  local lease_id lease_stderr lease_stderr_path
  _wave_reap_stale_lease_state "${wave}"
  while true; do
    lease_stderr_path="$(mktemp)"
    if lease_id="$(_wave_acquire_owned_lease "${wave}" "${prefix}" "${lane}" "${namespace}" 2>"${lease_stderr_path}")"; then
      rm -f "${lease_stderr_path}"
      printf '%s\n' "${lease_id}"
      return 0
    fi
    lease_stderr="$(cat "${lease_stderr_path}")"
    rm -f "${lease_stderr_path}"
    if [[ "${lease_stderr}" != *"LEASE_DENIED"* ]]; then
      printf '%s\n' "${lease_stderr}" >&2
      return 1
    fi
    if (( SECONDS - started_at >= wait_sec )); then
      printf '%s\n' "${lease_stderr}" >&2
      echo "E2E_LEASE_WAIT_TIMEOUT: lane=${lane} waited ${wait_sec}s — see wave status above (exit 3)" >&2
      return 3
    fi
    echo "E2E_LEASE_WAIT: lane=${lane} busy — retry in ${poll_sec}s (elapsed=$((SECONDS - started_at))s)" >&2
    _wave_reap_stale_lease_state "${wave}"
    sleep "${poll_sec}"
  done
}

_wave_release_owned_lease() {
  local wave="$1" prefix="$2" lease_id="$3" agent_id
  [[ -n "${lease_id}" ]] || return 0
  agent_id="$(_wave_new_agent_id "${prefix}")"
  bash "${wave}" --agent "${agent_id}" lease release "${lease_id}" >/dev/null
}

_wave_release_owned_lease_and_close_if_idle() {
  local wave="$1" prefix="$2" lease_id="$3" agent_id
  [[ -n "${lease_id}" ]] || return 0
  agent_id="$(_wave_new_agent_id "${prefix}")"
  bash "${wave}" --agent "${agent_id}" lease release "${lease_id}" --close-wave-if-idle >/dev/null
}
