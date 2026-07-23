# tests 模块架构

pytest 测试套件根目录。单元/集成/API/E2E 测试按域分子目录；[T] 业务密钥仅通过结构化 fixture 加载，不进入 server 运行时。

---

## 文件清单

| 路径 | 地位 | 职责 |
|------|------|------|
| `conftest.py` | 核心 | 进程级 `.env` + [T] secrets bootstrap、隔离 workspace、`test_secrets` session fixture、integration/e2e 路径每测后 `reset_global_browser_pool_for_tests()`、session 结束 + `@chrome_e2e` timeout 时 `reset_database_engine()` + `reap_chrome_e2e_session_hygiene()` + `shutdown_cached_memory_managers()`、浏览器进程树 cleanup（`tests/support/browser_process_cleanup`） |
| `support/browser_process_cleanup.py` | 辅助 | pytest 进程树内 browser 自动化子进程 teardown |
| `support/test_browser_process_cleanup.py` | 单元 | browser_process_cleanup 单测（100% 覆盖） |
| `support/test_secrets.py` | 核心 | [T] `.env.test` 结构化加载（`TestSecrets`、`load_test_secrets`、`resolve_test_env`） |
| `support/minimal_app.py` | 核心 | `build_minimal_app(preset=...)` 按需挂载 API 路由；禁止测试 import `app.main` |
| `support/feature_flags.py` | 辅助 | `seed_voice_interaction_flags()`，供 `tests/api/voice`、`tests/api/stt` conftest autouse |
| `support/bash_compressor_e2e.py` | 辅助 | bash compressor live/API E2E 共享 helper（模型 probe、workspace 压缩回放） |
| `support/chrome_mcp_e2e.py` | 核心 | Chrome MCP E2E helper（`open_mcp_page`、`dismiss_blocking_modals`、`prepare_e2e_ui_session` onboarding 收口；`open_mcp_page` 默认 `timeout_ms=None` → mux adaptive） |
| `support/chrome_memory_settings_e2e.py` | 辅助 | `/settings/memory` Chrome 开关 JS SSOT（memory citations + voice ACL E2E 共用） |
| `api/agent/utils.py` | 辅助 | Agent 测试共享工具（模型/搜索配置组装） |
| `e2e/conftest.py` | 辅助 | E2E ephemeral server fixture（API 级 e2e，不启动前端） |
| `e2e/test_kanban_chrome_e2e.py` | 模块 | Kanban Chrome MCP E2E（READ×4：看板渲染 + source_chat 深链过滤 + Drawer 附件 + Chat 成功卡片→看板） |
| `e2e/test_wiki_citation_chrome_e2e.py` | 模块 | Wiki citation Chrome MCP E2E（READ×2：citation reload + `/settings/wiki?agentId=`） |
| `e2e/test_integration_catalog_loopback_guard_chrome_e2e.py` | 模块 | Integration Catalog loopback guard Chrome MCP E2E（READ×2：live API `deployment_scope` 与 `/integrations/mcp/probe` 语义断言 + 阻断链 `scan/verify` 不扇出 + `recommendedMode` 重试后自动续接连接） |
| `e2e/test_memory_citations_chrome_e2e.py` | 模块 | Memory Chrome MCP E2E（READ×2：设置「历史会话搜索」开关；统一「依据/Evidence N」Sheet） |
| `e2e/test_voice_memory_acl_chrome_e2e.py` | 模块 | Voice memory ACL Chrome MCP E2E（READ×2：`/settings/memory` UI 开/关「历史会话搜索」→ `GET /config/personalSettings` 断言；token corpus 由 HTTP 集成测覆盖） |
| `api/voice/test_voice_memory_context.py` | 模块 | Voice memory ACL SSOT 单元 + policy 矩阵 |
| `api/voice/test_voice_memory_acl_api_integration.py` | 模块 | Voice memory ACL HTTP 集成（realtime/gemini token enum + tool-exec flags，ACL 路径 unmocked） |
| `e2e/test_background_tasks_panel_chrome_e2e.py` | 模块 | Background Tasks Panel Chrome MCP E2E（READ×3：打开 Panel、「耗时任务」分区、seed failed/running + UI cancel via `data-testid=background-task-cancel`（wait 合并 testid+分区，防 running 文本假阳性）+ tab-alive API poll） |
| `e2e/test_background_shell_live_agent_chrome_e2e.py` | 模块 | Background shell LIVE×1：`test_live_agent_background_shell_spawn_via_agent_stream` — agent-stream 须调 `bash_code_execute_tool`（5× stream retry + REST 20s probe + 3× chat retry 含 URLError/transport）→ REST running；`finally` teardown cancel |
| `e2e/test_skill_marketplace_live_agent_chrome_e2e.py` | 模块 | Skill marketplace LIVE×1：`test_live_agent_skill_marketplace_search_in_real_ui` — 自定义 Agent（`/?agentId=`）+ 自然语言用户消息 → 真实 WebUI 须呈现外部市场搜索结果；禁止注入式 `E2E_* MUST call` prompt（mimo 安全拒绝）；3× chat retry |
| `api/agent/test_memory_conversation_search_e2e.py` | 模块 | Memory + sessions opt-in API 集成（真实 LLM agent-stream；8 场景：opt-in/incognito/memory-off/多轮/passphrase） |
| `ai_agents/test_custom_agent_factory.py` | 模块 | Custom/Ephemeral 子 Agent `memory_search_tool` rebind + factory build 路径（38 项；`--cov-fail-under=90` on factory） |
| `ai_agents/test_conversation_search_opt_in_integration.py` | 模块 | conversation-search opt-in 与 tool_setup 绑定集成 |
| `e2e/test_subagent_dashboard_chrome_e2e.py` | 模块 | Subagent Dashboard Chrome MCP E2E（LIVE×3：cancel running、delegation pause toggle、SSE token/model 展示） |
| `services/agent/test_subagent_rebind_event.py` | 模块 | `SUBAGENT_REBIND_REQUIRED` 事件：`subagent_ids` 变更时 publish、同值/非绑定字段不 emit |
| `api/chats/test_citation_seed_fixture.py` | 模块 | citation fixture seed HTTP 单测（local-only，`/chats/test/seed-citation-fixture`） |
| `api/chats/test_kanban_closure_seed_fixture.py` | 模块 | Kanban closure fixture seed HTTP 单测（`/chats/test/seed-kanban-closure-fixture`） |
| `api/chats/test_kanban_closure_seed_integration.py` | 模块 | Kanban closure seed 真 DB 集成（metadata + board task） |
| `api/chats/test_citation_seed_integration.py` | 模块 | citation seed → GET messages 集成单测（真 DB metadata） |
| `api/files/test_revert_seed_integration.py` | 模块 | Revert seed 四 variant + production persist root hydrate + channel cleanup（6 项；无 RevertService mock） |
| `services/files/test_revert_hydrate.py` | 单元 | `revert_hydrate.py` 100% 覆盖：root 解析顺序、hydrate、cleanup |
| `e2e/test_revert_files_chrome_e2e.py` | 模块 | RevertFiles Chrome MCP E2E（READ×5：modify undo+diff+confirm；empty toast；large_skip non-revertible toast；reload hydrate undo；session SessionRevertButton）；`prepare_e2e_ui_session` + `dismiss_blocking_modals` + async Sonner wait |
| `e2e/test_allowlist_pattern_live_chrome_e2e.py` | 模块 | Allowlist pattern Chrome LIVE×1（`private_backend=True`：bash 审批→pattern allow-always→Settings 验证） |
| `api/agent/test_shpoib_hitl_attach_replay.py` | 模块 | SHPOIB HITL attach replay 集成（subscribe / multiplexed attach / hitl-probe / CORP；无 Chrome/LLM） |
| `api/security/test_allowlist_api.py` | 模块 | Allowlist REST list/delete + pattern 粒度 round-trip |
| `integration/test_kanban_attach_handler_integration.py` | 模块 | SQLite attach handler + orchestrator unblock tool invoke |
| `services/kanban/test_kanban_attach_handler.py` | 模块 | attach handler 单测（path/URL/SSRF/limits） |
| `api/agent/test_kanban_agent_stream_e2e.py` | 模块 | Live LLM agent-stream kanban add/list（`@pytest.mark.e2e`） |
| `benchmarks/bench_mcp_ptc_vs_direct.py` | 基准 | MCP PTC vs 直连 token/延迟对比；凭据仅来自 `.env.test` |
| `fixtures/cp_proxy_signature_contract.json` | 辅助 | 控制服务反向代理 HMAC 契约向量（server 侧自包含） |
| `../scripts/dev/run_tests_low_memory.sh` | 辅助 | 本地低内存 pytest 入口（`-n0`，可选 `PYTEST_XDIST_WORKERS=N`） |
| `../scripts/dev/profile_test_memory.py` | 辅助 | 按 test 文件采样 peak RSS，定位高内存用例 |
| `services/migration/_ARCH.md` | 模块 | 迁移业务层测试清单（四源 discover/load/e2e） |
| `services/agent/stream_session/` | 模块 | 流式会话链路测试（含 `memory_brief` 预计算、SSE 首包顺序、snapshot_id 追踪） |
| `services/hosting/` | 模块 | 多 target artifact 发布 API 与 provider 单测 |
| `architecture/_ARCH.md` | 模块 | 架构约束测试（含 migration 源闭包） |
| `api/runs/test_router.py` | 模块 | Unified Runs Hub 聚合 API 单测（20 项：源合并、degraded、分页、timed_out） |
| `remote_access/` | 模块 | 远程访问 trust_zone / pairing / E2EE / mobile_gate / host_allowlist 单测（16 文件） |
| `tasks/test_task_worker_retry.py` | 模块 | TaskWorker 自动重试回归（transient 重入 pending + datetime `next_retry_at`、permanent 失败终止、retries exhausted 终止；`next_retry_at` 未到期不消费、到期后执行，终态清空 `next_retry_at` 语义） |
| `tasks/test_task_event_bus.py` | 模块 | TaskEventBus 回归（事件正常入队；队列满时淘汰最旧并投递带 `sync_required` 的最新事件，断言 emitted/dropped/replaced 指标与 queue_full warning 节流） |

---

## [T] 测试密钥约定

1. 开发者复制 `myrm-agent-server/.env.test.example` → `.env.test`（gitignored）
2. `tests/conftest.py` 调用 `apply_test_secrets_to_environ()` 供 legacy `skipif(os.getenv(...))` 兼容
3. 新测试优先使用 `test_secrets` fixture 或 `resolve_test_env()`，禁止在源码中硬编码密钥
4. 权威变量索引：`.env.example`（[P/O]）、`.env.sandbox.example`（[S]）、`.env.test.example`（[T]）

---

## 测试分层（默认 `pytest`）

- 默认 `addopts`：`-m 'not e2e and not chrome_e2e and not performance'`（跳过 e2e、Chrome MCP UI E2E 与 benchmark/performance）
- **低内存推荐（本地 / CI 同款）**：`scripts/dev/run_tests_low_memory.sh` 或 monorepo **`./myrm test -n0`**
- 单元 + API 集成：monorepo **`./myrm test -n0`**（单 worker；实测 `build_minimal_app(chats)` ~118MB，`app.main` ~439MB）
- E2E（真实 LLM API，无 Chrome）：monorepo **`./myrm test -m e2e`**（`test.sh` 对非 chrome 路径自动设 `MYRM_E2E_LEASE_ID`；如 `tests/api/agent/test_kanban_agent_stream_e2e.py`）
- **Chrome MCP UI E2E（`chrome_e2e` marker）**：monorepo **`./myrm test -m chrome_e2e -n0`**（须 `./myrm ready --chrome`；Wave lease；见 `scripts/dev/CHROME_MCP_E2E.md`）
- **Kanban Chrome E2E**：`tests/e2e/test_kanban_chrome_e2e.py`（READ lane ×4，`private_backend=True` 自动 per-item 私 Backend，避免共享 `:8080` SQLite 锁；看板列渲染 + `?source_chat=` 深链 + Chat 成功卡 → 过滤看板）
- **Wiki citation Chrome E2E**：`tests/e2e/test_wiki_citation_chrome_e2e.py`（READ lane ×2：`/chats/test/seed-citation-fixture` → citation 按钮 reload 持久；`/settings/wiki?agentId=` combobox）。Settings 用例先 `warm_ui_route` HTTP 编译再 Chrome 导航（webpack 冷启）。READ 使用共享 `:8080`（`private_backend=False`）；**`private_backend=True`（SHPOIB）测例走私池 :180xx，并行窗口内无需 restart 共享栈**；仅共享 READ 写库测例新增 server 路由后须 `./myrm restart` 或 **`./myrm isolate <id> ready --chrome`**。
- **RevertFiles Chrome E2E**：`tests/e2e/test_revert_files_chrome_e2e.py`（READ×5：modify undo+diff+confirm；empty toast；large_skip non-revertible toast；reload hydrate undo；session SessionRevertButton）
- **Memory citations Chrome E2E**：`tests/e2e/test_memory_citations_chrome_e2e.py`（READ lane ×2：`/settings/memory` 开「历史会话搜索」；聊天页注入 citations → 「依据/Evidence N」Sheet）。并行 attach 若 mux timeout drift，须 `MYRM_MUX_ALLOW_TIMEOUT_RESTART=1`（见 `chrome-e2e-preflight.sh` attach heal）。
- **Voice memory ACL Chrome E2E**：`tests/e2e/test_voice_memory_acl_chrome_e2e.py`（READ lane ×2：Settings UI 开/关 memory+sessions → `personalSettings` API 断言；**不依赖** Providers Google key；corpus enum / tool-exec flags 见 `test_voice_memory_acl_api_integration.py`）。
- **Skill marketplace LIVE Chrome E2E**：`tests/e2e/test_skill_marketplace_live_agent_chrome_e2e.py`（LIVE×1：`skill_discovery_tool` 外部市场搜索；自定义 Agent system_prompt + `/?agentId=`；自然中文用户消息；API/UI 双路径断言；见 `scripts/dev/CHROME_MCP_E2E.md`）
- **Subagent Dashboard Chrome E2E**：`tests/e2e/test_subagent_dashboard_chrome_e2e.py`（LIVE lane ×3：`subagent-dashboard-e2e-prepare.mjs` delegate → Dashboard cancel / pause toggle / token+model；`open_mcp_page(..., timeout_ms=MAX_PAGE_TIMEOUT_MS)`）
- **Subagent rebind 单测**：`tests/services/agent/test_subagent_rebind_event.py`（`AgentService.update_agent` 变更 `subagent_ids` → `SUBAGENT_REBIND_REQUIRED`）
- **Citation seed 集成单测**：`tests/api/chats/test_citation_seed_integration.py`（seed → GET messages 断言 `citedMemoryIds`；默认 CI 套件执行，不依赖 Chrome）
- **A2UI Surface Gate Chrome E2E**：`tests/e2e/test_render_ui_surface_gate_chrome_e2e.py`（READ×2：Settings hint + `client_surface=web|tauri` + `__TAURI__`→`tauri`；submit+capture 3× mux 重试、`timeout=600`、`open_mcp_page timeout_ms=120_000`；LIVE inline 见 `test_render_ui_inline_card_chrome_e2e.py`；LIVE 按钮点击 → `ui_action` 见 `test_render_ui_inline_interaction_chrome_e2e.py`；LIVE `update_ui_data` 增量刷新 + **reload DB 持久**见 `test_render_ui_update_data_chrome_e2e.py`）
- **A2UI surface_unavailable 单测**：`tests/services/agent/stream_session/test_entitlement_gap_preflight.py`（IM + render_ui ON + UI 意图 → `reason=surface_unavailable`；Web 可挂载 → None；dedup）；`tests/core/channel_bridge/test_stream_events.py`（`capability_gap` → ProgressUpdate）；frontend `gapEvents.test.ts`（info-only toast，无 enable/resend）
- **A2UI 跨轮 DB patch 单测**：`tests/services/chat/test_ui_artifact_patch.py`（双 turn seed → `patch_ui_artifact_data_by_surface_id` → GET messages 断言 merged binding；collector 跨轮队列；finalize 接线）
- `tests/integration/test_render_ui_sse_wiring.py`：render_ui 确定性集成（20 场景：run_bind、fail-closed、data_update、collector 链、幂等）
- `tests/integration/test_ui_artifact_cross_turn_db_integration.py`：跨轮 `data_update` collector 队列 → 真实 SQLite patch → GET messages 断言 merged binding（无 mock 持久化路径）
- 并行（内存充足时）：`PYTEST_XDIST_WORKERS=4 scripts/dev/run_tests_low_memory.sh`；避免 `-n auto`（多 worker RSS 叠加，`-n auto` 在 8 核上可达数 GB）
- 定位高内存文件：`uv run python scripts/dev/profile_test_memory.py tests/api/agent --top 20`
- WebUI E2E：MCP **chrome-devtools** + Myrm E2E Chrome `:9333`（`./myrm ready --chrome`）；marker **`chrome_e2e`**（`lane=READ|LIVE_AGENT`）；禁止 `@playwright/test`。正式入口 **`./myrm test -m chrome_e2e`**；`tests/e2e/test_*_chrome_e2e.py`（含 Goal、execution_cache、edge_tts、parallel_tabs READ lane、`test_push_approval_deeplink_chrome_e2e` 等）；READ 只读测例不占 LIVE_AGENT cap（`resolve_e2e_session_lane.py`）
- CI 默认套件：`scripts/ci/run_default_tests.sh`（`-m 'not e2e and not performance' -n0`，workflow `server-unit-tests.yml`）
- `tests/api/skills/test_drafts_seed_mock.py`：seed-mock HTTP 单测（含 `agent_id` 查询参数，默认套件执行）
- `tests/api/approvals/test_seed_mock.py`：approvals push deeplink seed-mock HTTP 单测（local guard + pending list）
- `tests/api/approvals/test_list_pending_growth_filter.py`：`GET /approvals` 排除后台 growth、保留 inline `thread_id` skill_draft
- `tests/api/skills/conftest.py`：minimal app 含 drafts/curator/sync/evolution/skill-growth 路由
- `tests/api/integrations/test_llm_speed_test.py`：`POST /api/v1/integrations/llm/speed-test`
- `tests/api/notifications/conftest.py`：in-memory DB + loopback auth（通知 API 集成测）
- `tests/api/config/test_readiness_e2e.py`、`tests/api/security/test_generate_policy_e2e.py`：`@pytest.mark.e2e`（默认套件不收集）

## 依赖

- `tests/conftest.py` → `tests/support/test_secrets.py`（**唯一** [T] 加载入口）
- 新 API/集成测优先 `from tests.support.minimal_app import build_minimal_app` + `preset_for_test_path()`，禁止 `from app.main import app`
- `tests/conftest.py` → integration/e2e/lifecycle 路径 autouse `reset_global_browser_pool_for_tests()`（防 Chromium 跨测累积）；sessionfinish 释放 DB engine 与 `_memory_manager_cache`
- `tests/unit/test_system_storage.py`：系统存储 API 单元测（**禁止**在 `tests/unit/` 下创建 `api/` 子包，会与 `tests/api/` 在 `import_mode=importlib` 下冲突）
- `app/startup/env_loader.py` **不**读取 `.env.test`
