# scripts/dev/lib 模块架构

## 架构概述

`scripts/dev/` 专用 Bash 辅助。与根级 [scripts/lib/_ARCH.md](../../lib/_ARCH.md) 区分：根 `lib/` 供 `myrm` 主 CLI 使用；本目录供 `dev.sh` / `start.sh` source。

## 文件清单

| 文件 | 职责 |
|------|------|
| `frontend-warmup.sh` | Unix | Frontend `shell_hot` gate（curl `/`）+ `client_hot`（CDP hydration）+ warmth JSON；定义 `_lock_supervisor_alive`（frontend lock pid 存活） |
| `frontend-client-warmup.py` | Unix | CDP `Target.createTarget(background=true)` 预热 `:3000/` 直至 `[data-testid="app-layout"]` + `[data-chat-input]`；注册 `infra-browser-targets.json` |
| `cdp_chat_ui.py` | Unix | WebUI chat 自动化稳定导出层；实现按 transport/bootstrap/input/submit/turn/support 拆分 |
| `chrome_mcp_client.py` / `chrome_mcp_errors.py` / `mcp_protocol.py` / `mcp_chat_ui.py` | Unix | 正式 pytest UI E2E 的 MCP JSON-RPC client；`mcp_protocol.parse_evaluate_result` 对 MCP 返回的 JSON 字符串二次解析；`dev_gate_contract.TRANSIENT_MUX_ERROR_TOKENS` 经 `chrome_mcp_errors` 分类；`evaluate` 用 `mux_load` 自适应 tool timeout；`call_tool` 对 transient/timeout 有限重试 + mux transport recover；公开 `recover_mux_transport()` 供 E2E orchestrator 在 page-open 重试间调用；`mcp_chat_ui.evaluate` 对 `TimeoutError` 有限退避重试，**对 `Target closed` 等 transport `RuntimeError` fail-fast（不 replay）**，ownership/context-reset/detached-frame 走单次 reclaim/navigate heal；page client 必须依附 active 父 E2E lease；`reclaim_owned_page`；`is_mux_page_heal_error` |
| `cdp_chat_{transport,bootstrap,input,submit,turn,support}.py` | Unix | transport-independent chat UI 工作流；MCP 与 client warmup 复用；`cdp_chat_input.ensure_react_e2e_bridge` 拒绝 DOM fallback，computer_use/builtin-tools 须 React bridge |
| `cdp_chat_support.py` | Unix | E2E API/chat 消息 SSOT；`get_e2e_api_url/get_e2e_ui_url` 与 `_e2e_api_urlopen` 强制 loopback HTTP allowlist（127.0.0.1/localhost/::1/0.0.0.0）并对 config/messages 短重试 |
| `infra_browser_registry.py` | Unix | client warmup 短生命周期 target 归属 ledger；`wave reap` 与 preflight prune 回收死亡 owner 的 exact targetId |
| `browser_tab_hygiene.py` | Unix | `./myrm doctor --chrome` tab 计数报告（CDP / wave / infra registry） |
| `cdp_write_guard.py` | Unix | raw `/json/new` 永久拒绝；仅 supervisor `MYRM_CDP_WARMUP=1` 预热例外；active lease 计数经 `wave_state_paths` |
| `wave_state_paths.py` | Unix | `wave-orchestrator.json` 路径 SSOT；lazy bootstrap 委托 `wave_orchestrator.paths.resolve_wave_paths().state_file` |
| `runtime_identity.py` | Unix | Runtime Identity SSOT + attach/stack-core health gate：基础设施四元 epoch → hot-pool `runtimeId`；`api_health_errors()`（keepalive API-only）；`require_stack_core` 忽略 UI curl；源码 fingerprint 独立控制 warmth/HMR，不使 active lease drift；`read_stack_scoped_runtime_id()`（backend+frontend only）；`build_health_json` CLI |
| `runtime_probe.py` | Unix | Live mux/CDP probe + `run_drift_check()` for `--drift` / `runtime-drift` |
| `runtime-drift.sh` | Unix | `./myrm runtime-drift --expect <id>` 入口；exit 2 = `RUNTIME_DRIFT` |
| `stack-epoch.sh` | Unix | Backend `stack_epoch` bump/read for parallel Agent drift detection |
| `../stack_supervisor/` | Unix | Dev 栈单写者守护进程（跨进程锁 + RPC + 受 Wave 门禁的看门狗）；见 [stack_supervisor/_ARCH.md](../stack_supervisor/_ARCH.md) |
| `dev_state_paths.sh` | Unix | Dev 栈 pid/log SSOT + `MYRM_NEXT_DIST_DIR` / `dev-server.lock` 路径（`resolve_myrm_next_dist_dir`）；`cleanup_legacy_dev_artifacts` 清理旧 pid 路径与 `scripts/dev/myrm-agent-*` 遗留目录；`prune_stale_isolated_next_dirs` 删除非当前 active 的全部 `.next-isolated-*`（含非空残留） |
| `backend_bg.sh` | Unix | 后台启动 `myrm-agent-server`（:8080）；pid/log 写入 `dev_state_paths`；新启动前截断 backend.log；健康轮询后 `_bump_stack_epoch`；monorepo 下非 editable harness 时 **exit 1** |
| `process_identity.py` | Unix | 记录 `pid + OS start token + runtimeId`；停止前复验进程代次，只终止精确 owner 的进程树，PID 复用时 fail-closed |
| `e2e_mux_admission.py` | Unix | 全局 mux session 准入（READ+LIVE 统一 cap、`E2E_MUX_ADMISSION_WAIT`）；`MYRM_E2E_RUN_ID` label 经 `_registry_key()` uuid5 归一化 |
| `mux_upstream_admission.py` | Unix | 全局 mux cold attach 准入（cap=2、`MUX_UPSTREAM_WAIT`）；`chrome_mcp_client.new_page` 包装 |
| `e2e_capacity_messages.py` | Unix | Dev Gate UX：cap 等待人话行（保留 `E2E_*_WAIT` token） |
| `dev_gate_contract.py` | Unix | Dev Gate v2 SSOT（产品路径）：mux 错误分类、并行 cap（LIVE SHPOIB **4** / shared_hot **1** / mux **6** / cold attach **2**）、**`E2E_UNIFIED_WAIT_SEC=900`**、**`CDMCP_MUX_REQUEST_TIMEOUT_MS_DEFAULT=180000`**、**lane pytest timeout**（READ=1110 / LIVE=**1710** / desktop=7200） |
| `e2e_unified_admission.py` | Unix | UEA v3 contract 常量 re-export（`E2E_UNIFIED_WAIT_SEC` · `LIVE_SHPOIB/SHARED_HOT_MAX`） |
| `../resolve_e2e_session_profile.py` | Unix | UEA v3 profile SSOT（`{lane, shpoib, shared_hot}`）；`test.sh` 驱动 cap 与 stream-first |
| `e2e_lease_runtime_sync.py` | Unix | formal chrome E2E acquire 后 fail-closed gate：`lease.runtimeId == _read_shared_hot_stack_runtime_id()`；state 经 `wave_state_paths.resolve_wave_state_file()`；`test.sh` 经 `_e2e_sync_lease_runtime` 调用 |
| `mux_load.py` | Unix | mux context / wave lease 负载探针；adaptive page/tool timeout |
| `mux_responsive_probe.py` | Unix | mux daemon stamp 对齐 + `tools/list` 探活；`--probe-timeout-sec` 随 active Wave leases 缩放（preflight attach heal） |

## 依赖

- [scripts/dev/_ARCH.md](../_ARCH.md)
- [scripts/dev/dev.sh](../dev.sh) · [scripts/dev/start.sh](../start.sh) — source `backend_bg.sh` · `dev-stack.sh` — source `frontend-warmup.sh`

## Dev 栈状态路径 SSOT

| 项 | 路径 |
|----|------|
| 状态根 | `MYRM_DEV_STATE_DIR`（默认 `~/.local/state/myrm-dev`） |
| Backend pid/log | `{state}/backend.pid` · `{state}/backend.log` |
| Backend process identity | `{state}/backend-process.json`（原子写；禁止只凭 pid/端口执行 kill） |
| Frontend pid/log | `{state}/frontend.pid` · `{state}/frontend.log` |
| Isolated Next dist | `{frontend}/.next-isolated-{runtimeId}/dev-server.lock`（`MYRM_NEXT_DIST_DIR`） |

Unix 解析见 `dev_state_paths.sh`；`dev-stack.sh` / `stack_supervisor` / `backend_bg.sh` 为写入方。

## 约束

- pytest raw CDP 与 MCP chrome-devtools 纪律见 [scripts/dev/_ARCH.md](../_ARCH.md) WebUI E2E 节
