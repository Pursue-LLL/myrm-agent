# wave_orchestrator 模块架构

## 架构概述

Chrome MCP UI E2E 的 **Immutable Test Wave** 状态机。冻结 `runtimeId`、发放 READ lease；**open wave 钉死栈**（`stack-pin.json`）；活跃 lease 或 stack pin 时阻断 `dev-stack reset` 与 frontend kill（`WAVE_STACK_PINNED` / `WAVE_STACK_WRITE_DENIED`）；**ensure 冷启动恢复不受 pin 阻挡**。

维护者基建，不属于 harness / server / control-plane。

## 文件清单

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `paths.py` | 解析 state dir（`MYRM_WAVE_STATE_DIR` 优先）+ `resolve_dev_state_dir()` SSOT；`state_file` 为 `wave-orchestrator.json` 路径 | ✅ |
| `types.py` | `WaveRecord` / `LeaseRecord` / `Lane` | ✅ |
| `store.py` | flock + JSON 原子读写 | ✅ |
| `lanes.py` | Typed lane 冲突矩阵 | ✅ |
| `lease_state.py` | 无 I/O 的租约 TTL、owner、runtime drift 与活跃状态规则；`reap_abandoned_leases` 在 owner 已死时 expire ghost lease；所有 `waveId` 访问均使用 `.get("waveId")` 防御性访问（防 zombie lease 缺失字段 KeyError） | ✅ |
| `lease_cleanup.py` | browser lease 绑定/解绑；锁外 exact page/context 与资源清理 | ✅ |
| `browser_lifecycle.py` | Chrome page lifecycle（lease page bind/unbind 元数据 + release/reap 时 best-effort exact-target close）；被 `lease_state.py` / `lease_cleanup.py` 引用 | ✅ |
| `resource_ledger.py` | 资源登记 / lease 释放清理 | ✅ |
| `resource_cleanup.py` | chat 等资源 HTTP 清理驱动；503/500 指数退避重试 | ✅ |
| `stack_pin.py` | `wave open` 写入 `stack-pin.json`；`probe_stack_pids` 读 `{state}/backend.pid` + `{state}/frontend.pid`；gate 阻断无 STACK_WRITE 的栈变更 | ✅ |
| `core.py` | Wave/lease 编排 façade + `check_stack_write_gate`（含 stack pin）；`waveId` 比较均使用 `.get()` 防御性访问 | ✅ |
| `cli.py` | `./myrm wave` 子命令 | ✅ |
| `__main__.py` | `python -m wave_orchestrator` 入口 | — |

## CLI（`../wave.sh`）

| 命令 | 行为 |
|------|------|
| `open [--runtime-id]` | 冻结当前或指定 `runtimeId`，开启 wave |
| `close [--force]` | 关闭 wave；`--force` 释放活跃 lease |
| `status` | JSON 状态 |
| `lease acquire READ [--parent-lease-id <id>]` | 测试租约（可多 Agent 并行 READ）；正式 E2E 页面显式绑定父 Session lease |
| `lease release <id> [--close-wave-if-idle]` | 释放租约；父 Session 退出时原子级联自己的子 lease，并在最后一个 lease 退出时关闭 Wave |
| `lease heartbeat <id>` | 延长 TTL |
| `ledger register <leaseId> <kind> <ref>` | 登记测试资源（须 RESOURCE_WRITE 或 GLOBAL_WRITE lease；含 Kanban board/task） |
| `ledger list [--lease-id] [--namespace]` | 列出活跃账本资源 |
| `ledger cleanup --lease-id <id>` / `--namespace <ns>` | 手动清理 |
| `check-stack-write` | exit 0=允许 reset；exit 3=活跃 lease 或 **open wave stack pin**（ensure 幂等/冷启动不在此 gate） |

## Typed Lanes（`lanes.py`）

| Lane | 用途 | 策略 |
|------|------|------|
| `READ` | UI 只读并行 | 多租约；GLOBAL_WRITE / STACK_WRITE 阻断 |
| `RESOURCE_WRITE` | namespace 资源写 | 同 namespace 独占；可与私池 LIVE_AGENT 并行；GLOBAL_WRITE / STACK_WRITE 阻断 |
| `GLOBAL_WRITE` | 全局配置写入 | 共享栈全局独占；阻断 READ / LIVE_AGENT / RESOURCE_WRITE；PRIVATE 后端使用 `e2e:private:<run>` namespace，仅保留本 lease 生命周期/ledger 约束，不阻断共享栈或其他私池 |
| `LIVE_AGENT` | API E2E / 真实模型流 | `./myrm test` 默认双路真实并行；环境变量可显式调到 4 |
| `STACK_WRITE` | reset/restart | 全局独占 |

`./myrm test` 先向 Dev Gate coordinator 注册显式 execution/access/workload，再使用 `wave-e2e-lease.sh acquire`。页面 READ lease 通过 `parentLeaseId` 归属当前 Session；trap 只级联本 Session 子 lease/page。Wave 负责资源写冲突与 stack pin，不负责浏览器 session admission。共享逻辑 session 不限量；mux 固定 4 个物理 worker。PRIVATE 的昂贵后端由 coordinator 按机器容量限制为 1–4 credits，容量满自动排队。

PRIVATE session 的 root wave lease（以及其 page/context 子 lease）带有 `e2e:private:<run>` namespace。它们仍参与 ownership、heartbeat、ledger 和最终 cleanup，但不会阻断共享后端的 epoch/heal/stack-write 决策；只有共享 lease 才能 pin 共享栈。

**Resource Ledger**：`RESOURCE_WRITE` 或 `GLOBAL_WRITE` 租约创建 chat 等业务资源后，须 `./myrm wave ledger register <leaseId> chat <chatId>`；`lease release` / TTL 过期自动 HTTP 清理（`resource_cleanup.py` → `DELETE /api/v1/chats/...`）。

状态文件锁只保护快照和结果提交；CDP/HTTP 清理在锁外执行，失败记录为 `failed` 并由后续 reaper 重试。`bind_browser_lease` 在 bind 新 target 前锁外 HTTP close 旧 targetId。`wave reap` 调用 `infra_browser_registry.prune_infra_registry()`。清理认证必须显式设置 `MYRM_E2E_ADMIN_PASSWORD` 或 `E2E_ADMIN_PASSWORD`，源码不含默认密码。需要浏览器状态隔离时为每个活跃 lease 绑定唯一 `contextId`；不同 tab 本身仍共享 Cookie/localStorage。

全局选项 `--agent` 须放在子命令前：`./myrm wave --agent my-id lease acquire READ`。

## 集成

- `dev-stack.sh` `cmd_reset` / `_kill_frontend_supervisor` / `_repair_orphan_frontend` 调用 `check-stack-write`（`MYRM_WAVE_GATE_BYPASS=1` 仅测试）
- `stack_supervisor/daemon.py` — watchdog 每 30s 直接 Python 调用 `wave_orchestrator.core.reap()` + `check_stack_write_gate()`（无 bash 子进程，避免 venv 路径/超时引起的静默失败）
- `ifm/profile.yaml` browser-mcp — Agent 正式流程
- [../lib/e2e_core/runtime_probe.py](../lib/e2e_core/runtime_probe.py) — `runtimeId` 探针；`core.probe_runtime_id()` 与 `e2e_bootstrap` / `e2e_runtime_guard` 同源；正式 `./myrm test` chrome E2E 会话期间 `reap_runtime_drift` 仅 heal 或 no-op，**永不** drift-invalidate 共享 immutable wave

## Lease TTL 策略

默认 `DEFAULT_LEASE_TTL_SEC = 900`（15min），heartbeat 延长同 900s。正常测试以 ~5min 间隔 heartbeat 保活；崩溃测试最迟 15min 过期（PID-based reaper 通常在 30s 内清理）。

## 依赖

- [../lib/e2e_core/runtime_probe.py](../lib/e2e_core/runtime_probe.py)
- [../lib/e2e_core/wave_state_paths.py](../lib/e2e_core/wave_state_paths.py)
- [../dev-stack.sh](../dev-stack.sh)
- [../_ARCH.md](../_ARCH.md)
