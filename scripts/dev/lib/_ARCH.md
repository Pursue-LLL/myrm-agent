# scripts/dev/lib 模块架构

## 架构概述

`scripts/dev/` 专用 Bash 辅助。与根级 [scripts/lib/_ARCH.md](../../lib/_ARCH.md) 区分：根 `lib/` 供 `myrm` 主 CLI 使用；本目录供 `dev.sh` / `start.sh` source。

## 文件清单

| 文件 | 职责 |
|------|------|
| `frontend-warmup.sh` | Unix | Frontend `shell_hot` gate（curl `/`）+ `client_hot`（CDP hydration）+ warmth JSON；定义 `_lock_supervisor_alive`（frontend lock pid 存活） |
| `frontend-client-warmup.py` | Unix | CDP `Target.createTarget(background=true)` 预热 `:3000/` 直至 `[data-testid="app-layout"]` + `[data-chat-input]`；注册 `infra-browser-targets.json` |
| `cdp_chat_ui.py` | Unix | WebUI chat 自动化稳定导出层；实现按 transport/bootstrap/input/submit/turn/support 拆分 |
| `chrome_mcp_client.py` / `chrome_mcp_errors.py` / `mcp_protocol.py` / `mcp_chat_ui.py` | Unix | 正式 pytest UI E2E 的 MCP JSON-RPC client；**R47** reclaim **120s** 硬墙 + `MUX_RECLAIM_STALL` → `recover_mux_transport`；**R48** `abandon_inflight_requests` generation token + shell probe `evaluate_task.cancel()`；**R49** abandon/recover **同步**（禁止 `to_thread(abandon)` 线程池死锁）；**R50** abandon 替换 `_request_lock` + recover 前必 abandon；**R51** `reset_after_orphan()` 单入口（generation++ · teardown · 新 Lock · recover）替换 scattered abandon+recover；**R57** `_TransportDeadError` 统一 transport 层异常（`_read` EOF · `_write` BrokenPipe/ValueError 均 raise `_TransportDeadError` 而非 `RuntimeError`）；**R58** `_request`/`_recover_mux_transport` 的 `start_generation` 检查（防止 executor 与 asyncio 线程竞态 recovery）；**R60** `_write` 中 `json.dumps` 移至 `try` 块外（避免序列化 `ValueError` 被误捕获为 transport 错误）；`_wait_shell_layout_ready` 用 `layout_wait_started` 防 hydrate 重置 stall 时钟；`mcp_chat_ui.evaluate` wall deadline；`cdp_chat_bootstrap._hydrate_chat_home_surface` SHPOIB；`call_tool` transient/timeout 有限重试；page client 须 active 父 lease；`reclaim_owned_page` |
| `cdp_chat_{transport,bootstrap,input,submit,turn,support}.py` | Unix | transport-independent chat UI 工作流；MCP 与 client warmup 复用；**R72-FINAL** `cdp_chat_submit.send_chat_message_atomic` 仅 `submitAndObserveTurn` fail-closed（无 legacy `submit()` pyramid）；`cdp_chat_turn.send_message` 强制 `sendTurnSealed`；**R50** `ensure_chat_surface` SHPOIB 缩放 + `_hydrate_chat_home_surface` + `ensure_react_e2e_bridge` fallback；**R67** `cdp_chat_bootstrap.bootstrap` 结束 `complete_bootstrap_phase()` 重置 BODY 墙钟；`cdp_chat_input._heal_empty_chat_shell_for_bridge` 走 `_shared_ui_burst`；`cdp_chat_input.ensure_react_e2e_bridge` 拒绝 DOM fallback，blank shell 时 heal 重导航；`cdp_chat_bootstrap._wait_providers_hydrated` 的 API readiness probe 走 `to_thread + wait_for` 非阻塞守门；computer_use/builtin-tools 须 React bridge |
| `dev_gate_contract.py` | Unix | Dev Gate v2 SSOT：**R47** … **R72** `SEND_TURN_*` · **R60/R61** `SignoffProfile` / `SIGNOFF_LEG_MTB_SEC` / `SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC`（540）/ `SIGNOFF_PYTEST_SAFE_BUFFER_SEC` / `clarify_skip_api_wait_sec` |
| `cdp_chat_support.py` | Unix | E2E API/chat 消息 SSOT；`get_e2e_api_url/get_e2e_ui_url` 与 `_e2e_api_urlopen` 强制 loopback HTTP allowlist（127.0.0.1/localhost/::1/0.0.0.0）并对 config/messages 短重试 · **`start_clarify_turn_via_api`**（signoff clarify API stream fallback）· **`_collect_agent_stream_events`** SSE 采集 SSOT |
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
| `backend_bg.sh` | Unix | 后台启动 `myrm-agent-server`（:8080）；pid/log 写入 `dev_state_paths`；source drift 时 **leases>0 defer reload + record-pending**（R31-G），leases=0 才 TERM reload；**R61** health-aware self-healing：identity mismatch 时回收 state files；health probe 失败 + leases=0 时 kill+restart，leases>0 时 defer kill；health probe 分支提前 source `stack-epoch.sh`（**R61-A** 修复 `_wave_active_lease_count` 未定义）+ `2>/dev/null \|\| echo 0` 防御 |
| `process_identity.py` | Unix | 记录 `pid + OS start token + runtimeId`；停止前复验进程代次，只终止精确 owner 的进程树，PID 复用时 fail-closed |
| `e2e_mux_admission.py` | Unix | 全局 mux session 准入（READ+LIVE 统一 cap、`E2E_MUX_ADMISSION_WAIT`）；`MYRM_E2E_RUN_ID` label 经 `_registry_key()` uuid5 归一化 |
| `e2e_runtime_cell.py` | Unix | **R73-F** E2E Runtime Cell：per-slot `MYRM_E2E_CELL_ID` · per-cell UI hydrate flock · `runtime_cell_snapshot()` |
| `e2e_shared_ui_hydrate.py` | Unix | SHPOIB 并行 navigate/reload burst flock（R36 窄化锁；queue ≤900s）；**R73-F** 有 cell 时走 `e2e_runtime_cell.cell_ui_hydrate_slot` |
| `e2e_shared_ui_session.py` | Unix | chrome_e2e Shared UI Session Contract（marker `e2e_search_policy` · RESET/BIND/BRIDGE/SEARCH 四阶段 · bootstrap + `click_new_chat` hook；**R55** empty 两态契约；**R67** 各步 `assert_phase_budget` + bridge `asyncio.wait_for` fail-fast） |
| `e2e_pytest_dedupe.py` | Unix | chrome_e2e 文件级 dedupe；stale wall = `LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC`（1410s dev LIVE）；`E2E_PYTEST_DEDUPE_DENIED` |
| `mux_upstream_admission.py` | Unix | 全局 mux cold attach 准入（cap=3、`MUX_UPSTREAM_WAIT`）；`read_mux_cold_attach_status()` 供 `e2e-context` 暴露 `muxColdAttachSaturated`；`chrome_mcp_client.new_page` 包装 |
| `e2e_capacity_messages.py` | Unix | Dev Gate UX：cap 等待人话行（保留 `E2E_*_WAIT` token） |
| `send_turn_contract.py` | Unix | R72 SendTurnContract：`SendTurnPhase` · `SendTurnError` · LIVE/READ profile SSOT |
| `transport_supervisor.py` | Unix | **R65-A/R73-B** mux runtime：muxDaemons=1 · global recover mutex · session 120s budget keyed by **MYRM_E2E_CELL_ID** |
| `e2e_orchestrator.py` | Unix | **R65/R73-D** E2EOrchestrator SSOT（lifecycle + orchestrator_snapshot · runtime_cell in snapshot） |
| `e2e_session_lifecycle.py` | Unix | **R62** 四相位 budget SSOT（ADMIT/BOOTSTRAP/BODY/TEARDOWN）；dev LIVE_AGENT BODY **900s** · READ/signoff **600s**；**R67** `begin_bootstrap_phase` 始终切 BOOT 180s · `complete_bootstrap_phase` 重置 BODY |
| `stack_mutation_policy.py` / `stack_mutation_policy.sh` | Unix | R30 SMP SSOT：shared-stack drift heal defer under active wave leases；`pending-stack-drift.json`；preflight/bootstrap/supervisor 统一入口；**R46** attach crash heal（3× `backend-only ensure` + backoff 5s/10s；preflight wait 每 30s 再 heal max 2）；**R46.1** attach 健康探针（`CHROME_E2E_ATTACH_HEALTH_PROBE_*`）先判 backend/pending drift，再进入 mux attach；idle apply 若命中 harness import 失败会自动执行一次 `./myrm harness install` 后重试 `backend-only ensure` |
| `e2e_api_verify.py` | Unix | Agent `./myrm verify-api` / `e2e-context` SSOT：stored/workspace fingerprint epoch 匹配路由；blocked+epoch mismatch 时 stderr **`E2E_BLOCKED_EPOCH`**；`muxColdAttachSaturated`/`muxHandProbeAllowed`；**默认 human/json 含 `parallelSnapshot` + `capHeadroom` + `E2E_PARALLEL_ACTIVE`**（禁止 pgrep 误判）；`--ensure-backend` 按需 seed 私池（exit 2 BLOCKED fail-closed） |
| `verify_backend_seed.py` | Unix | verify-api BLOCKED 时 backend-only isolated spawn（SHPOIB cap 内；cap/bootstrap 5s×1 重试；`claim_bootstrap_slot`→health→`running` phase SSOT） |
| `../resolve_e2e_session_profile.py` | Unix | UEA v3 profile SSOT（`{lane, shpoib, shared_hot}`）；`-m`/`-k` pytest collect-only（scoped `tests/e2e`）；驱动 cap、stream-first、approval skip |
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
