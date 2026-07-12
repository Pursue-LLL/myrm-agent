# wave_orchestrator 模块架构

## 架构概述

Chrome MCP UI E2E 的 **Immutable Test Wave** 状态机。冻结 `runtimeId`、发放 READ lease、在活跃租约期间阻断 `dev-stack reset`（`WAVE_STACK_WRITE_DENIED`）。

维护者基建，不属于 harness / server / control-plane。

## 文件清单

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `paths.py` | 解析 `~/.local/state/myrm-dev/wave-orchestrator.json` | ✅ |
| `types.py` | `WaveRecord` / `LeaseRecord` / `Lane` | ✅ |
| `store.py` | flock + JSON 原子读写 | ✅ |
| `lanes.py` | Typed lane 冲突矩阵 | ✅ |
| `resource_ledger.py` | 资源登记 / lease 释放清理 | ✅ |
| `resource_cleanup.py` | chat 等资源 HTTP 清理驱动 | ✅ |
| `core.py` | wave/lease 业务逻辑 + `check_stack_write_gate` | ✅ |
| `cli.py` | `./myrm wave` 子命令 | ✅ |
| `__main__.py` | `python -m wave_orchestrator` 入口 | — |

## CLI（`../wave.sh`）

| 命令 | 行为 |
|------|------|
| `open [--runtime-id]` | 冻结当前或指定 `runtimeId`，开启 wave |
| `close [--force]` | 关闭 wave；`--force` 释放活跃 lease |
| `status` | JSON 状态 |
| `lease acquire READ` | 测试租约（可多 Agent 并行 READ） |
| `lease release <id>` | 释放租约 |
| `lease heartbeat <id>` | 延长 TTL |
| `ledger register <leaseId> <kind> <ref>` | 登记测试资源（须 RESOURCE_WRITE 或 GLOBAL_WRITE lease） |
| `ledger list [--lease-id] [--namespace]` | 列出活跃账本资源 |
| `ledger cleanup --lease-id <id>` / `--namespace <ns>` | 手动清理 |
| `check-stack-write` | exit 0=允许 reset；exit 3=有活跃 lease |

## Typed Lanes（`lanes.py`）

| Lane | 用途 | 策略 |
|------|------|------|
| `READ` | UI 只读并行 | 多租约；GLOBAL_WRITE / STACK_WRITE 阻断 |
| `RESOURCE_WRITE` | namespace 资源写 | 同 namespace 独占；LIVE_AGENT / GLOBAL_WRITE / STACK_WRITE 阻断 |
| `GLOBAL_WRITE` | 全局配置写入 | 全局独占；阻断 READ / LIVE_AGENT / RESOURCE_WRITE |
| `LIVE_AGENT` | API E2E / 真实模型流 | 默认并发 1（`MYRM_LIVE_AGENT_MAX_CONCURRENT`） |
| `STACK_WRITE` | reset/restart | 全局独占 |

`./myrm test -m e2e` 使用 `wave-e2e-lease.sh acquire LIVE_AGENT`（已删除 `api-e2e.lock`）。

**Resource Ledger**：`RESOURCE_WRITE` 或 `GLOBAL_WRITE` 租约创建 chat 等业务资源后，须 `./myrm wave ledger register <leaseId> chat <chatId>`；`lease release` / TTL 过期自动 HTTP 清理（`resource_cleanup.py` → `DELETE /api/v1/chats/...`）。

全局选项 `--agent` 须放在子命令前：`./myrm wave --agent my-id lease acquire READ`。

## 集成

- `dev-stack.sh` `cmd_reset` 首行调用 `check-stack-write`（`MYRM_WAVE_GATE_BYPASS=1` 仅测试）
- `ifm/profile.yaml` browser-mcp — Agent 正式流程
- [runtime_probe.py](../lib/runtime_probe.py) — `runtimeId` 探针

## 依赖

- [../lib/runtime_probe.py](../lib/runtime_probe.py)
- [../dev-stack.sh](../dev-stack.sh)
- [../_ARCH.md](../_ARCH.md)
