# tests 模块架构

pytest 测试套件根目录。单元/集成/API/E2E 测试按域分子目录；[T] 业务密钥仅通过结构化 fixture 加载，不进入 server 运行时。

---

## 文件清单

| 路径 | 地位 | 职责 |
|------|------|------|
| `conftest.py` | 核心 | 进程级 `.env` + [T] secrets bootstrap、隔离 workspace、`test_secrets` session fixture、integration/e2e 路径每测后 `reset_global_browser_pool_for_tests()`、session 结束 + `@chrome_e2e` timeout 时 `reset_database_engine()` + `reap_chrome_e2e_session_hygiene()` + `shutdown_cached_memory_managers()`、浏览器进程树 cleanup（`tests/support/browser_process_cleanup`）；`@pytest.mark.chrome_e2e` 三维 profile + **PRIVATE 必填 `private_reason`**（与 `resolve_e2e_session_profile.py` 对齐） |
| `support/browser_process_cleanup.py` | 辅助 | pytest 进程树内 browser 自动化子进程 teardown |
| `support/test_browser_process_cleanup.py` | 单元 | browser_process_cleanup 单测（100% 覆盖） |
| `support/test_secrets.py` | 核心 | [T] `.env.test` 结构化加载（`TestSecrets`、`load_test_secrets`、`resolve_test_env`） |
| `support/wb_bench_e2e_helpers.py` | 辅助 | WBBench Chrome E2E 共享探针 SSOT：`SOURCES_READY_JS`、`all_cards_memory_ab_ready_js`（每卡片 Memory A/B 按钮就绪）、`click_subset_memory_ab_js`、`restore_eval_lab_route`、`reset_wb_bench_source` 等 |
| `support/minimal_app.py` | 核心 | `build_minimal_app(preset=...)` 按需挂载 API 路由；禁止测试 import `app.main` |
| `support/feature_flags.py` | 辅助 | `seed_voice_interaction_flags()`，供 `tests/api/voice`、`tests/api/stt` conftest autouse |
| `support/verify_api_base.py` | 辅助 | Live 集成测 verify-api 私池 base SSOT（`resolve_verify_api_base()`；epoch 匹配 + `--ensure-backend` seed） |
| `support/theme_marketplace_e2e.py` | 辅助 | Theme marketplace E2E：CP 探活、JWT、official seed、listing 查询 |
| `support/gap_toast_chrome_e2e_contract.py` | 辅助 | Gap Toast E2E Dual-Plane SSOT（Verification=API/integration · Experience=browser send+poll；禁止 chrome_e2e body 内 agent-stream httpx） |
| `support/bash_compressor_e2e.py` | 辅助 | bash compressor live/API E2E 共享 helper（模型 probe、workspace 压缩回放） |
| `support/e2e_wall_progress.py` | 辅助 | Chrome E2E 墙钟 progress token（R57：仅 touch，不再重置 body 计时） |
| `../scripts/dev/lib/e2e_shared_ui_session.py` | 辅助 | R51-v2 Shared UI Session Contract（marker `e2e_search_policy` · conftest env · bootstrap/`click_new_chat` 四阶段 reset） |
| `support/chrome_memory_settings_e2e.py` | 辅助 | `/settings/memory` Chrome 开关 JS SSOT（memory citations + voice ACL E2E 共用） |
| `support/evicted_drawer_selectors.py` | 辅助 | UECD Drawer Chrome E2E 共享选择器/探针 SSOT（`data-testid` 定位 + `/files/evicted` 分页参数断言） |
| `api/agent/utils.py` | 辅助 | Agent 测试共享工具（模型/搜索配置组装） |
| `e2e/conftest.py` | 辅助 | E2E ephemeral server fixture（API 级 e2e，不启动前端） |
| `e2e/test_migration_readiness_gap_chrome_e2e.py` | 模块 | migration post-import readiness gap（LIVE×3 SHPOIB：`mcp_warning` · `provider_critical` · `diagnostic_critical` 各独立 `::test_*` · R139 禁 batch） |
| `e2e/test_mcp_reload_confirm_chrome_e2e.py` | 模块 | MCP Settings reload 确认 Chrome E2E（READ×1 SHPOIB 单会话：toggle cancel/confirm · delete · import JSON · add/save → `GET /config/mcpServers` 断言） |
| `e2e/test_kanban_chrome_e2e.py` | 模块 | Kanban Chrome MCP E2E（READ×14：看板渲染 + source_chat 深链过滤 + Drawer 附件 + Chat 成功卡片→看板 + stats bar running N/M + ready 排队 badge ±（占满显示/未满不显示）+ 多 ready 同时排队 badge + 真实执行排队释放闭环 + 队列按序释放 badge 递减 + model_override UI 建卡 / 抽屉徽章编辑清除 + 技能选择器 UI 建卡（真实技能集，picker 搜索选择 → extra_skill_ids 持久化）+ 抽屉技能编辑保存（chips → 编辑态 → picker 增选 → 保存 → 退出编辑态且持久化）） |
| `e2e/test_wiki_citation_chrome_e2e.py` | 模块 | Wiki citation Chrome MCP E2E（READ×2：citation reload + `/settings/wiki?agentId=`） |
| `e2e/test_wiki_dedup_chrome_e2e.py` | 模块 | Wiki corpus dedup Chrome MCP E2E（SHARED+READ×1：seed-after-warm → duplicateReview exact group panel） |
| `e2e/test_wiki_compound_chrome_e2e.py` | 模块 | Wiki chat compound Chrome E2E（SHARED+READ×3：`POST /chats/` seed Q&A → `POST /wiki/compound` happy+409 dedup · incognito 403 · user role 422） |
| `e2e/test_wiki_health_report_chrome_e2e.py` | 模块 | Wiki health report Chrome E2E（SHARED+READ×1：API structural health + seed provenance gap → 单 tab Overview `[data-testid=wiki-health-section]` + stats badge；shell 探针 `wiki-settings-shell`；transport retry 同 dedup） |
| `e2e/test_clarify_refresh_chrome_e2e.py` | 模块 | Clarify refresh Chrome MCP E2E（READ×4 SHPOIB：`seed-clarify-refresh-fixture` pending/answered/regenerate_sibling/structured_form → F5 hydrate 断言 composer 态） |
| `e2e/test_clarify_skip_chrome_e2e.py` | 模块 | Clarify skip LIVE×1 SHPOIB：真实 LLM HITL → Skip → resume（`E2E_SIGNOFF=1` API fallback）；M3 stub 签收腿已删 |
| `api/chats/test_clarify_refresh_seed_fixture.py` | 模块 | clarify refresh seed HTTP 单测（local-only gate + 三 variant mock 持久化） |
| `e2e/test_integration_catalog_loopback_guard_chrome_e2e.py` | 模块 | Integration Catalog loopback guard Chrome MCP E2E（READ×3：live API `deployment_scope` 与 `/integrations/mcp/probe` 语义断言 + 阻断链 `scan/verify` 不扇出 + `recommendedMode` 在 `connection_refused` / `probe_failed_unknown` 重试后自动续接连接） |
| `e2e/test_memory_citations_chrome_e2e.py` | 模块 | Memory Chrome MCP E2E（READ×2：设置「历史会话搜索」开关；统一「依据/Evidence N」Sheet） |
| `e2e/test_voice_memory_acl_chrome_e2e.py` | 模块 | Voice memory ACL Chrome MCP E2E（READ×2：`/settings/memory` UI 开/关「历史会话搜索」→ `GET /config/personalSettings` 断言；token corpus 由 HTTP 集成测覆盖） |
| `api/voice/test_voice_memory_context.py` | 模块 | Voice memory ACL SSOT 单元 + policy 矩阵 |
| `api/voice/test_voice_memory_acl_api_integration.py` | 模块 | Voice memory ACL HTTP 集成（realtime/gemini token enum + tool-exec flags，ACL 路径 unmocked） |
| `e2e/test_background_tasks_panel_chrome_e2e.py` | 模块 | Background Tasks Panel Chrome MCP E2E（READ×5 SHPOIB：打开 Panel、failed/running seed、UI cancel、`vault_log` drawer、`success` finish toast；`data-testid=background-task-cancel` / `background-task-view-vault-log`） |
| `e2e/test_background_shell_live_agent_chrome_e2e.py` | 模块 | Background shell LIVE×1 SHPOIB（`lane=LIVE_AGENT`，默认 `private_backend=True`）：自然语言 user turn + `bash_code_execute_tool` stream（HITL 时 `decisions[]` approve resume）；5× stream retry + REST 20s probe + 3× chat retry；`finally` teardown cancel |
| `e2e/test_skill_marketplace_live_agent_chrome_e2e.py` | 模块 | Skill marketplace LIVE×1 SHPOIB：`skill_market_tool` 经 agent-stream 真实 LLM 调用断言；UI toggle 见 READ `test_skill_mount_builtin_gate_chrome_e2e` |
| `api/agent/test_memory_conversation_search_e2e.py` | 模块 | Memory + sessions opt-in API 集成（真实 LLM agent-stream；8 场景：opt-in/incognito/memory-off/多轮/passphrase） |
| `ai_agents/test_custom_agent_factory.py` | 模块 | Custom/Ephemeral 子 Agent `memory_search_tool` rebind + factory build 路径（38 项；`--cov-fail-under=90` on factory） |
| `ai_agents/test_conversation_search_opt_in_integration.py` | 模块 | conversation-search opt-in 与 tool_setup 绑定集成 |
| `e2e/test_theme_marketplace_gallery_chrome_e2e.py` | 模块 | Theme Studio Gallery 免费安装 Chrome MCP smoke（READ×1：CP seed→acquire→download→install-from-marketplace） |
| `e2e/test_subagent_dashboard_chrome_e2e.py` | 模块 | Subagent Dashboard Chrome MCP E2E（LIVE×6：cancel running、delegation pause toggle、SSE token/model 展示、budget used/limit、canvas 拓扑渲染 + 点击定位回树、fission 拓扑合并渲染） |
| `api/eval/test_memory_ab_live_integration.py` | 模块 | Memory A/B Live 集成（`@pytest.mark.e2e`）：真实 embedding probe + WBBench office 真实下载构建 + 双臂真实 LLM 执行 + `memory_tool_calls` 报告 + 临时记忆卷清理（关键路径禁 mock；执行 case 数受限） |
| `e2e/test_memory_ab_chrome_e2e.py` | 模块 | Memory A/B Chrome E2E（READ×1 + NAMESPACE_WRITE×2）：WBBench 卡片 Memory A/B 入口 + 确认对话框取消（READ）；预置双报告渲染双臂矩阵 + Run History 表（per-arm pass-rate + `memory_tool_calls`）+ 点击历史 View 加载（NAMESPACE_WRITE）；真实 run 启动（SSE running + header Stop）+ Stop abort 清理（NAMESPACE_WRITE） |
| `services/agent/test_subagent_rebind_event.py` | 模块 | `SUBAGENT_REBIND_REQUIRED` 事件：`subagent_ids` 变更时 publish、同值/非绑定字段不 emit |
| `services/agent/readiness/test_readiness_mcp_secrets.py` | 模块 | readiness mcp 维度密钥预检（`_check_mcp` 六分支：requiredSecrets 全齐不报 / 缺失报 / headers `{{secret:KEY}}` 引用报 / disabled 跳过 / 无声明不查 / vault 异常跳过）+ org MCP 合并单测 |
| `api/internal/test_org_mcp_sync_integration.py` | 模块 | org MCP 真实 DB 全链路集成：CP `POST /api/admin/org-mcp-sync` → ConfigService 加密落库 → `load_user_config_entry` 解密加载 → `merge_org_mcp_configs` 合并（scope=org）→ readiness `_check_mcp` 识别绑定 org server（关键路径无 mock） |
| `services/agent/backends/test_secret_backend_list_keys.py` | 模块 | `DatabaseSecretBackend.list_secret_keys` 真实 DB（保存后键名列表、未知 agent 空列表；FK 预置 agent + 测后清理） |
| `api/chats/test_citation_seed_fixture.py` | 模块 | citation fixture seed HTTP 单测（local-only，`/chats/test/seed-citation-fixture`） |
| `api/chats/test_deliverable_seed_fixture.py` | 模块 | deliverable link fixture seed HTTP 单测（`/chats/test/seed-deliverable-link-fixture`） |
| `core/artifacts/test_processor_short_file_id.py` | 模块 | LocalArtifactProcessor 透传 `short_file_id` → artifacts SSE JSON |
| `core/artifacts/test_processor_oversized_shareable.py` | 模块 | Local 超大可分享 reference-only persist + processor→deliverable 集成（sandboxes 路径、一次 resolve） |
| `core/artifacts/test_processor_upsert_emit.py` | 模块 | upsert 失败不 emit / 部分 upsert 失败只 emit 成功项 |
| `e2e/test_deliverable_link_chrome_e2e.py` | 模块 | Deliverable inline link Chrome READ E2E（seed → 自然路由 hydrate → `[data-testid=deliverable-reference-link]` → Portal 预览；**禁止 attachToChat**，store/DOM 不同步） |
| `api/wiki/test_wiki_structural_cache_invalidation.py` | 模块 | Wiki vault mutation SSOT：`_after_wiki_vault_mutation` 在 apply/move/repair-publication/delete/repair-types/pending approve 等端点触发或 skip（9 项） |
| `api/wiki/test_maintain_endpoint.py` | 模块 | POST /maintain：默认 structural mode · `?mode=full` · compile-busy 409 |
| `api/chats/test_kanban_closure_seed_fixture.py` | 模块 | Kanban closure fixture seed HTTP 单测（`/chats/test/seed-kanban-closure-fixture`） |
| `api/chats/test_kanban_closure_seed_integration.py` | 模块 | Kanban closure seed 真 DB 集成（metadata + board task） |
| `api/chats/test_citation_seed_integration.py` | 模块 | citation seed → GET messages 集成单测（真 DB metadata） |
| `api/chats/test_prior_chat_recall_integration.py` | 模块 | prior_chat seed → GET `/recall/search` SSOT + mention inject 集成（真 DB，无 mock） |
| `e2e/test_evicted_live_terminal_chrome_e2e.py` | 模块 | UECD EvictedOutputDrawer Chrome MCP E2E（READ×1 SHPOIB：**单 tab** 全文 spill + `navigate` 过期 chat；选择器与分页探针统一来自 `support/evicted_drawer_selectors.py`；禁止拆成 2× `open_mcp_page`，并行 mux 会 30s timeout） |
| `e2e/test_bash_failure_dual_evicted_drawer_chrome_e2e.py` | 模块 | 失败 bash 双 evicted 流 Chrome MCP E2E（SHARED+NAMESPACE_WRITE×1：seed `bash_failure` variant → LiveTerminal stdout/stderr 双入口 → 各自 Drawer 读回；`evicted_view_full_output` / `evicted_view_full_stderr_output` data-testid） |
| `api/files/test_evicted_web_fetch_spill.py` | 模块 | UECD evicted-file API 单测（`web_fetch_{hex8}.md` basename + GET content） |
| `api/files/test_evicted_background_spill.py` | 模块 | UECD bash/background spill → evicted API 单测 |
| `integration/test_evicted_uecd_live_api_integration.py` | 模块 | UECD live API 集成（`resolve_verify_api_base()` 私池 · seed POST `_LIVE_SEED_POST_TIMEOUT_SEC=60` · GET evicted · 404 `expired` envelope） |
| `integration/test_artifact_share_integration.py` | 模块 | 工件分享真实全链路集成（无 mock）：`ArtifactVault.put` 真实落盘 → DB artifact/version → create share 真实物化 → public entry redirect → 静态资源放行；密码分享 gate + 签名解锁 cookie 授权 asset；SQLite 内存库 + TestClient 进程内 |
| `api/config/test_telegram_onboarding_apply.py` | 模块 | Telegram onboarding 原子编排回归（成功、失败回滚、同名冲突复用、并发防重、跨进程锁占用冲突） |
| `api/config/test_search_services_validation.py` | 模块 | searchServices Omni 422：unknown slug、duplicate enabled priority、non-selectable enabled slug |
| `api/config/test_omni_config.py` | 模块 | Omni-Config schema/sync/history/rollback；batch sync duplicate search priority 422 |
| `e2e/test_search_priority_chain_chrome_e2e.py` | 模块 | Search priority chain signoff（API integration persist + Chrome READ `lane=READ private_backend=False` Settings priority badges；payload Tavily p1 + Perplexity p2；`@pytest.mark.timeout(180)`） |
| `integration/test_fallback_integration.py` | 模块 | Harness provider_chain 集成：invalid primary hop、legacy role 迁移；SearXNG 不可用时 skip（`AllQueriesFailedError`） |
| `api/files/test_revert_seed_integration.py` | 模块 | Revert seed 四 variant + production persist root hydrate + channel cleanup（6 项；无 RevertService mock） |
| `services/files/test_revert_hydrate.py` | 单元 | `revert_hydrate.py` 100% 覆盖：root 解析顺序、hydrate、cleanup |
| `services/files/test_reveal_utils_obsidian.py` | 模块 | Obsidian launch 探测：Local/Tauri gate + macOS/Windows/Linux 安装路径 |
| `e2e/test_revert_files_chrome_e2e.py` | 模块 | RevertFiles Chrome MCP E2E（READ×5：modify undo+diff+confirm；empty toast；large_skip non-revertible toast；reload hydrate undo；session SessionRevertButton）；`prepare_e2e_ui_session` + `dismiss_blocking_modals` + async Sonner wait |
| `e2e/test_channel_routing_general_only_chrome_e2e.py` | 模块 | Channel Settings 渠道路由 Chrome MCP E2E（READ×1 SHPOIB：Settings → Channel Routing；Agent 下拉 **0 Search**；General-only SSOT 签收） |
| `e2e/test_allowlist_pattern_live_chrome_e2e.py` | 模块 | Allowlist pattern Chrome LIVE×1（`private_backend=True`：bash 审批→pattern allow-always→Settings 验证） |
| `e2e/test_file_write_empty_chrome_e2e.py` | 模块 | Empty file_write Chrome E2E（READ×2 SHPOIB：`seed-file-mutation-fixture?variant=empty_write` → FileMutationWarning 横幅 + `reload_mcp_page()` metadata 持久；LIVE×1：`test_file_write_empty_live_agent_webui` — 真实 LLM `file_write_tool(content='')` + mutation failure 横幅 + **磁盘无文件**；`@e2e_search_policy("empty")` + `seed-file-edit-batch-workspace` sandbox；**solo 签收** ~618s） |
| `api/chats/test_file_mutation_seed_fixture.py` | 模块 | HTTP：file-mutation seed `empty_write` → persisted `metadata.fileMutationFailures` |
| `api/chats/test_workspace_merge_seed_fixture.py` | 模块 | HTTP：workspace-merge seed `batch_merge_fail` → persisted `metadata.workspaceMergeFailures` |
| `e2e/test_workspace_merge_chrome_e2e.py` | 模块 | Chrome READ×2 SHPOIB：seed workspace merge fixture → WorkspaceMergeWarning + reload hydrate |
| `api/agent/test_stream_collector_file_mutation.py` | 模块 | StreamContentCollector `file_mutation_failed` / `workspace_merge_failed` → `extra_data.fileMutationFailures` / `workspaceMergeFailures` |
| `api/agent/test_agent_stream_retry_contract_e2e.py` | 模块 | agent-stream 重试契约：执行中同 `chat_id+message_id+content` 重试 → user turn 幂等 + SSE `AgentBusyError`(409)；mock Agent 挂起 active session；**early claim** 后须等 user persist 再 retry |
| `api/agent/test_agent_stream_concurrency_limit_e2e.py` | 模块 | agent-stream 并发上限契约：gateway 排队超时 `AgentQueueTimeout` → 结构化 SSE `error_kind=concurrency_limit`（`diagnostic_result` 含 reason/占用者/i18n 文案/resolution_steps）；holder 直接挂起 gateway 占槽位，waiter 走真实 HTTP 全链路 |
| `api/agent/test_reconnect_integration.py` | 模块 | ASGI Last-Event-ID 重连 + early busy 第二 turn 不双写 user row（mock agent） |
| `api/chats/test_stream_retry_busy_seed_fixture.py` | 模块 | stream-retry-busy seed/release HTTP + **`test_busy_fixture_query_is_not_risk_blocked`**（fixture 文案不得触发 risk gate） |
| `e2e/test_stream_retry_contract_chrome_e2e.py` | 模块 | Chrome READ×1 SHPOIB：seed busy fixture → API POST busy 断言 → **`retryStreamWithSameMessageId` UI `busy:true`** → userCount 不变 |
| `api/agent/test_timestamp_integration.py` | 模块 | Web 消息 timestamp/sent_at 持久化 + `ensure_chat_and_append_user_message` 幂等（同 id+content 复用 / 不同 content 换 id）；内存 SQLite |
| `api/agent/test_shpoib_hitl_attach_replay.py` | 模块 | SHPOIB HITL attach replay 集成（subscribe / multiplexed attach / hitl-probe / CORP；无 Chrome/LLM） |
| `api/security/test_allowlist_api.py` | 模块 | Allowlist REST list/delete + pattern 粒度 round-trip |
| `integration/test_kanban_attach_handler_integration.py` | 模块 | SQLite attach handler + orchestrator unblock tool invoke |
| `integration/test_project_workspace_bind_file_write_integration.py` | 模块 | Project bind → `convert_to_general_agent_params.declared_allowed_roots` → `file_write_tool` 磁盘断言（无 LLM） |
| `integration/test_durable_outbound_integration.py` | 模块 | Durable outbound 全链路集成（15 cases：含 QueueFull 自动 recover、edit_placeholder、send_tracked、edit fallback、null-send→DLQ） |
| `api/health/test_liveness_pending_outbound.py` | 模块 | GET `/health/liveness` 返回 `pendingOutboundCount` |
| `e2e/test_org_model_policy_chrome_e2e.py` | 模块 | Org model policy Chrome MCP E2E（PRIVATE×1 SHPOIB：`exclusive_backend` · SHPOIB 后 `POST /api/admin/org-model-policy-sync` seed `minimax/*` → 打开 model picker → minimax 可选 / openai-like 灰显） |
| `api/chats/test_effective_workspace_ssot.py` | 模块 | SSOT：GET chat / suggest / browse(chat_id) / PATCH 409 — project.workspace_path 优先于 stale chat.workspace_dir |
| `services/workspace/test_file_watch_service.py` | 模块 | P1：watchdog emit / release / refcount → `WORKSPACE_FILE_CHANGED` |
| `api/files/test_browse_watch_api.py` | 模块 | P1：POST/DELETE `/files/browse/watch` 注册/释放 + 危险路径拒绝 |
| `services/project/test_legacy_workspace_path_migration.py` | 模块 | 假 `workspace_path` SQL 清理语义（清 `/persistent/workspace/project_%`、保留真实 bind） |
| `services/kanban/test_kanban_attach_handler.py` | 模块 | attach handler 单测（path/URL/SSRF/limits） |
| `services/kanban/test_board_settings_roundtrip.py` | 模块 | BoardSettings 9 字段 ORM 往返完整性（三映射函数 + dataclass 字段覆盖守卫 + 旧库 ALTER 迁移默认值） |
| `services/agent/test_agent_name_resolution.py` | 模块 | Agent 同名解析确定性单测（大小写归一 + 稳定排序 + 空名短路） |
| `api/agent/test_kanban_agent_stream_e2e.py` | 模块 | Live LLM agent-stream kanban add/list（`@pytest.mark.e2e`） |
| `api/agent/test_mcp.py` | 模块 | Agent MCP 集成（`@pytest.mark.e2e`）：amap · 12306 Node stdio PTC；TestClient 进程内；须 `-m e2e` |
| `api/agent/mcp_e2e_helpers.py` | 辅助 | MCP E2E 启动/preflight：12306 stdio 解析、LLM preflight、shared venv prewarm |
| `api/agent/mcp_e2e_goodhart.py` | 辅助 | MCP E2E Goodhart 锚点：skill/PTC/get_tickets deliver 断言 |
| `api/agent/mcp_e2e_stream.py` | 辅助 | MCP E2E SSE runner：`run_mcp_agent_stream`、approval resume、iteration_limit 旗标 |
| `benchmarks/bench_mcp_ptc_vs_direct.py` | 基准 | MCP PTC vs 直连 token/延迟对比；凭据仅来自 `.env.test` |
| `fixtures/cp_proxy_signature_contract.json` | 辅助 | 控制服务反向代理 HMAC 契约向量（server 侧自包含） |
| `../scripts/dev/run_tests_low_memory.sh` | 辅助 | 本地低内存 pytest 入口（`-n0`，可选 `PYTEST_XDIST_WORKERS=N`） |
| `../scripts/dev/profile_test_memory.py` | 辅助 | 按 test 文件采样 peak RSS，定位高内存用例 |
| `services/migration/_ARCH.md` | 模块 | 迁移业务层测试清单（五源 discover/load/e2e） |
| `services/memory/test_import_sessions.py` | 模块 | import session lifecycle；readiness/first-turn 持久化；`recheck_facts` SSOT + readiness recheck facts fallback |
| `services/memory/test_import_readiness.py` | 模块 | 导入后 `readiness` 合同规则单测（ready/warning/critical + issue codes + settings_path） |
| `services/agent/stream_session/test_migration_readiness_preflight.py` | 模块 | migration readiness live preflight：`from_readiness` SSE + async `resolve_and_build_*`（warning→/settings/mcp） |
| `services/agent/stream_session/test_migration_readiness_anchor_live_fallback.py` | 模块 | finalize 缺 preflight live 时再 resolve；resolve 失败不落 stale anchor |
| `api/memory/test_import_readiness_recheck_api.py` | 模块 | `POST /memory/import/readiness-recheck` HTTP 集成测（200/404） |
| `services/agent/stream_session/test_migration_readiness_anchor.py` | 模块 | migration readiness 首轮结果归类单测（success/failed/no_output） |
| `services/agent/stream_session/test_migration_bound_project.py` | 模块 | migration vault bind 同窗 handoff：`persist` 后 `move_chat_to_project`；已有 project / resume 跳过 |
| `services/hosting/` | 模块 | 多 target artifact 发布 API 与 provider 单测 |
| `architecture/_ARCH.md` | 模块 | 架构约束测试（含 migration 源闭包） |
| `api/runs/test_router.py` | 模块 | Unified Runs Hub 聚合 API 单测（20 项：源合并、degraded、分页、timed_out） |
| `remote_access/` | 模块 | 远程访问 trust_zone / pairing / E2EE / mobile_gate / host_allowlist 单测（16 文件） |
| `tasks/test_task_worker_retry.py` | 模块 | TaskWorker 自动重试回归（transient 重入 pending + datetime `next_retry_at`、permanent 失败终止、retries exhausted 终止；`next_retry_at` 未到期不消费、到期后执行，终态清空 `next_retry_at` 语义） |
| `tasks/test_task_event_bus.py` | 模块 | TaskEventBus 回归（事件正常入队；队列满时淘汰最旧并投递带 `sync_required` 的最新事件，断言 emitted/dropped/replaced 指标与 queue_full warning 节流） |
| `e2e/test_team_hub_builtin_badge_chrome_e2e.py` | 模块 | Team Assets Hub 内置 Agent 徽标 + 名称本地化 Chrome E2E（PRIVATE+READ×1：API 数据契约 `is_built_in` + `/settings/memory?sub=team-hub` 渲染「内置」徽标与 `getBuiltinAgentName` 本地化名 + follow-ups 筛选下拉本地化 + zh 界面无英文名泄漏） |
| `e2e/test_pending_approvals_chrome_e2e.py` | 模块 | Fleet pendingApprovals KPI Chrome E2E（PRIVATE+NAMESPACE_WRITE×1：`POST /chats/test/seed-kanban-in-review-fixture` 单写者建 IN_REVIEW 任务 → 真实 UI /agents Fleet「Pending」KPI +1 → **点击 KPI 卡片验证深链直达 `/settings/kanban?status=in_review`（看板自动选中含待审任务的 board + status 过滤条 + 任务卡片落地）** → 双击卡片开抽屉 approve/reject 双生命周期回落；fixture 绑定内置 agent，抽屉 agent 下拉断言本地化名不泄漏英文） |
| `api/statistics/test_badges.py` | 模块 | Nav badges API 单测（monkeypatch kanban 合并 + OperationalError 降级；`TestKanbanCountRealStore` 真 SQL store 链验证 `count_tasks_by_agent`/`count_tasks` 聚合） |
| `api/statistics/test_pending_approvals_integration.py` | 模块 | pendingApprovals 全链路集成（真实 store seed IN_REVIEW → badges/fleet KPI 反映真实行；approve/reject 后回落；goal+kanban 合并） |
| `api/agent/test_fleet_overview_integration.py` | 模块 | Fleet Overview API 集成（Chat/CronJob/Approval 真实 DB 聚合 + kanban IN_REVIEW 并入 pendingApprovals + kanban store 故障降级） |
| `api/chats/test_kanban_in_review_seed_integration.py` | 模块 | IN_REVIEW seed fixture 集成（fixture → badges 计数 + approve/reject 转换回落） |
| `core/web_push/test_push_deep_links.py` | 模块 | Web Push 点击路由（resolve_push_url：APPROVAL_REQUIRED 深链、pending_review+board_id 直达看板 in_review 列、非 review 状态回退聊天页、缺 chat 回首页） |
| `api/kanban/test_in_review_api.py` | 模块 | IN_REVIEW 审批 API（approve/reject 转换、守卫、pending_review 通知 payload 含 board_id） |
| `platform_utils/sandbox/_ARCH.md` | 模块 | `platform_utils/sandbox` 业务逻辑回归（platform provider seed 14 例 + tool gateway merge），见子目录清单 |

---

## [T] 测试密钥约定

1. 开发者复制 `myrm-agent-server/.env.test.example` → `.env.test`（gitignored）
2. `tests/conftest.py` 调用 `apply_test_secrets_to_environ(overwrite=False)` — 已有 `os.environ`（shell/monkeypatch）优先于 `.env.test`
3. 新测试优先使用 `test_secrets` fixture 或 `resolve_test_env()`，禁止在源码中硬编码密钥
4. 权威变量索引：`.env.example`（[P/O]）、`.env.sandbox.example`（[S]）、`.env.test.example`（[T]）

---

## 测试分层决策

pytest marker 是收集过滤器。四层金字塔（server 侧）：

| 层级 | marker | 职责 | LLM | Chrome | 默认 `addopts` | monorepo 命令 |
|------|--------|------|-----|--------|----------------|---------------|
| 单元 | 无 / 快测 | 单模块逻辑 | 否 | 否 | 收集 | `./myrm test -n0 <路径>` |
| integration | `@pytest.mark.integration` | 跨模块 wiring（registry、mount、converter、HTTP 契约） | 通常否 | 否 | 收集 | `./myrm test -n0 <路径>` |
| e2e | `@pytest.mark.e2e` | Agent-stream 全回合（SSE、MCP stdio、工具链） | 是（`.env.test`） | 否 | **排除** | `./myrm test -m e2e <路径>` |
| chrome_e2e | `@pytest.mark.chrome_e2e` | WebUI 用户操作（`:3000` + MCP mux） | 常要 | 是 | **排除** | `./myrm ready --chrome` + `./myrm test -m chrome_e2e …` |

- 入口统一 **`./myrm test`**（`test.sh` → `run-pytest-safe.sh` → `.venv/bin/python -m pytest`）；禁止 `uv run pytest`。
- 维护者速查：`scripts/dev/MAINTAINER_QUICKSTART.md`「测试分层速查」。
- **不涉及前端**：integration / e2e / `support/verify_api_base.py` + `./myrm verify-api`；多数 `@pytest.mark.e2e` 用 TestClient 进程内跑，不必 `:8080` live server。
- **harness**（`myrm-agent-harness/tests/`）：默认 `-m 'not integration and not e2e …'` → monorepo `./myrm test -m integration …`。
- `-m e2e` 与 `-m chrome_e2e` 互不包含；缺 marker 时带 e2e 标签的 node 会 deselect。

示例：

```bash
# integration（默认收集）
./myrm test -n0 tests/integration/test_chat_runtime_pool_live_integration.py

# e2e（须 -m e2e）
./myrm test -m e2e tests/api/agent/test_mcp.py::TestAgentMCP::test_agent_with_12306_python_mcp
```

---

## 测试分层（默认 `pytest`）

- 默认 `addopts`：`-m 'not e2e and not chrome_e2e and not performance'`（跳过 e2e、Chrome MCP UI E2E 与 benchmark/performance）
- **低内存推荐（本地 / CI 同款）**：`scripts/dev/run_tests_low_memory.sh` 或 monorepo **`./myrm test -n0`**
- 单元 + API 集成：monorepo **`./myrm test -n0`**（单 worker；实测 `build_minimal_app(chats)` ~118MB，`app.main` ~439MB）
- E2E（真实 LLM API，无 Chrome）：monorepo **`./myrm test -m e2e`**（`test.sh` 对非 chrome 路径自动设 `MYRM_E2E_LEASE_ID`；如 `tests/api/agent/test_kanban_agent_stream_e2e.py`）
- **Chrome MCP UI E2E（`chrome_e2e` marker）**：monorepo **`./myrm test -m chrome_e2e -n0`**（须 `./myrm ready --chrome`；Wave lease；见 `scripts/dev/CHROME_MCP_E2E.md`）
- **Kanban Chrome E2E**：`tests/e2e/test_kanban_chrome_e2e.py`（`execution_mode=SHARED` ×14：看板列渲染 + `?source_chat=` 深链 + Chat 成功卡 → 过滤看板 + stats bar running `N/M` 并发占用 + ready 排队 badge ±（并发占满时显示 / 未满不显示）+ 多 ready 同时排队 badge（1 running + 2 ready 全部显示）+ 真实执行排队释放闭环（UI 建卡 → dispatcher 真实 LLM 执行 → 占槽 badge 出现 → 释放后 badge 消失 → 双双完成）+ 队列按序释放 badge 递减（3 任务单槽：2 badge→1 badge→0 badge）+ model_override UI 建卡/抽屉徽章编辑清除 + 技能选择器 UI 建卡（picker 搜索选择真实技能 → `extra_skill_ids` 持久化）+ 抽屉技能编辑保存（chips → 编辑态 → picker 增选 → 保存 → 退出编辑态且 API 持久化）。marker 已用现代 profile 字段（`execution_mode/access_scope/workload`），不再支持 legacy `private_backend` 字段（`resolve_e2e_session_profile.py` 强制）。
- **Wiki citation Chrome E2E**：`tests/e2e/test_wiki_citation_chrome_e2e.py`（READ lane ×2：`/chats/test/seed-citation-fixture` → citation 按钮 reload 持久；`/settings/wiki?agentId=` combobox）。Settings 用例先 `warm_ui_route` HTTP 编译再 Chrome 导航（webpack 冷启）。READ 使用共享 `:8080`（`private_backend=False`）；**`private_backend=True`（SHPOIB）测例走私池 :180xx，并行窗口内无需 restart 共享栈**；仅共享 READ 写库测例新增 server 路由后须 `./myrm restart` 或 **`./myrm isolate <id> ready --chrome`**。
- **Clarify refresh Chrome E2E**：`tests/e2e/test_clarify_refresh_chrome_e2e.py`（READ×4 SHPOIB：`POST /chats/test/seed-clarify-refresh-fixture?variant=pending|answered|regenerate_sibling|structured_form` → 深链 `/{chat_id}` → `__MYRM_E2E_CHAT__.turnSnapshot` + DOM（`data-clarification-form` / `data-chat-input`）→ `client.reload` 二次断言；无 LLM）。HTTP 覆盖：`tests/api/chats/test_clarify_refresh_seed_fixture.py`（5 项 mock）。产品 hydrate SSOT：`clarificationState.ts` + `stream_finalize._mark_pending_clarification_answered`。
- **Clarify skip LIVE Chrome E2E**：`tests/e2e/test_clarify_skip_chrome_e2e.py`（LIVE×1 SHPOIB：真实 LLM HITL → Skip → agent resume；`E2E_SIGNOFF=1` 时 API fallback 加长 SSE 预算）。日常：`./myrm test -m chrome_e2e tests/e2e/test_clarify_skip_chrome_e2e.py`。**注**：M3 `test_clarify_signoff_api_e2e`（stub LLM 签收腿）已删除（2026-08-11）。
- **RevertFiles Chrome E2E**：`tests/e2e/test_revert_files_chrome_e2e.py`（READ×5：modify undo+diff+confirm；empty toast；large_skip non-revertible toast；reload hydrate undo；session SessionRevertButton）
- **Memory citations Chrome E2E**：`tests/e2e/test_memory_citations_chrome_e2e.py`（READ lane ×2：`/settings/memory` 开「历史会话搜索」；聊天页注入 citations → 「依据/Evidence N」Sheet）。并行 attach 若 mux timeout drift，须 `MYRM_MUX_ALLOW_TIMEOUT_RESTART=1`（见 `chrome-e2e-preflight.sh` attach heal）。
- **Memory A/B Chrome E2E**：`tests/e2e/test_memory_ab_chrome_e2e.py`（READ×1 + NAMESPACE_WRITE×2，`e2e_search_policy("empty")`）：① 卡片入口 + 确认对话框取消（`all_cards_memory_ab_ready_js` 每卡就绪 → `click_subset_memory_ab_js`）；② `_seeded_memory_ab_reports` 预置 latest+older 双报告到 `.myrm/memory_ab_reports/` → Memory A/B tab 双臂矩阵（No/With Memory 行 + Memory Calls 列 + per-arm pass-rate `50%(0)`/`100%(5)`）+ Run History 表 + 点击 View 加载 aged 报告（case message + Current 禁用态）；③ 真实 run：确认 Start → SSE running + header Stop → Stop 清理。**注意**：历史表 pass-rate 单元格渲染为 `50%(0)`（无空格），probe 正则用 `50%\s*\(0\)`；seed 目录需同时写 timestamped JSON + `latest.json`（对齐后端 `run_memory_ab_background`）。
- **Voice memory ACL Chrome E2E**：`tests/e2e/test_voice_memory_acl_chrome_e2e.py`（READ lane ×2：Settings UI 开/关 memory+sessions → `personalSettings` API 断言；**不依赖** Providers Google key；corpus enum / tool-exec flags 见 `test_voice_memory_acl_api_integration.py`）。
- **Skill marketplace LIVE Chrome E2E**：`tests/e2e/test_skill_marketplace_live_agent_chrome_e2e.py`（LIVE×1 SHPOIB：`skill_market_tool` agent-stream 真实 LLM 断言；UI toggle 见 READ gate；见 `scripts/dev/CHROME_MCP_E2E.md`）
- **Empty file_write Chrome E2E**：`tests/e2e/test_file_write_empty_chrome_e2e.py`（READ×2 SHPOIB：seed mutation fixture → FileMutationWarning + reload 持久；LIVE×1：`agnes-2.0-flash` 真实 tool call；见 `scripts/dev/CHROME_MCP_E2E.md`）
- **Background Tasks Panel Chrome E2E**：`tests/e2e/test_background_tasks_panel_chrome_e2e.py`（READ×5 SHPOIB：panel 列表、failed/running seed、UI cancel、vault log drawer、success finish toast；见 `scripts/dev/CHROME_MCP_E2E.md` §Background Shell）
- **Background shell LIVE Chrome E2E**：`tests/e2e/test_background_shell_live_agent_chrome_e2e.py`（LIVE×1 SHPOIB：自然语言 prompt + agent-stream spawn；HITL 时 `decisions[]` approve；见 `BUGFIX_LOG.md` BUG-DG-2026-07-23-010）
- **UECD EvictedOutputDrawer Chrome E2E**：`tests/e2e/test_evicted_live_terminal_chrome_e2e.py`（READ×1 SHPOIB：`seed-evicted-live-terminal-fixture?variant=full|expired` → LiveTerminal 截断预览 → View Full Output → Drawer 全文/过期；共享 `tests/support/evicted_drawer_selectors.py` 统一选择器与分页参数探针）。**CI anti-mux**：同一 SHPOIB + **单 `open_mcp_page`**，场景间 `client.navigate` 切 chat；**禁止**拆成 2 测例各开新 tab（并行 E2E 下第二次 `new_page` 易 30s timeout；pytest rerun 不采纳）。HTTP/API 覆盖见 `test_evicted_web_fetch_spill.py`、`test_evicted_background_spill.py`、`test_evicted_uecd_live_api_integration.py`
- **失败 bash 双 evicted Drawer Chrome E2E**：`tests/e2e/test_bash_failure_dual_evicted_drawer_chrome_e2e.py`（SHARED+NAMESPACE_WRITE×1：`variant=bash_failure` seed 一个失败 bash step 同时 evict stdout+stderr → LiveTerminal 双 "view full output" 入口 → `EvictedOutputDrawer` 分别读回两文件；共享 `ensure_chat_route` + `evicted_drawer_selectors.py`）
- **Chrome E2E 共享路由/heal helpers**：`tests/support/chrome_mcp_e2e.py` 提供 `ensure_chat_route`（复用 warm shell 时强制导航到目标 chat 路由并校验 React hydration，`errorOverlay`/`ChunkLoadError` 下 cache-bypass reload 自愈）、`wait_for_state`（含 errorOverlay 检测的 overlay-heal 阶段）、`warm_ui_route`（turbopack 预编译）。凡 `open_mcp_page` 后直接进入 chat 页的 E2E 均经 `ensure_chat_route`，禁止绕过
- **UECD LIVE fast+deep Chrome E2E**：`tests/e2e/test_fast_deep_search_evicted_read_chrome_e2e.py`（LIVE×1 SHPOIB：真实 MiniMax + fast/deep + Wikipedia `web_fetch_tool` spill → `file_read_tool`；`preserveActionMode` + progress **UI 优先 / API 自愈**（Chrome CDP flake 时 `_api_deep_search_progress` 不断言中断））
- **UECD LIVE bash foreground Chrome E2E**：`tests/e2e/test_bash_foreground_evicted_live_chrome_e2e.py`（LIVE×1 SHPOIB：yolo code_execute agent → 前台 `bash_code_execute_tool` 大输出 spill → GET `/files/evicted` + LiveTerminal Drawer；**无 enrich 端点**，断言真实 `tool_call_id` 绑定 reload 路径）
- **Subagent Dashboard Chrome E2E**：`tests/e2e/test_subagent_dashboard_chrome_e2e.py`（LIVE lane ×6：`subagent-dashboard-e2e-prepare.mjs` delegate → Dashboard cancel / pause toggle / token+model / budget used-limit / canvas 拓扑渲染+点击节点定位回树 / fission 拓扑经 store bridge 注入后合并渲染；`open_mcp_page(..., timeout_ms=MAX_PAGE_TIMEOUT_MS)`）
- **Subagent rebind 单测**：`tests/services/agent/test_subagent_rebind_event.py`（`AgentService.update_agent` 变更 `subagent_ids` → `SUBAGENT_REBIND_REQUIRED`）
- **Citation seed 集成单测**：`tests/api/chats/test_citation_seed_integration.py`（seed → GET messages 断言 `citedMemoryIds`；默认 CI 套件执行，不依赖 Chrome）
- **Prior chat recall SSOT 集成单测**：`tests/api/chats/test_prior_chat_recall_integration.py`（seed-prior-chat-fixture → GET `/recall/search` → mention inject；默认 CI，不依赖 Chrome）
- **A2UI Surface Gate Chrome E2E**：`tests/e2e/test_render_ui_surface_gate_chrome_e2e.py`（READ×2：Settings hint + `client_surface=web|tauri` + `__TAURI__`→`tauri`；submit+capture 3× mux 重试、`timeout=600`、`open_mcp_page timeout_ms=120_000`；LIVE inline 见 `test_render_ui_inline_card_chrome_e2e.py`；LIVE 按钮点击 → `ui_action` 见 `test_render_ui_inline_interaction_chrome_e2e.py`；LIVE `update_ui_data` 增量刷新 + **reload DB 持久**见 `test_render_ui_update_data_chrome_e2e.py`）
- **A2UI surface_unavailable 单测**：`tests/services/agent/stream_session/test_entitlement_gap_preflight.py`（IM + render_ui ON + UI 意图 → `reason=surface_unavailable`；Web 可挂载 → None；dedup）；`tests/core/channel_bridge/test_stream_events.py`（`capability_gap` surface_unavailable + web_search config gap → ProgressUpdate）；frontend `gapEvents.test.ts`（info-only toast，无 enable/resend）；`tests/api/agent/test_capability_gap_integration.py`（discover miss 不 emit gap；web preflight render_ui ON → 无 gap）
- **web_search 未配置 gap 单测/集成**：`test_entitlement_gap_preflight.py`（`build_web_search_config_gap_sse_event` unit）；`test_stream_chunks_web_search_preflight.py`（config gap 独立于 entitlement preflight text / resume 边界）；`tests/api/agent/test_capability_gap_integration.py::test_agent_stream_emits_web_search_config_gap_sse`（agent-stream preflight SSE：`reason=not_configured` + `settings_path=/settings/search`）；`tests/api/agent/test_capability_gap_integration.py::test_migration_readiness_live_resolve_emits_gap_after_db_seed`（live DB seed + resolve migration readiness → `tool_id=migration_import` + `settings_path=/settings/mcp`）；`tests/core/channel_bridge/test_stream_events.py`（IM web_search gap + empty display_message fallback）；frontend `gapEvents.test.ts` + `webSearchConfigGap.test.ts`（`not_configured|unreachable` → i18n CTA / local 一键启用）
- **web_search config-gap Chrome E2E**：`tests/e2e/test_web_search_config_gap_chrome_e2e.py`（LIVE×1 browser send+poll toast + READ×1 fast client guard；Dual-Plane：禁止 body 内 httpx agent-stream；`__MYRM_E2E_DIRECT_SSE__=false`；CI static：`scripts/dev/tests/test_gap_toast_e2e_contract_static.py`）
- **OpenAPI fail-loud Chrome E2E**：`tests/e2e/test_openapi_fail_loud_chrome_e2e.py`（LIVE×2 SHPOIB：`openapi_load_failed` · `openapi_direct_budget_exceeded`；`tests/support/chrome_openapi_fail_loud_e2e.py` bridge JS；agent 模式 + `?agentId=` 绑定；断言 chat `metadata.error_type` 或 `processing_failed` progressStep）
- **migration readiness gap Chrome E2E**：`tests/e2e/test_migration_readiness_gap_chrome_e2e.py`（LIVE×3 SHPOIB 独立节点：`test_*_mcp_warning` · `test_*_provider_critical` · `test_*_diagnostic_critical`；R139 拆测例 · signoff 逐 leg；Verification：`test_capability_gap_integration.py` + live seed 三 variant）
- **MCP reload confirm Chrome E2E**：`tests/e2e/test_mcp_reload_confirm_chrome_e2e.py`（READ×1 SHPOIB 单会话：toggle · delete · import · add/save → `MCPReloadConfirmDialog`；见 `CHROME_MCP_E2E.md` §MCP reload confirm）
- **A2UI 跨轮 DB patch 单测**：`tests/services/chat/test_ui_artifact_patch.py`（双 turn seed → `patch_ui_artifact_data_by_surface_id` → GET messages 断言 merged binding；collector 跨轮队列；finalize 接线）
- `tests/integration/test_render_ui_sse_wiring.py`：render_ui 确定性集成（20 场景：run_bind、fail-closed、data_update、collector 链、幂等）
- `tests/integration/test_ui_artifact_cross_turn_db_integration.py`：跨轮 `data_update` collector 队列 → 真实 SQLite patch → GET messages 断言 merged binding（无 mock 持久化路径）
- 并行（内存充足时）：`PYTEST_XDIST_WORKERS=4 scripts/dev/run_tests_low_memory.sh`；避免 `-n auto`（多 worker RSS 叠加，`-n auto` 在 8 核上可达数 GB）
- 定位高内存文件：`uv run python scripts/dev/profile_test_memory.py tests/api/agent --top 20`
- WebUI E2E：MCP **chrome-devtools** + Myrm E2E Chrome `:9333`（`./myrm ready --chrome`）；marker **`chrome_e2e`**（`lane=READ|LIVE_AGENT`）；禁止 `@playwright/test`。正式入口 **`./myrm test -m chrome_e2e`**；`tests/e2e/test_*_chrome_e2e.py`（含 Goal、execution_cache、edge_tts、parallel_tabs READ lane、`test_channel_routing_general_only_chrome_e2e` General-only 签收、`test_push_approval_deeplink_chrome_e2e` 等）；READ 只读测例不占 LIVE_AGENT cap（`resolve_e2e_session_lane.py`）
- CI 默认套件：`scripts/ci/run_default_tests.sh`（`-m 'not e2e and not performance' -n0`，workflow `server-unit-tests.yml`）
- `tests/api/skills/test_drafts_seed_mock.py`：seed-mock HTTP 单测（含 `agent_id` 查询参数，默认套件执行）
- `tests/api/approvals/test_seed_mock.py`：approvals push deeplink seed-mock HTTP 单测（local guard + pending list）
- `tests/api/approvals/test_list_pending_growth_filter.py`：`GET /approvals` 排除后台 growth、保留 inline `thread_id` skill_draft
- `tests/api/skills/conftest.py`：minimal app 含 drafts/curator/sync/evolution/skill-growth 路由
- `tests/api/integrations/test_llm_speed_test.py`：`POST /api/v1/integrations/llm/speed-test`
- `tests/api/integrations/test_model_switch_preflight.py`：`POST /api/v1/integrations/llm/model-switch-preflight`（tier 推断 / 显式比例 clamp / prompt_mode 回退 / 多模型）
- `tests/api/notifications/conftest.py`：in-memory DB + loopback auth（通知 API 集成测）
- `tests/api/config/test_readiness_e2e.py`、`tests/api/security/test_generate_policy_e2e.py`：`@pytest.mark.e2e`（默认套件不收集）

## 依赖

- `tests/conftest.py` → `tests/support/test_secrets.py`（**唯一** [T] 加载入口）
- 新 API/集成测优先 `from tests.support.minimal_app import build_minimal_app` + `preset_for_test_path()`，禁止 `from app.main import app`
- `tests/conftest.py` → integration/e2e/lifecycle 路径 autouse `reset_global_browser_pool_for_tests()`（防 Chromium 跨测累积）；sessionfinish 释放 DB engine 与 `_memory_manager_cache`
- `tests/unit/test_system_storage.py`：系统存储 API 单元测（**禁止**在 `tests/unit/` 下创建 `api/` 子包，会与 `tests/api/` 在 `import_mode=importlib` 下冲突）
- `app/startup/env_loader.py` **不**读取 `.env.test`
