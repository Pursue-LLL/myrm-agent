#!/usr/bin/env bash
# Cold-start wait of the backend that `_start_backend_bg` just spawned: success needs the new pid to own the
# listen port and answer health; a healthy listener that won the port first is adopted when it is this stack's.
# [POS] backend_bg.sh 的冷启动健康等待；被其 source，无其他调用方。

# Args: new_pid backend_port health_url log_file pid_file identity_file server_dir runtime_id state_dir python identity_helper
# Returns 0 ready or adopted | 1 failed (record and process cleaned up).
_wait_backend_ready() {
  local new_pid="$1" backend_port="$2" health_url="$3" log_file="$4" pid_file="$5" identity_file="$6"
  local server_dir="$7" runtime_id="$8" state_dir="$9" py="${10}" identity_helper="${11}"

  local health_wait_sec="${MYRM_BACKEND_HEALTH_WAIT_SEC:-180}"

  for _ in $(seq 1 "${health_wait_sec}"); do
    local listener_pid
    listener_pid="$(lsof -nP -iTCP:"${backend_port}" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
    if curl -sf "${health_url}" >/dev/null 2>&1; then
      if [[ "${listener_pid}" == "${new_pid}" ]]; then
        _stack_stage backend_listening
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
        _stack_stage epoch_bumped
        return 0
      fi
      if [[ -n "${listener_pid}" ]]; then
        # 端口已被另一个健康 backend 抢先占用：只有它是本栈的（并发 ensure 竞争）才接管
        # 记录并回收本实例；非己方进程（例如桌面 sidecar）既不接管、不盖 epoch，也不动它。
        kill -TERM "${new_pid}" 2>/dev/null || true
        if ! _adopt_port_owner "${py}" "${identity_helper}" "${identity_file}" "${runtime_id}" \
          "${listener_pid}" "${backend_port}"; then
          rm -f "${pid_file}" "${identity_file}"
          return 1
        fi
        echo "STACK_SYNC: :${backend_port} served by existing pid ${listener_pid} — adopted record, killed new pid ${new_pid}" >&2
        echo "${listener_pid}" > "${pid_file}"
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
