# wave_orchestrator 模块架构

## 架构概述

Chrome MCP UI E2E 的 **Immutable Test Wave** 状态机。冻结 `runtimeId`、发放 READ lease；**open wave 钉死栈**（`stack-pin.json`）；活跃 lease 或 stack pin 时阻断 `dev-stack reset` 与 frontend kill（`WAVE_STACK_PINNED` / `WAVE_STACK_WRITE_DENIED`）；**ensure 冷启动恢复不受 pin 阻挡**。

维护者基建，不属于 harness / server / control-plane。

## 文件清单

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `paths.py` | 解析 `~/.local/state/myrm-dev/wave-orchestrator.json` | ✅ |
| `types.py` | `WaveRecord` / `LeaseRecord` / `Lane` | ✅ |
| `store.py` | flock + JSON 原子读写 | ✅ |
| `lanes.py` | Typed lane 冲突矩阵 | ✅ |
| `lease_state.py` | 无 I/O 的租约 TTL、owner、runtime drift 与活跃状态规则 | ✅ |
| `lease_cleanup.py` | browser lease 绑定/解绑；锁外 exact page/context 与资源清理 | ✅ |
| `resource_ledger.py` | 资源登记 / lease 释放清理 | ✅ |
| `resource_cleanup.py` | chat 等资源 HTTP 清理驱动；503/500 指数退避重试 | ✅ |
| `stack_pin.py` | `wave open` 写入 `stack-pin.json`；`probe_stack_pids` 读 `{state}/backend.pid` + `{state}/frontend.pid`；gate 阻断无 STACK_WRITE 的栈变更 | ✅ |
| `core.py` | Wave/lease 编排 façade + `check_stack_write_gate`（含 stack pin） | ✅ |
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
| `GLOBAL_WRITE` | 全局配置写入 | 全局独占；阻断 READ / LIVE_AGENT / RESOURCE_WRITE |
| `LIVE_AGENT` | API E2E / 真实模型流 | `./myrm test` 默认双路真实并行；环境变量可显式调到 4 |
| `STACK_WRITE` | reset/restart | 全局独占 |

`./myrm test -m chrome_e2e` 使用 `wave-e2e-lease.sh acquire`（lane 由 monorepo `scripts/dev/resolve_e2e_session_lane.py` 解析为 READ 或 LIVE_AGENT）；页面 READ lease 通过 `parentLeaseId` 显式归属 LIVE_AGENT Session。trap 释放父 lease 时只级联本 Session 子 lease/page，不会遗留零 lease 的 stack pin，也不会关闭或清理仍有并行 lease 的 Wave。正式入口默认 `MYRM_LIVE_AGENT_MAX_CONCURRENT=2`，资源充足时可显式升到 4；昂贵 private Backend bootstrap 独立限制为同时最多 2 路。底层 lane 未经正式入口调用时保持 fail-safe 单路默认。

**Resource Ledger**：`RESOURCE_WRITE` 或 `GLOBAL_WRITE` 租约创建 chat 等业务资源后，须 `./myrm wave ledger register <leaseId> chat <chatId>`；`lease release` / TTL 过期自动 HTTP 清理（`resource_cleanup.py` → `DELETE /api/v1/chats/...`）。

状态文件锁只保护快照和结果提交；CDP/HTTP 清理在锁外执行，失败记录为 `failed` 并由后续 reaper 重试。`bind_browser_lease` 在 bind 新 target 前锁外 HTTP close 旧 targetId。`wave reap` 调用 `infra_browser_registry.prune_infra_registry()`。清理认证必须显式设置 `MYRM_E2E_ADMIN_PASSWORD` 或 `E2E_ADMIN_PASSWORD`，源码不含默认密码。需要浏览器状态隔离时为每个活跃 lease 绑定唯一 `contextId`；不同 tab 本身仍共享 Cookie/localStorage。

全局选项 `--agent` 须放在子命令前：`./myrm wave --agent my-id lease acquire READ`。

## 集成

- `dev-stack.sh` `cmd_reset` / `_kill_frontend_supervisor` / `_repair_orphan_frontend` 调用 `check-stack-write`（`MYRM_WAVE_GATE_BYPASS=1` 仅测试）
- `ifm/profile.yaml` browser-mcp — Agent 正式流程
- [runtime_probe.py](../lib/runtime_probe.py) — `runtimeId` 探针；`reap()` 在 signoff matrix guard 活跃时原地 heal runtimeId，否则 drift invalidate

## 依赖

- [../lib/runtime_probe.py](../lib/runtime_probe.py)
- [../dev-stack.sh](../dev-stack.sh)
- [../_ARCH.md](../_ARCH.md)
