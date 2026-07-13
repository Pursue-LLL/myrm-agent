# scripts/dev/lib 模块架构

## 架构概述

`scripts/dev/` 专用 Bash 辅助。与根级 [scripts/lib/_ARCH.md](../../lib/_ARCH.md) 区分：根 `lib/` 供 `myrm` 主 CLI 使用；本目录供 `dev.sh` / `start.sh` source。

## 文件清单

| 文件 | 职责 |
|------|------|
| `frontend-warmup.sh` | Unix | Frontend `shell_hot` gate（curl `/`）+ `client_hot`（CDP hydration）+ warmth JSON；定义 `_lock_supervisor_alive`（frontend lock pid 存活） |
| `frontend-client-warmup.py` | Unix | CDP navigate `:3000/` until `app-layout` — client chunk compile SSOT; registers `warm_tab_pool` |
| `cdp_warm_tab_pool.py` | Unix | Persist one preflight/raw-pytest hydration target (`warmTabPool` in HEALTH_JSON); mux clients cannot adopt cross-owner targets |
| `cdp_write_guard.py` | Unix | Block direct `/json/new` while active Wave READ leases (mux-only CDP writer) |

**pytest vs MCP 纪律**：`myrm-agent-server/tests/e2e/test_execution_cache_chrome_e2e.py` 在 guard 允许时可直连 warm tab CDP WS（raw pytest 特权）；Cursor Agent / chrome-devtools MCP **必须** `new_page` 自有 tab（见 [CHROME_MCP_E2E.md](../../../../scripts/dev/CHROME_MCP_E2E.md)）。
| `runtime_identity.py` | Unix | Runtime Identity SSOT：`backendEpoch`/`frontendEpoch`/`chromeEpoch`/`muxEpoch` → `runtimeId`；`build_health_json` CLI |
| `runtime_probe.py` | Unix | Live mux/CDP probe + `run_drift_check()` for `--drift` / `runtime-drift` |
| `runtime-drift.sh` | Unix | `./myrm runtime-drift --expect <id>` 入口；exit 2 = `RUNTIME_DRIFT` |
| `stack-epoch.sh` | Unix | Backend `stack_epoch` bump/read for parallel Agent drift detection |
| `../stack_supervisor/` | Unix | Dev 栈单写者守护进程（跨进程锁 + RPC + 受 Wave 门禁的看门狗）；见 [stack_supervisor/_ARCH.md](../stack_supervisor/_ARCH.md) |
| `backend_bg.sh` | Unix | 后台启动 `myrm-agent-server`（:8080）；默认 `SQLITE_POOL_SIZE=15`；新启动前截断 `.myrm-dev-backend.log` 防无限膨胀；健康轮询后 `_bump_stack_epoch`；monorepo 下非 editable harness 时 **exit 1** |

## 依赖

- [scripts/dev/_ARCH.md](../_ARCH.md)
- [scripts/dev/dev.sh](../dev.sh) · [scripts/dev/start.sh](../start.sh) — source `backend_bg.sh` · `dev-stack.sh` — source `frontend-warmup.sh`
