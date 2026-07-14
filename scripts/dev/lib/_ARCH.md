# scripts/dev/lib 模块架构

## 架构概述

`scripts/dev/` 专用 Bash 辅助。与根级 [scripts/lib/_ARCH.md](../../lib/_ARCH.md) 区分：根 `lib/` 供 `myrm` 主 CLI 使用；本目录供 `dev.sh` / `start.sh` source。

## 文件清单

| 文件 | 职责 |
|------|------|
| `frontend-warmup.sh` | Unix | Frontend `shell_hot` gate（curl `/`）+ `client_hot`（CDP hydration）+ warmth JSON；定义 `_lock_supervisor_alive`（frontend lock pid 存活） |
| `frontend-client-warmup.py` | Unix | CDP navigate `:3000/` until `[data-testid="app-layout"]` + `[data-chat-input]`（无 MessageListSkeleton）；注册 `cdp-transient-targets.json` |
| `cdp_chat_ui.py` | Unix | WebUI chat 自动化稳定导出层；实现按 transport/bootstrap/input/submit/turn/support 拆分 |
| `chrome_mcp_client.py` / `mcp_chat_ui.py` | Unix | 正式 pytest UI E2E 的 MCP JSON-RPC client；`mcp_chat_ui` 导出 `is_detached_frame_error` / `is_recoverable_evaluate_error` / `recreate_page`（detached/upstream 错误 evaluate 重试）；每页绑定 exact targetId + Wave READ lease |
| `cdp_chat_{transport,bootstrap,input,submit,turn,support}.py` | Unix | transport-independent chat UI 工作流；MCP 与 client warmup 复用 |
| `cdp_transient_targets.py` | Unix | Preflight client warmup 短生命周期 target 归属 ledger；只按死亡 owner 的 exact targetId 回收 |
| `cdp_write_guard.py` | Unix | raw `/json/new` 永久拒绝；仅 supervisor `MYRM_CDP_WARMUP=1` 预热例外 |
| `runtime_identity.py` | Unix | Runtime Identity SSOT + attach health gate：四元 epoch → `runtimeId`；`build_health_json` CLI |
| `runtime_probe.py` | Unix | Live mux/CDP probe + `run_drift_check()` for `--drift` / `runtime-drift` |
| `runtime-drift.sh` | Unix | `./myrm runtime-drift --expect <id>` 入口；exit 2 = `RUNTIME_DRIFT` |
| `stack-epoch.sh` | Unix | Backend `stack_epoch` bump/read for parallel Agent drift detection |
| `../stack_supervisor/` | Unix | Dev 栈单写者守护进程（跨进程锁 + RPC + 受 Wave 门禁的看门狗）；见 [stack_supervisor/_ARCH.md](../stack_supervisor/_ARCH.md) |
| `dev_state_paths.sh` | Unix | Dev 栈 pid/log SSOT：`~/.local/state/myrm-dev/{backend,frontend}.{pid,log}`；`cleanup_legacy_dev_artifacts` 仅 stop 时删子目录残留 |
| `backend_bg.sh` | Unix | 后台启动 `myrm-agent-server`（:8080）；pid/log 写入 `dev_state_paths`；新启动前截断 backend.log；健康轮询后 `_bump_stack_epoch`；monorepo 下非 editable harness 时 **exit 1** |

## 依赖

- [scripts/dev/_ARCH.md](../_ARCH.md)
- [scripts/dev/dev.sh](../dev.sh) · [scripts/dev/start.sh](../start.sh) — source `backend_bg.sh` · `dev-stack.sh` — source `frontend-warmup.sh`

## Dev 栈状态路径 SSOT

| 项 | 路径 |
|----|------|
| 状态根 | `MYRM_DEV_STATE_DIR`（默认 `~/.local/state/myrm-dev`） |
| Backend pid/log | `{state}/backend.pid` · `{state}/backend.log` |
| Frontend pid/log | `{state}/frontend.pid` · `{state}/frontend.log` |

Unix 解析见 `dev_state_paths.sh`；`dev-stack.sh` / `stack_supervisor` / `backend_bg.sh` 为写入方。

## 约束

- pytest raw CDP 与 MCP chrome-devtools 纪律见 [scripts/dev/_ARCH.md](../_ARCH.md) WebUI E2E 节
