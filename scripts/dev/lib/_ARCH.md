# scripts/dev/lib 模块架构

## 架构概述

`scripts/dev/` 专用 Bash 辅助。与根级 [scripts/lib/_ARCH.md](../../lib/_ARCH.md) 区分：根 `lib/` 供 `myrm` 主 CLI 使用；本目录供 `dev.sh` / `start.sh` source。

**Chrome E2E 域**（§19.10）已收编至 [chrome_e2e/_ARCH.md](chrome_e2e/_ARCH.md)：`gates/` · `mux/` · orchestrator 门面。

**Dev Gate 域**已收编至 [dev_gate/_ARCH.md](dev_gate/_ARCH.md)，canonical 实现在 `dev_gate/`。

**Dev Gate 基建 pytest** 唯一根在 monorepo [`open-perplexity/scripts/dev/tests/`](../../../../scripts/dev/tests/)（`conftest.py` 注入本目录至 `sys.path`）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `frontend-warmup.sh` | Unix | Frontend `shell_hot` gate（curl `/`）+ `client_hot`（CDP hydration）+ warmth JSON；定义 `_lock_supervisor_alive`（frontend lock pid 存活） |
| `frontend-warmup-heal-entry.sh` | Unix | timed shared UI heal 的子进程入口（R158 — bash -c 无法看到 sourced functions） |
| `dev_gate/` | Unix | **Dev Gate 域（15 模块）**：`contract.py`（超时/错误分类/物理浏览器池 SSOT；**S2** `LIVE_SHPOIB_MAX_CONCURRENT=4` 为 cap 根，派生 bootstrap/mux/private credits；共享逻辑 session 不设 cap，BODY=600s）· `session.py`（`ExecutionMode`/`AccessScope`/`Workload`、状态机、所有权和 cleanup receipt）· `store.py`（SQLite WAL/CAS registry + event journal + dead-owner reaper）· `coordinator.py`/`cli.py`（Unix socket 协调器与自动启动客户端；受限环境回退同一 SQLite 事务路径）· `async_queue.py` · `cleanup_observed_seal.py`（**P0-A** observed cleanup seal）· `desktop_seat_controller.py` · `event_hub.py`/`event_wait.py` · `owner_identity.py` · `private_resource_controller.py`（PRIVATE machine-aware 1–4 credits、aging + work-conserving queue、900s admission）· `signoff_export.py` · `solo_launch_gate.py` · `status.py`（registry-first shared/private/credits/session 状态快照）。文档 [dev_gate/_ARCH.md](dev_gate/_ARCH.md) |
| `cdp_chat/` | Unix | **WebUI chat 自动化域（12 模块）**：`bootstrap`/`input`/`resume`/`submit`/`support`/`transport`/`turn`/`ui`/`mcp_ui`/`live_turn_wait`/`resume_turn_contract`/`send_turn_contract`；**R72-FINAL** `submit.send_chat_message_atomic` 仅 `submitAndObserveTurn` fail-closed；`turn.send_message` 强制 `sendTurnSealed`；**§26.22** `wait_turn_done` 统一观测链（bridge→goal API→DOM）、`chat_id_hint` 初值、`okViaGoal` 经 `is_persisted_e2e_goal` 校验、节流 `E2E_OBSERVE`；**R50** SHPOIB 缩放 + bridge fallback；computer_use/builtin-tools 须 React bridge；`support.py` **`fetch_e2e_goal_status`/`wait_e2e_goal_status`/`is_persisted_e2e_goal`/`GOAL_PERSISTED_STATUSES`**（Goal 持久化 SSOT）、`get_e2e_api_url/get_e2e_ui_url` loopback allowlist、**`wait_e2e_provider_ready`**、**`E2E_API_BINDING_PROBE_JS`/`require_e2e_api_binding_probe`**、**`chat_user_message_count`** kickoff 硬锚、**`start_clarify_turn_via_api`**、**`_collect_agent_stream_events`** SSE 采集；`send_turn_contract.py` R72 SendTurnContract（`SendTurnPhase`/`SendTurnError`/LIVE/READ profile SSOT）。文档 [cdp_chat/_ARCH.md](cdp_chat/_ARCH.md) |
| `mux/` | Unix | **mux transport 域（7 模块）**：`load.py`（mux context/wave lease 负载探针；`active_mux_context_count`·`heal_mux_for_solo_gate`·`parallel_open_page_peer_count`·`reap_idle_empty_mux_contexts`）· `transport_recovery_core.py`（**R79 TRSM SSOT**：`solo_full`/`parallel_page_reclaim`/`parallel_local_respawn`）· `transport_supervisor.py`（**R65-A/R73-B** muxDaemons=1 · global recover mutex · session 120s budget keyed by **MYRM_E2E_CELL_ID**）· `upstream_admission.py`（物理 mux cold-attach 操作背压 cap=4、`MUX_UPSTREAM_WAIT`；不是 session admission）· `responsive_probe.py`（mux daemon stamp 对齐 + `tools/list` 探活；`--probe-timeout-sec` 随 active Wave leases 缩放）· `transport_adapter.py` · `attach_force_restart.py` |
| `chrome_mcp/` | Unix | **正式 pytest UI E2E 的 MCP JSON-RPC client 域（7 模块）**：`client.py`（`MYRM_BROWSER_ORCHESTRATOR=1` 时条件分发到 daemon client；每 session 稳定 isolated context；page/lease 精确所有权同步到协调器；有界 transport 恢复与 exact-target 清理）· `errors.py` · `protocol.py` · `snapshot.py` · `ui_driver.py`（Semantic real-UI actions）· `page_helpers.py` · `page_lease_heartbeat.py` |
| `browser_orchestrator/` | Unix | **Browser Orchestrator daemon 域（6 模块）**：`client.py`（Unix socket JSON-RPC 客户端；session/page lifecycle 路由到 daemon）· `core.py` · `e2e.py`（Orchestrator 路径 E2E page lifecycle；parallel `open_page` 遇 stale/`No context for session` 时 destroy→create 重试）· `page_open.py` · `page_create_transaction.py` · `frontend_client_warmup.py` |
| `e2e_core/` | Unix | **E2E 基建域（57 模块，`e2e_*` 前缀剥离）**：`orchestrator.py`（**R65/R73-D** E2EOrchestrator SSOT + orchestrator_snapshot）· `warm_shell_registry.py`（**§19.11 TAB-6** epoch shell seal/fresh · SHARED+READ hot bootstrap）· `browser_pool.py`（单一专用 Chrome(:9333) + 默认 4 个 mux 物理 worker SSOT）· `stall_guard.py`（**R96-B6** Semantic Stall SSOT）· `live_chrome_pytest_scan.py`（live chrome_e2e pytest 扫描 SSOT）· `stale_lease_reap.py`（hung pytest SIGINT + wave reap + epoch drift 兜底 reap）· `cleanup_observed_seal.py`（observed cleanup seal）· `effect_guard.py` · `cdp_write_guard.py`（raw `/json/new` 永久拒绝；仅 supervisor `MYRM_CDP_WARMUP=1` 例外）· `guardrail_ssot.py` · `stack_mutation_policy.py`（**R30 SMP SSOT**：shared-stack drift heal defer；**R46** attach crash heal；**R46.1** attach 健康探针）· `launch_gate.py`（**R166-B UPAP** fail-closed when `NEXT_ACTION=FAIL_FAST`）· `api_verify.py`（fingerprint epoch 匹配路由；**`E2E_BLOCKED_EPOCH`**；`OPERATION_BACKPRESSURE`；`launch-check` 子命令）· `parallel_status.py`（`capHeadroom`/`queueLayer` SSOT）· `runtime_identity.py`（基础设施四元 epoch → hot-pool `runtimeId`；`read_stack_scoped_runtime_id()`）· `runtime_probe.py`（Live mux/CDP probe + `run_drift_check()`）· `shared_ui_session.py`（**R55/R67/R158** Shared UI Session Contract）· `shared_ui_hydrate.py`（**R36/R73-F** SHPOIB 并行 navigate/reload burst flock）· `shpoib_warm_pool.py`（**R159** warm backend pool borrow/maintain）· `resource_ledger.py`（**R98** runtime resource ledger SSOT）· `lease_liveness.py`（**R74-OBS-3/4/R167** `effective_*` root lease counts）· `pytest_dedupe.py` · `capacity_messages.py` · `process_identity.py`（`pid + OS start token`，PID 复用 fail-closed）· `infra_browser_registry.py` · `browser_tab_hygiene.py` · `wave_state_paths.py` · `peer_count_ssot.py` · `idle_tab_hygiene.py`/`idle_hygiene_scheduler.py` · `route_manifest.py` · `readiness.py` · `pytest_zero_selected.py` · `env_test_shell_lint.py` · `llm_receipt.py` · `real_user_home.py` · `auth_cdp.py`/`auth_keychain.py`/`auth_provisioner.py` · `verify_backend_seed.py` · `epoch_delivery_plane.py` · `gate_epoch_preflight.py` · `signoff_stack_preflight.py`/`signoff_stack_heal.py` · `stack_heal_coordinator.py` · `host_resource_governor.py`/`host_governor_benchmark.py` · `mux_transport_queue.py` · `cluster_launch_policy.py` · `bootstrap_deadline.py` · `admit_poll.py` · `warm_ui_heal.py` · `wave_ledger.py` · `surface_contract.py` · `runtime_cell.py`（**R73-F** per-slot `MYRM_E2E_CELL_ID`）· `lease_pytest_gate.py` · `lease_runtime_sync.py` · `cursor_mcp_isolation.py` · `browser_topology_contract.py`（Agent :9410 vs E2E :9333 跨文件静态契约；`test_browser_mcp_ssot_static` 门禁） |
| `chrome_e2e/` | Unix | **§19.10 Chrome E2E 域**：`gates/`（entry · lease · orphan · diagnostic policy）· `mux/diagnostic_recovery.py`。文档 [chrome_e2e/_ARCH.md](chrome_e2e/_ARCH.md) |
| `e2e_session_runtime/` | Unix | per-pid session snapshot（**R96-B6** `nodeStartedMonotonic`）· 统一 `heartbeat_once` SSOT（coordinator + wave lease + runtime）· E2E session registry（ADMIT through BODY，R144 SSOT）· 四相位 budget SSOT（ADMIT/BOOTSTRAP/BODY/TEARDOWN；dev LIVE_AGENT BODY **600s**） |
| `e2e_live_flows/` | Unix | live flow runners：`_flow_base` · `browser_takeover_live_{api,flow,gate,mux,runner}` |
| `../stack_supervisor/` | Unix | Dev 栈单写者守护进程（跨进程锁 + RPC + 受 Wave 门禁的看门狗）；见 [stack_supervisor/_ARCH.md](../stack_supervisor/_ARCH.md) |
| `dev_state_paths.sh` | Unix | Dev 栈 pid/log SSOT + `MYRM_NEXT_DIST_DIR` / `dev-server.lock` 路径；`cleanup_legacy_dev_artifacts` 清理旧 pid 路径与 `scripts/dev/myrm-agent-*` 遗留目录；`prune_stale_isolated_next_dirs` 删除非当前 active 的全部 `.next-isolated-*`（含非空残留） |
| `stack_mutation_policy.sh` | Unix | Stack mutation policy shell helpers（**R30** SMP SSOT：shared-stack drift heal defer under active wave leases **or dev-stack ensure.lock.d**；`pending-stack-drift.json`） |
| `wave-lease-owner.sh` | Unix | stable lease ownership 共享辅助（E2E helper 脚本共用） |
| `dev_paths.py` | Unix | 产品 dev-gate 模块共享路径 bootstrap |
| `backend_bg.sh` | Unix | 后台启动 `myrm-agent-server`（:8080）；pid/log 写入 `dev_state_paths`；source drift 时 **leases>0 defer reload + record-pending**（R31-G），leases=0 才 TERM reload；**R61** health-aware self-healing：identity mismatch 时回收 state files；health probe 失败 + leases=0 时 kill+restart，leases>0 时 defer kill；health probe 分支提前 source `stack-epoch.sh`（**R61-A** 修复 `_wave_active_lease_count` 未定义）+ `2>/dev/null \|\| echo 0` 防御 |
| `stack-epoch.sh` | Unix | Backend `stack_epoch` bump/read for parallel Agent drift detection |
| `../runtime-drift.sh` | Unix | `./myrm runtime-drift --expect <id>` 入口；exit 2 = `RUNTIME_DRIFT` |

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
