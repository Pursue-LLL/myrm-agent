#!/usr/bin/env bash
# Start myrm-agent-server on :8080 in background. Sets SERVER_DIR, writes pid/log under server dir.
# Health-aware self-healing (R61/R61-A):
#   - port truth SSOT: the lsof listener on the backend port is the only
#     authority for liveness; a desynced pid record is re-synced to the port
#     owner, never kill a healthy listener
#   - health probe fail + leases=0: kill+restart the port owner (not the record)
#   - health probe fail + leases>0: defer kill (protect parallel E2E)
#   - health probe fail + leases>0 + SUPERVISOR/WAVE bypass: SHC leader crash heal may kill+restart
#   - source drift + leases>0: defer reload + record-pending (R31-G SMP)
#   - cold-start health wait requires new_pid to own the listen port before success
# [POS] Dev 栈 backend 进程管理。source stack-epoch.sh 获取 _wave_active_lease_count。
set -euo pipefail

# shellcheck source=dev_state_paths.sh
source "${BASH_SOURCE[0]%/*}/dev_state_paths.sh"

_require_harness_editable_for_monorepo() {
  local server_dir="$1"
  local agent_root harness_src expected_src py mode pkg_dir

  if [[ "${MYRM_SKIP_HARNESS_EDITABLE_CHECK:-0}" == "1" ]]; then
    return 0
  fi

  agent_root="$(cd "${server_dir}/.." && pwd)"
  harness_src="$(cd "${agent_root}/.." 2>/dev/null && pwd)/myrm-agent-harness/src/myrm_agent_harness"
  if [[ ! -d "${harness_src}" ]]; then
    return 0
  fi
  expected_src="$(cd "${harness_src}" && pwd)"

  py=""
  if [[ -x "${server_dir}/.venv/bin/python" ]]; then
    py="${server_dir}/.venv/bin/python"
  elif [[ -x "${server_dir}/.venv/Scripts/python.exe" ]]; then
    py="${server_dir}/.venv/Scripts/python.exe"
  fi
  if [[ -z "${py}" ]]; then
    return 0
  fi

  if ! {
    read -r mode
    read -r pkg_dir
  } < <(
    cd "${server_dir}" && "${py}" -c "
import pathlib
import myrm_agent_harness
from myrm_agent_harness.runtime.install_guard.probe import get_distribution_mode
from myrm_agent_harness.agent.artifacts.ui_registry import bind_run_message_id  # noqa: F401
pkg = pathlib.Path(myrm_agent_harness.__file__).resolve().parent
print(get_distribution_mode().value)
print(pkg)
" 2>/dev/null
  ); then
    echo "ERROR: monorepo harness source present but myrm_agent_harness import failed." >&2
    echo "   Run: from open-perplexity root  ./myrm harness install  then retry." >&2
    echo "   If a stale backend is running:  myrm stop" >&2
    exit 1
  fi

  if [[ "${mode}" != "source" || "${pkg_dir}" != "${expected_src}" ]]; then
    echo "ERROR: Server venv harness is not monorepo editable source." >&2
    echo "   mode=${mode}  import=${pkg_dir}" >&2
    echo "   expected=${expected_src}" >&2
    echo "   pytest may pass while live agent-stream misses ui_update (stale wheel)." >&2
    echo "   Fix: from open-perplexity root run  ./myrm harness install  then  myrm stop  and restart." >&2
    echo "   PyPI consumer test only:  MYRM_SKIP_HARNESS_EDITABLE_CHECK=1 myrm dev" >&2
    exit 1
  fi
}

_start_backend_bg() {
  local server_dir="$1"
  local state_dir
  state_dir="$(dev_state_dir)"
  local backend_port="${MYRM_BACKEND_PORT:-${PORT:-8080}}"
  local pid_file="${MYRM_BACKEND_PID_FILE:-${state_dir}/backend.pid}"
  local log_file="${MYRM_BACKEND_LOG_FILE:-${state_dir}/backend.log}"
  local identity_file="${MYRM_BACKEND_IDENTITY_FILE:-${state_dir}/backend-process.json}"
  local identity_helper
  identity_helper="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/e2e_core/process_identity.py"
  local runtime_id="${MYRM_RUNTIME_NAMESPACE:-shared}"
  local health_url
  if [[ "${MYRM_PRIVATE_BACKEND:-}" == "1" || "${MYRM_E2E_PRIVATE_BACKEND:-}" == "1" ]]; then
    health_url="http://127.0.0.1:${backend_port}/api/v1/health"
  else
    health_url="${E2E_API_BASE:-http://127.0.0.1:${backend_port}}/api/v1/health"
  fi
  local health_timeout="${MYRM_BACKEND_HEALTH_TIMEOUT_SEC:-8}"
  mkdir -p "${state_dir}"

  local py=""
  if [[ -x "${server_dir}/.venv/bin/python" ]]; then
    py="${server_dir}/.venv/bin/python"
  elif [[ -x "${server_dir}/.venv/Scripts/python.exe" ]]; then
    py="${server_dir}/.venv/Scripts/python.exe"
  fi
  if [[ -z "${py}" ]]; then
    echo "ERROR: no .venv python. Run: myrm setup" >&2
    return 1
  fi

  # 端口真值 SSOT：lsof 的实际 listener 是 backend 存活性的唯一权威。
  # pid_file / identity 只是记录；记录与端口 owner 失步时以端口 owner 为准，
  # 绝不 kill 健康 listener（否则 kill 的只是 phantom 记录，真 owner 仍在服务，
  # 新实例永远抢不到端口，无限重启 + 进程堆积）。
  local port_owner_pid=""
  port_owner_pid="$(lsof -nP -iTCP:"${backend_port}" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"

  # 冷启动前端口回收标记：某分支决定重建时，先杀真 owner，再等端口释放。
  local need_rebuild=0
  local rebuild_target=""

  if [[ -f "${pid_file}" ]]; then
    local old_pid
    old_pid="$(cat "${pid_file}")"

    if [[ -n "${port_owner_pid}" ]]; then
      # ---- 端口有监听者：owner 是唯一真值，记录无条件同步到 owner ----
      if ! "${py}" "${identity_helper}" record \
        --pid "${port_owner_pid}" \
        --identity-file "${identity_file}" \
        --runtime-id "${runtime_id}" \
        --role backend \
        --expected-command-token run.py >/dev/null 2>&1; then
        echo "STACK_FAIL: :${backend_port} owned by non-backend pid ${port_owner_pid} — refusing to reclaim foreign process" >&2
        return 1
      fi
      if [[ "${port_owner_pid}" != "${old_pid}" ]]; then
        echo "STACK_SYNC: backend record ${old_pid} → port owner ${port_owner_pid}" >&2
      fi
      echo "${port_owner_pid}" > "${pid_file}"

      # owner 健康 → 走 drift 检查；不健康 → 重试 3 次仍失败才重建（抗瞬时负载误杀）。
      local owner_healthy=0
      local retry_i
      for retry_i in 1 2 3; do
        if curl -sf --max-time "${health_timeout}" "${health_url}" >/dev/null 2>&1; then
          owner_healthy=1
          break
        fi
        sleep 2
      done

      if [[ "${owner_healthy}" -eq 1 ]]; then
        _require_harness_editable_for_monorepo "${server_dir}"
        local stack_epoch_lib stored_fp current_fp
        stack_epoch_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-epoch.sh"
        if [[ -f "${stack_epoch_lib}" ]]; then
          # shellcheck source=stack-epoch.sh
          source "${stack_epoch_lib}"
          if [[ ! -f "$(_stack_epoch_file)" ]]; then
            _bump_stack_epoch "${port_owner_pid}" "${server_dir}" >/dev/null || true
          fi
          stored_fp="$(_read_stack_epoch_source_fingerprint)"
          current_fp="$(_backend_source_fingerprint "${server_dir}")"
          if [[ -n "${current_fp}" && ( -z "${stored_fp}" || "${stored_fp}" != "${current_fp}" ) ]]; then
            local monorepo_root agent_root active_leases policy_py defer_reason drift_action
            agent_root="$(cd "${server_dir}/.." && pwd)"
            monorepo_root="$(cd "${agent_root}/.." && pwd)"
            active_leases="$(_wave_active_lease_count "${monorepo_root}")"
            policy_py="$(cd "$(dirname "${BASH_SOURCE[0]}")/e2e_core" && pwd)/stack_mutation_policy.py"
            defer_reason="backend_source_drift"
            if [[ -z "${stored_fp}" ]]; then
              defer_reason="backend_source_fingerprint_missing"
            fi
            python3 "${policy_py}" record-pending \
              --state-dir "${state_dir}" \
              --reason "${defer_reason}" \
              --server-dir "${server_dir}" >/dev/null 2>&1 || true

            # A healthy SHARED backend is immutable for daily attach, watchdog,
            # coordinator and crash-heal paths. Source changes belong to a
            # PRIVATE epoch; only an explicit maintenance command may promote
            # them to :8080, and even that must fail closed while any logical
            # SHARED session is live (PREPARING included, not just wave leases).
            drift_action="$(python3 "${policy_py}" decide-drift \
              --active-leases "${active_leases}" --drift-pending 1 2>/dev/null || echo defer)"
            if [[ "${MYRM_SHARED_BACKEND_MAINTENANCE:-0}" != "1" || "${drift_action}" != "apply" ]]; then
              echo "STACK_DRIFT_PENDING: keep healthy shared backend pid=${port_owner_pid}; use PRIVATE for changed backend code or explicit maintenance promotion" >&2
              echo "Backend already running (pid ${port_owner_pid})"
              return 0
            fi
            if [[ -z "${stored_fp}" ]]; then
              echo "STACK_WARN: shared backend missing source_fingerprint — reloading pid=${port_owner_pid}" >&2
            else
              echo "STACK_WARN: shared backend source drift detected — reloading pid=${port_owner_pid}" >&2
            fi
            need_rebuild=1
            rebuild_target="${port_owner_pid}"
          else
            if [[ "${runtime_id}" == "shared" ]]; then
              python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")/e2e_core" && pwd)/stack_mutation_policy.py" \
                clear-pending --state-dir "${state_dir}" >/dev/null 2>&1 || true
            fi
            echo "Backend already running (pid ${port_owner_pid})"
            return 0
          fi
        else
          echo "Backend already running (pid ${port_owner_pid})"
          return 0
        fi
      else
        # owner 存在但连续 3 次探活失败：只有确认没有活跃 peer 时才可
        # kill 真 owner。共享并行会话期间必须保留 owner，避免一次探活
        # 抖动把其他 session 的 backend 一并中断；特权 crash-heal 只在
        # 已明确授权的 supervisor/wave recovery 路径允许重建。
        local guard_root strict_active_leases
        guard_root="$(cd "${server_dir}/../.." && pwd)"
        strict_active_leases="$(_wave_active_lease_count_strict "${guard_root}")"
        if [[ "${strict_active_leases}" == "unknown" ]]; then
          echo "STACK_DEFER: backend on :${backend_port} unhealthy after retries (pid=${port_owner_pid}); lease state unavailable — preserving listener" >&2
          return 1
        fi
        if [[ "${strict_active_leases}" -gt 0 ]] \
          && [[ "${MYRM_SUPERVISOR_BYPASS:-0}" != "1" ]] \
          && [[ "${MYRM_WAVE_GATE_BYPASS:-0}" != "1" ]]; then
          echo "STACK_DEFER: backend on :${backend_port} unhealthy after retries (pid=${port_owner_pid}); active leases=${strict_active_leases} — preserving listener" >&2
          return 1
        fi
        echo "STACK_HEAL: backend on :${backend_port} unhealthy after retries (pid=${port_owner_pid}); active leases=${strict_active_leases} — kill and restart" >&2
        need_rebuild=1
        rebuild_target="${port_owner_pid}"
      fi
    else
      # ---- 端口无监听者：记录 pid 若存活则是 phantom/僵尸，verify 后回收 ----
      if dev_pid_alive "${old_pid}"; then
        if "${py}" "${identity_helper}" verify \
          --identity-file "${identity_file}" \
          --expected-pid "${old_pid}" \
          --expected-runtime-id "${runtime_id}" >/dev/null 2>&1; then
          echo "STACK_HEAL: backend pid ${old_pid} not listening on :${backend_port} — kill and restart" >&2
          need_rebuild=1
          rebuild_target="${old_pid}"
        else
          echo "STACK_WARN: stale backend record pid ${old_pid} (identity mismatch) — discarding record" >&2
        fi
      fi
      rm -f "${pid_file}" "${identity_file}"
    fi
  else
    # 无 pid_file 但端口被 backend 占用：接管记录，不重建（端口 owner 是权威）。
    if [[ -n "${port_owner_pid}" ]]; then
      if ! "${py}" "${identity_helper}" record \
        --pid "${port_owner_pid}" \
        --identity-file "${identity_file}" \
        --runtime-id "${runtime_id}" \
        --role backend \
        --expected-command-token run.py >/dev/null 2>&1; then
        echo "STACK_FAIL: :${backend_port} owned by non-backend pid ${port_owner_pid} — refusing to reclaim foreign process" >&2
        return 1
      fi
      echo "${port_owner_pid}" > "${pid_file}"
      echo "Backend already running (pid ${port_owner_pid})"
      return 0
    fi
  fi

  # ---- 重建：kill 真 owner（若有），等待 LISTEN 端口释放后再冷启动 ----
  if [[ "${need_rebuild}" -eq 1 ]]; then
    if [[ -n "${rebuild_target}" ]] && dev_pid_alive "${rebuild_target}"; then
      kill -TERM "${rebuild_target}" 2>/dev/null || true
      local wait_i
      for wait_i in $(seq 1 20); do
        dev_pid_alive "${rebuild_target}" || break
        sleep 0.25
      done
      if dev_pid_alive "${rebuild_target}"; then
        kill -KILL "${rebuild_target}" 2>/dev/null || true
      fi
    fi
    local free_i
    for free_i in $(seq 1 20); do
      if ! lsof -nP -iTCP:"${backend_port}" -sTCP:LISTEN -t >/dev/null 2>&1; then
        break
      fi
      sleep 0.5
    done
    rm -f "${pid_file}" "${identity_file}"
  fi

  export DEPLOY_MODE="${DEPLOY_MODE:-local}"
  export HOST="${HOST:-127.0.0.1}"
  export PORT="${backend_port}"
  # SQLite is single-writer: a large async pool only widens write-lock
  # contention across parallel E2E sessions. Keep the pool modest and lean on
  # the busy_timeout PRAGMA (which waits on the aiosqlite worker thread without
  # blocking the event loop) to absorb short write bursts.
  export SQLITE_POOL_SIZE="${SQLITE_POOL_SIZE:-8}"
  export SQLITE_POOL_MAX_OVERFLOW="${SQLITE_POOL_MAX_OVERFLOW:-8}"
  export SQLITE_BUSY_TIMEOUT_MS="${SQLITE_BUSY_TIMEOUT_MS:-15000}"
  export MYRM_STACK_EPOCH_FILE="${MYRM_STACK_EPOCH_FILE:-${state_dir}/stack-epoch.json}"
  # Child backend must run under the real user home: sandboxed HOME (e.g.
  # ~/.cursor2) would split harness data into ~/.cursor2/.myrm, desyncing
  # memory/cron/task state from the rest of the stack.
  export_spawn_home

  _require_harness_editable_for_monorepo "${server_dir}"

  cd "${server_dir}"
  # Dev log is append-only; truncate on fresh start to avoid unbounded growth.
  : >"${log_file}"
  export PYTHONUNBUFFERED=1
  # Record $! against the Python backend, not a nohup wrapper (macOS ps shows "(nohup)").
  # macOS has no setsid(1). Without a dedicated session the backend inherits the
  # caller's process group and dies whenever that group is signalled (test
  # cleanup, supervisor kill). Use a tiny Python launcher that calls
  # os.setsid() before exec'ing run.py, guaranteeing an independent session on
  # every platform. The launcher keeps the exact argv of run.py so the
  # ownership identity record (expected-command-token "run.py") stays valid.
  if command -v setsid >/dev/null 2>&1; then
    setsid "${py}" run.py >>"${log_file}" 2>&1 &
  else
    "${py}" -c '
import os, sys
os.setsid()
os.execv(sys.argv[1], sys.argv[1:])
' "${py}" run.py >>"${log_file}" 2>&1 &
    disown -h $! 2>/dev/null || true
  fi
  local new_pid
  new_pid=$!
  echo "${new_pid}" >"${pid_file}"
  if ! "${py}" "${identity_helper}" record \
    --pid "${new_pid}" \
    --identity-file "${identity_file}" \
    --runtime-id "${runtime_id}" \
    --role backend \
    --expected-command-token run.py >/dev/null; then
    kill -TERM "${new_pid}" 2>/dev/null || true
    rm -f "${pid_file}" "${identity_file}"
    echo "ERROR: failed to record backend process ownership" >&2
    return 1
  fi

  local health_wait_sec="${MYRM_BACKEND_HEALTH_WAIT_SEC:-180}"

  for _ in $(seq 1 "${health_wait_sec}"); do
    local listener_pid
    listener_pid="$(lsof -nP -iTCP:"${backend_port}" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
    if curl -sf "${health_url}" >/dev/null 2>&1; then
      if [[ "${listener_pid}" == "${new_pid}" ]]; then
        local stack_epoch_lib
        stack_epoch_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-epoch.sh"
        if [[ -f "${stack_epoch_lib}" ]]; then
          # shellcheck source=stack-epoch.sh
          source "${stack_epoch_lib}"
          _bump_stack_epoch "${new_pid}" "${server_dir}" >/dev/null || true
          if [[ "${runtime_id}" == "shared" ]]; then
            python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")/e2e_core" && pwd)/stack_mutation_policy.py" \
              clear-pending --state-dir "${state_dir}" >/dev/null 2>&1 || true
          fi
        fi
        return 0
      fi
      if [[ -n "${listener_pid}" ]]; then
        # 端口已被另一个健康 backend 抢先占用（并发 ensure 竞争）：不争抢，
        # 接管端口 owner 记录并回收本实例，避免孤儿进程堆积。
        echo "STACK_SYNC: :${backend_port} served by existing pid ${listener_pid} — adopting record, killing new pid ${new_pid}" >&2
        kill -TERM "${new_pid}" 2>/dev/null || true
        if "${py}" "${identity_helper}" record \
          --pid "${listener_pid}" \
          --identity-file "${identity_file}" \
          --runtime-id "${runtime_id}" \
          --role backend \
          --expected-command-token run.py >/dev/null 2>&1; then
          echo "${listener_pid}" > "${pid_file}"
        fi
        local stack_epoch_lib_adopt
        stack_epoch_lib_adopt="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stack-epoch.sh"
        if [[ -f "${stack_epoch_lib_adopt}" ]]; then
          # shellcheck source=stack-epoch.sh
          source "${stack_epoch_lib_adopt}"
          _bump_stack_epoch "${listener_pid}" "${server_dir}" >/dev/null || true
        fi
        return 0
      fi
    fi
    sleep 1
  done

  # 超时仍未获得端口：终止本实例，避免孤儿进程，清除记录。
  kill -TERM "${new_pid}" 2>/dev/null || true
  sleep 1
  if dev_pid_alive "${new_pid}"; then
    kill -KILL "${new_pid}" 2>/dev/null || true
  fi
  rm -f "${pid_file}" "${identity_file}"
  echo "ERROR: backend not ready on :${backend_port}. See ${log_file}" >&2
  return 1
}
