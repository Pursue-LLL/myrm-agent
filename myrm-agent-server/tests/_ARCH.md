# tests 模块架构

pytest 测试套件根目录。单元/集成/API/E2E 测试按域分子目录；[T] 业务密钥仅通过结构化 fixture 加载，不进入 server 运行时。

---

## 文件清单

| 路径 | 地位 | 职责 |
|------|------|------|
| `conftest.py` | 核心 | 进程级 `.env` + [T] secrets bootstrap、隔离 workspace、`test_secrets` session fixture、integration/e2e 路径每测后 `reset_global_browser_pool_for_tests()`、session 结束 + `@chrome_e2e` timeout 时 `reset_database_engine()` + `reap_chrome_e2e_session_hygiene()` + `shutdown_cached_memory_managers()`、浏览器进程树 cleanup（`tests/support/browser_process_cleanup`）；`@pytest.mark.chrome_e2e` 三维 profile + **PRIVATE 必填 `private_reason`** + **`global_write_non_namespace`⇒`GLOBAL_WRITE` 语义校验**（与 `scripts/dev/e2e_session/profile.py` 对齐） |
| `support/browser_process_cleanup.py` | 辅助 | pytest 进程树内 browser 自动化子进程 teardown |
| `support/test_browser_process_cleanup.py` | 单元 | browser_process_cleanup 单测（100% 覆盖） |
| `support/test_secrets.py` | 核心 | [T] `.env.test` 结构化加载（`TestSecrets`、`load_test_secrets`、`resolve_test_env`） |
| `support/session_mock_guard.py` | 辅助 | `restore_leaked_session_mocks(mock_get_session, mock_get_session_factory)`：列在 DB 会话 `patch` 之前的上下文守卫，退出时把「补丁生效期间首次 import 而捕获了 mock」的模块全局重绑回真实可调用对象（`patch` 只还原它点名的属性）；`tests/api/{agent,skills,companion,notifications,approvals}/conftest.py` 的会话夹具共用 |
| `support/test_session_mock_guard.py` | 单元 | 守卫回归：补丁期间首次 import 的模块在无守卫时保留 mock（复现后续用例 `no such table: user_configs`），有守卫时重绑为真实函数 |
| `support/fake_secrets.py` | 辅助 | 厂商格式假凭据夹具 SSOT：`stripe_live_key(body)`、`slack_bot_token(body)` 在调用时才拼出厂商前缀，源码里不出现完整 token（GitHub push protection 会拒绝含完整厂商 token 的推送，假值也不例外）；脱敏与泄漏检测类测试共用，由 `architecture/test_no_provider_shaped_secrets_in_tests.py` 守卫 |
| `support/e2e_provider_seed.py` | 辅助 | LIVE E2E provider seed SSOT：`resolve_e2e_llm_endpoints`（OmniRoute `:20128` preflight · fail-fast，无 silent fallback）、`seed_live_e2e_providers` |
| `support/test_e2e_provider_seed.py` | 单元 | `resolve_e2e_llm_endpoints` keep/fallback 契约 |
| `support/e2e_runtime_guard.py` | 辅助 | LIVE E2E runtime guard：immutable-wave lease 校验 · `assert_chrome_attach_health`（`e2e_core/runtime_identity.py` 子进程探针） |
| `support/wb_bench_e2e_helpers.py` | 辅助 | WBBench Chrome E2E 共享探针 SSOT：`SOURCES_READY_JS`、`all_cards_memory_ab_ready_js`（每卡片 Memory A/B 按钮就绪）、`click_subset_memory_ab_js`、`restore_eval_lab_route`、`reset_wb_bench_source` 等 |
| `support/minimal_app.py` | 核心 | `build_minimal_app(preset=...)` 按需挂载 API 路由；禁止测试 import `app.main` |
| `support/public_api_app.py` | 辅助 | `public_api_openapi()`：全量公开 API 的 OpenAPI 路径表，并带回生成期间捕获的 `Duplicate Operation ID` 警告（进程内只生成一次，`tests/architecture` 路由类测试共用；不 import `app.main`） |
| `support/chat_db_fixtures.py` | 辅助 | 内存库夹具插件（经根 `conftest.py` 的 `pytest_plugins` 全局注册，不是 conftest：既是 conftest 又列在 `pytest_plugins` 会被注册两次，指向其目录的运行直接中止）：`db_session`（建全部表并把 `get_session_factory` 绑到它）、`fts_db`（再建 `messages_fts` trigram 虚拟表、三个同步触发器与会话回忆表）；聊天持久化与搜索类测试显式请求 |
| `support/artifact_upsert_fixture.py` | 辅助 | 制品 upsert 自动 mock 插件（autouse，`pytest_plugins` 全局注册）：把 `app.core.artifacts.listener.upsert_processor_artifact` 换成 `AsyncMock`；`core/artifacts` 与 `api/artifacts` 测试共用，对不碰制品管线的测试无副作用 |
| `support/export_world.py` | 辅助 | 专家导出测试的假安装：`ExportWorld`（专家、技能目录与文件、连接器）+ `installed()` 上下文把导出闭包指向它；`SKILL_MD` 最小合法技能；`services/plugins` 与 `api/plugins` 导出测试共用 |
| `support/redaction_review_e2e.py` | 辅助 | 导出脱敏复核 Chrome E2E 的浏览器侧：`ReviewFlow`（对话框标题、进入方式、成功提示措辞）+ `run_review_flow`（zh 与 en 各读一遍发现项的本地化句子且无原始代码、`kinds.` 键名与另一语言句子，再点“导出脱敏版”走真实下载并以对话框关闭为判据，结束恢复 `NEXT_LOCALE`）；专家导出、批量导出与单技能导出三个 E2E 共用（`advance_js` 让打开在选择步骤的向导前进到复核步骤） |
| `e2e/test_expert_export_redaction_kinds_chrome_e2e.py` | E2E | Chrome E2E（PRIVATE+NAMESPACE_WRITE×1）：`/settings/agents` 带密钥与本机路径的智能体，预览 API 返回 `api_token`/`absolute_path` 代码，导出对话框在 zh/en 渲染本地化句子，点导出脱敏版后下载并关闭对话框 |
| `e2e/test_bulk_export_redaction_kinds_chrome_e2e.py` | E2E | Chrome E2E（PRIVATE+NAMESPACE_WRITE×1）：`/settings/agents` 点“批量导出”→下一步，带密钥与本机路径的智能体，批量预览 API 返回 `api_token`/`absolute_path` 代码，向导自身按钮/标题与复核面板在 zh/en 均本地化，点导出脱敏版后下载并关闭对话框 |
| `e2e/test_featured_expert_lucide_icons_chrome_e2e.py` | E2E | Chrome E2E（PRIVATE+NAMESPACE_WRITE×1）：空聊天首页精选专家芯片（`empty-chat-featured-chips`）按模板 API 的 `lucide:<name>` 逐个懒加载图标；每个芯片须为已解析的具名 svg（非 Bot/Users 占位），且不同图标几何互异 |
| `e2e/test_skill_export_redaction_kinds_chrome_e2e.py` | E2E | Chrome E2E（PRIVATE+NAMESPACE_WRITE×1）：经 `.zip` 上传装一个带密钥与本机路径的技能，`/settings/skills` 已安装列表搜索 → 详情抽屉 → 导出，对话框在 zh/en 渲染本地化句子，点导出脱敏版后下载并关闭对话框；结束卸载该技能 |
| `support/test_chrome_bridge_diagnostics.py` | 单元 | `wait_for_react_e2e_bridge` 超时诊断：快照辅助返回页面 readyState/脚本加载/未捕获错误，自身异常不覆盖原始超时，超时信息携带 `diagnostics=` 以区分「未 hydrate」与「脚本未加载完」 |
| `e2e/test_telemetry_posture_chrome_e2e.py` | E2E | Chrome E2E：真实 Chrome 浏览器 Developer 设置页面 OpenTelemetry Posture 遥测态势卡片、协议/端点/特性渲染与刷新端到端测试 |
| `api/system/test_shutdown.py` | 单元 | 系统三段式优雅停机、会话排空与 WAL TRUNCATE 强制刷盘集成测试 |
| `api/memory/test_evidence_playback_api.py` | 单元 | 记忆证据链溯源、上下文切片回放与凭据脱敏 API 集成测试 |
| `api/memory/test_command_center_graph_api.py` | 单元 | 记忆指挥中心知识图谱双视图（Hub 聚合排序、孤岛三态与连通度度数）API 单元与契约测试 |
| `api/memory/test_pending_api.py` | 单元 | 待审批记忆 HTTP 面（`/memory/pending`）：列表、单条/批量批准与拒绝（含审批者改写文本透传、不可编辑提案 400、内部 ValueError 仍为 500），记录缺失 404 与服务端失败 500 的错误映射 |
| `api/memory/test_command_center_actions.py` | 单元 | 记忆指挥中心治理动作分发器：待审批批准/拒绝/编辑、共享提案动作、冲突仲裁委托，以及纠正/置顶/遗忘等通用动作 |
| `ai_agents/general_agent/test_correction_pending_roundtrip.py` | 集成 | 隐式纠正生产者 → 真实 SQLite 审批队列 → `approve` 往返：纠正提案保留目标并应用审批者改写，遗忘提案批准即归档（非硬删除），不可编辑提案拒绝改写且保持待审 |
| `channels/routing/test_memory_pending_command.py` | 单元 | IM `/memory` 待审批：列表对纠正/遗忘提案附目标记忆摘要（含多语言），普通新增不附加；目标已变化的提案以用户语言提示，`approve all` 汇报未通过数量 |
| `channels/routing/test_draft_review_stream_hold.py` | 单元 | `draft_review` 待审回复：生成期间正文不流式写入聊天占位消息（审批续跑回合同样），普通回复照常流式；是否扣留只取决于话题，与回合类型无关 |
| `channels/routing/test_action_button_approval.py` | 单元 | IM 按钮审批：内容解析校验、群聊请求者/共同审批人授权（私聊免检）、批准/拒绝续跑与重复点击幂等、原消息状态行按点击者语言编辑、无运行任务时 SSE 回退；扣留回复（`outbound_draft`）仅 owner 可裁决——非 owner 被拒并指引、运行中的任务不放行他人、工具审批不受 owner 校验，owner 卡片的每个按钮处理器都认识 |
| `core/notifications/test_approval_card.py` | 单元 | 审批通知卡片：草稿正文预览（截断/附件摘要/自动发送提示/剩余时间）不含内部标识与链接，仅 Telegram 带批准/拒绝按钮、其他渠道提示打开应用，按用户语言渲染 |
| `channels/reliability/test_durable_outbound_poison_isolation.py` | 单元 | 持久化出站队列：带按钮的消息重启后完整读回；无法解码的记录隔离到失败桶，不拖垮其余记录、仅一次性上报永久失败且绝不重发，网关启动不受影响 |
| `api/memory/test_pending_proposal_seed.py` | 单元 | `POST /memory/test/seed-pending-proposal` 契约（local-only 404 · correct/delete 入队 · 目标不存在或非语义记忆 404 · 重复提案 409） |
| `api/agent/test_agent_clone_e2e.py` | 模块 | Agent 克隆 API E2E（自定义名 / 默认「(Copy)」/ 不存在 404 / 提示词与技能随克隆保留、家目录与头像不带）+ 已退役的 JSON 导入导出与工作区文件束路由不再对外提供（404/405 守卫） |
| `integration/test_expert_export_i18n_sync.py` | 模块 | 跨层同步：专家导出的 `Omit` 原因码与 `OmittedKind` 种类须与 6 个 locale 的 `agent.expertExport.omitReason` / `omittedKinds` 键完全一致，避免导出对话框显示原始 key |
| `integration/test_readiness_i18n_sync.py` | 模块 | 跨层同步：`ReadinessCode` 须与 6 个 locale 的 `Agent.readiness.reasons` 键完全一致，`ExportErrorCode`（重试流程码除外）须被 `agent.expertExport.errors` 覆盖，文案均非空，避免新增错误码在界面上静默降级为通用句 |
| `services/plugins/test_export_acceptance.py` | 模块 | 专家导出验收（以官方冻结 schema 与归档字节为判据，不对内部结构做断言）：`plugin.json`/`mcp.json` schema 合规与 `ai.myrm` 独占扩展 · 归档路径安全 · 脱敏只触及秘密（其余字节不变）· 未带出清单对账（含反例）· 导出→导入→再导出定点往返 · 本地导出→云端导入的 stdio 降级 |
| `services/plugins/test_third_party_plugin.py` | 模块 | 第三方真实插件（`fixtures/agent_plugins/third_party/hindsight/`）在平铺与单层包裹两种归档下都能解析并预览：技能与远程连接器不丢，外来 `extensions` 命名空间保持外来 |
| `fixtures/agent_plugins/` | 辅助 | 官方冻结 JSON Schema（`plugin.schema.json` / `mcp.schema.json`）与第三方真实插件夹具（`third_party/hindsight/`，`NOTICE` 记录来源与许可） |
| `integration/test_expert_exchange_integration.py` | 模块 | 专家交换真实栈集成（真实数据库 + 连接器配置库 + 技能安装流水线 + 导出/导入路由 + ZIP，无 mock）：团队（含泄漏密钥、越权策略、远程连接器）导出 → 空的第二套安装导入（子专家重新连线 · 密钥与越权策略不外带 · 连接器默认停用且头部为占位符）；自定义技能（安装 → 导出 → 卸载 → 导入：路径泄漏被脱敏、专家重新指向新装技能）；同机导入默认生成「(imported)」副本且不动原件，选择「替换」时保存可回滚版本并保持用户自己的安全策略 |
| `core/utils/test_error_redaction.py` | 单元 | 全局异常处理与标准 HTTP 异常响应消息自动凭据与路径脱敏测试 |
| `e2e/test_control_ui_error_redaction_flow_e2e.py` | E2E | Task Flow E2E：Control UI 错误脱敏跨渠道测试连通性与 FastAPI 入口/出口全局防护全链路测试 |
| `e2e/test_error_redaction_chrome_e2e.py` | E2E | Chrome E2E：真实 Chrome 浏览器 Control UI Toast 弹窗与设置界面敏感凭据打码防护测试 |
| `e2e/test_mermaid_preview_sanitize_chrome_e2e.py` | E2E | Chrome E2E：真实 Chrome 浏览器 Mermaid 图表严格净化与 XSS 物理阻断端到端测试 |
| `unit/test_conversation_recall_cjk_query.py` | 单元 | 会话召回 CJK 中日韩分词与二元词降级规划测试 |
| `api/mcp/test_mcp_endpoint_e2e.py` | 集成 | /mcp HTTP 端点端到端流水线集成测试（DNS 重绑定/Origin 守卫拦截、原生工具免检与 Token 校验鉴权） |
| `api/memory/test_repo_evidence_api.py` | 契约 | 代码库 Git 事实证据提取 API 端点（分支、脏状态、提交摘要）契约测试 |
| `e2e/test_paginated_table_harvest_flow_e2e.py` | E2E | Universal Task Flow E2E：多页表格翻页抓取、双哨兵防死循环（首行指纹哈希与硬上限）及 UTF-8-SIG CSV/Excel 工件生成与解析全链路测试 |
| `e2e/test_paginated_table_harvest_chrome_e2e.py` | E2E | Chrome E2E：真实浏览器动态多页表格提取与双哨兵（首行指纹哈希/末页置灰按钮）翻页终止自动化测试 |
| `support/feature_flags.py` | 辅助 | `seed_voice_interaction_flags()`，供 `tests/api/voice`、`tests/api/stt` conftest autouse |
| `support/curtain_watcher.py` | 辅助 | 无人值守帷幕单测共享支撑：`make_state` 状态快照（`shell_alive` 模拟壳失联）、`drive` 哨兵退出的 tick 驱动器、`arm_on_demand_unlock`（五条件齐备的锁屏场景，返回代解锁桩）/ `acquire` / `mark_watcher_running` 按需解锁入口、`dead_process_pid` 已退出进程 PID、`record_clear` / `set_locked` / `has_session` / `no_session` 桩、`set_hid_idle` / `AWAY_IDLE_SECONDS` 固定硬件输入空闲读数（在场门禁；真实探针读开发机此刻键鼠，用例须经此固定；`tests/services/locked_use/` 获取门禁、并发、harness 会话接线、watcher 循环、租约分支与会话路径测试共用） |
| `support/verify_api_base.py` | 辅助 | Live 集成测 verify-api 私池 base SSOT（`resolve_verify_api_base()`；epoch 匹配 + `--ensure-backend` seed） |
| `support/theme_marketplace_e2e.py` | 辅助 | Theme marketplace E2E：CP 探活、JWT、official seed、listing 查询 |
| `support/gap_toast_chrome_e2e_contract.py` | 辅助 | Gap Toast E2E Dual-Plane SSOT（Verification=API/integration · Experience=browser send+poll；禁止 chrome_e2e body 内 agent-stream httpx） |
| `support/bash_compressor_e2e.py` | 辅助 | bash compressor live/API E2E 共享 helper（模型 probe、workspace 压缩回放） |
| `support/local_embedding_server.py` | 辅助 | 本地 OpenAI 兼容 embedding 端点（`/v1/embeddings`，确定性 1024 维哈希向量）；产品支持任意自托管 embedding `api_base`，用于外部 embedding 账户配额不可用时打通真实链路（`e2e/test_memory_ab_model_disclosure_chrome_e2e.py` 使用） |
| `support/retrieval_embedding.py` | 辅助 | `configured_retrieval_embedding(api_url)`：为 Chrome E2E 写入 WebUI `retrieval.embeddingConfig`（已配置则沿用；否则用 `.env.test` 的真实 embedding 账户，缺失时回退 `local_embedding_server`），使 `create_memory_manager` 走真实嵌入 |
| `support/e2e_wall_progress.py` | 辅助 | Chrome E2E 墙钟 progress token（R57：仅 touch，不再重置 body 计时） |
| `../../scripts/dev/lib/e2e_core/shared_ui_session.py` | 辅助 | R51-v2 Shared UI Session Contract（marker `e2e_search_policy` · conftest env · bootstrap/`click_new_chat` 四阶段 reset） |
| `support/chrome_memory_settings_e2e.py` | 辅助 | `/settings/memory` Chrome 开关 JS SSOT（memory citations + voice ACL E2E 共用） |
| `support/evicted_drawer_selectors.py` | 辅助 | UECD Drawer Chrome E2E 共享选择器/探针 SSOT（`data-testid` 定位 + `/files/evicted` 分页参数断言 + `drawer_mount_wait_js` 等待 lazy drawer mount） |
| `api/agent/utils.py` | 辅助 | Agent 测试共享工具（模型/搜索配置组装；`hide_sse_heartbeats`（同步 `TestClient`）与 `hide_sse_heartbeats_async`（`httpx.AsyncClient`）响应钩子共用同一状态机，让行解析器看不到 keep-alive 帧；`check_e2e_errors` 环境类错误 skip） |
| `e2e/conftest.py` | 辅助 | E2E ephemeral server fixture（API 级 e2e，不启动前端） |
| `e2e/test_skill_hooks_live_chrome_e2e.py` | 模块 | 技能 command hooks 治理真实 WebUI 对话回合 Chrome LIVE E2E（PRIVATE+LIVE，六场景各自独立 `file::test` 运行以守 600s BODY 墙钟：斜杠面板选技能 chip 发送 → `[use skill]` 线上消息 → 真实模型调 bash → SessionStart/PreToolUse/PostToolUse/SessionEnd 钩子写出可观测文件；被命令门禁拒绝的第三方钩子不运行；`fail_closed` 钩子拦下工具调用；HITL 审批卡批准后恢复回合重新激活钩子；带附件（content blocks）与超长消息落盘引用两种载体仍调用技能；不带技能的后续消息不复活钩子） |
| `support/chrome_skill_hooks_live_e2e.py` | 辅助 | 技能钩子 LIVE E2E 的后端装配：经产品 API 采纳带 `hooks:` 的本地技能，`setup_skill_chat` / `SkillChat`（providers + 持有该技能的智能体 + 空聊天），`audit_hooks()` / `fail_closed_hooks()` 生成写可观测文件的 SKILL.md `hooks:` 块 |
| `support/chrome_skill_hooks_composer.py` | 辅助 | 技能钩子 Chrome E2E 的浏览器侧：真实 composer 里斜杠选技能 chip、可选经真实 file input 挂附件、输入并点真实发送键，页面对已发送回合的自述（`describe_page`），转录区 chip 渲染探针 |
| `support/chrome_skill_hooks_approval.py` | 辅助 | 技能钩子 Chrome E2E 的 HITL 审批卡：等待审批卡出现、点真实 Approve 键，`approve_cards_until_reply` 逐张批准直到回复落库（模型重试被执行器拒绝的命令会再停一张卡），`describe_unanswered_resume` 给出批准后无回复的失败现场 |
| `support/chrome_skill_hooks_observe.py` | 辅助 | 技能钩子回合留下的证据：等用户消息/助手回复落库、读取钩子写出的文件与后端日志，`assert_no_hook_raised` / `assert_audit_turn_governed` |
| `api/agent/test_sse_heartbeat_filter.py` | 模块 | agent 测试客户端（同步 `TestClient` 与异步 `httpx.AsyncClient`）对行解析器隐藏 SSE keep-alive 帧（帧由真实 `ResilientStreamBuffer` 产出，格式变更在此报红，避免 `data: null` 解析洞在流测试里重开） |
| `core/channel_bridge/test_inbound_skill_invocation.py` | 模块 | 绑定技能的斜杠命令到达 agent 时仍是 `[use skill] ...`：回复上下文、群上下文与投递横幅一律置于标签之后 |
| `core/utils/test_skill_invocation.py` | 单元 | `decorate_behind_skill_tag`：只装饰标签之后的文本，标签始终居首 |
| `lifecycle/test_init_risk_rules.py` | 模块 | 启动风险规则初始化对真实 SQLite：先读后写遇并发提交（SQLITE_BUSY_SNAPSHOT，`busy_timeout` 不覆盖）时在新事务上重试，检测引擎仍拿到规则 |
| `integration/test_repo_call_graph_integration.py` | 模块 | 代码调用图谱与改动影响面分析集成任务流测试（多语言代码库索引、正反向拓扑遍历、受影响测试套件触达、增量重索引一致性） |
| `e2e/test_migration_readiness_gap_chrome_e2e.py` | 模块 | migration post-import readiness gap（LIVE×3 SHPOIB：`mcp_warning` · `provider_critical` · `diagnostic_critical` 各独立 `::test_*` · R139 禁 batch） |
| `e2e/test_mem0_import_review_chrome_e2e.py` | 模块 | mem0 export 真实 UI 导入 Chrome E2E（SHARED+NAMESPACE_WRITE×1：/settings/memory file picker 上传 mem0 `memories` JSON → 前端 POST dry-run → server auto-detect=mem0 → review dialog 渲染翻译后 `sources.mem0`（C1 无 raw key 泄漏）+ `memories` 映射桶；**停在 confirm 前不写真实记忆**，写路径由 unit/API 覆盖） |
| `e2e/test_mcp_reload_confirm_chrome_e2e.py` | 模块 | MCP Settings reload 确认 Chrome E2E（READ×1 SHPOIB 单会话：toggle cancel/confirm · delete · import JSON · add/save → `GET /config/mcpServers` 断言） |
| `e2e/test_muse_spark_responses_wire_chrome_e2e.py` | 模块 | muse-spark Responses wire Chrome LIVE×1 SHPOIB（PRIVATE+LIVE：`muse-spark-1.2-contributor` + OpenCode Go BYOK API seed → agent 关 workflow · 仅 `web_search` → Turn1 `TOOL_LOOP_OK` → Turn2 reasoning blob replay `TURN2_OK`；前置 `~/.cursor-byok/opencode-go.json`；**shared**：`./myrm ready --attach --chrome` → `./myrm test -m chrome_e2e -n0 ::test_muse_spark_responses_wire_two_turn_tool_loop`；**争用隔离**：`./myrm isolate muse-spark-wire restart --chrome` + `MYRM_E2E_ISOLATED_RUNTIME_ID=muse-spark-wire MYRM_E2E_FULL_ISOLATED=1` 同上 test） |
| `e2e/test_kanban_chrome_e2e.py` | 模块 | Kanban Chrome MCP E2E（READ×14：看板渲染 + source_chat 深链过滤 + Drawer 附件 + Chat 成功卡片→看板 + stats bar running N/M + ready 排队 badge ±（占满显示/未满不显示）+ 多 ready 同时排队 badge + 真实执行排队释放闭环 + 队列按序释放 badge 递减 + model_override UI 建卡 / 抽屉徽章编辑清除 + 技能选择器 UI 建卡（真实技能集，picker 搜索选择 → extra_skill_ids 持久化）+ 抽屉技能编辑保存（chips → 编辑态 → picker 增选 → 保存 → 退出编辑态且持久化）） |
| `e2e/test_wiki_citation_chrome_e2e.py` | 模块 | Wiki citation Chrome MCP E2E（READ×2：citation reload + `/settings/wiki?agentId=`） |
| `e2e/test_wiki_dedup_chrome_e2e.py` | 模块 | Wiki corpus dedup Chrome MCP E2E（SHARED+READ×1：seed-after-warm → duplicateReview exact group panel） |
| `e2e/test_wiki_compound_chrome_e2e.py` | 模块 | Wiki chat compound Chrome E2E（SHARED+READ×3：`POST /chats/` seed Q&A → `POST /wiki/compound` happy+409 dedup · incognito 403 · user role 422） |
| `e2e/test_wiki_health_report_chrome_e2e.py` | 模块 | Wiki health report Chrome E2E（SHARED+READ×1：API structural health + seed provenance gap → 单 tab Overview `[data-testid=wiki-health-section]` + stats badge；shell 探针 `wiki-settings-shell`；transport retry 同 dedup） |
| `e2e/test_clarify_refresh_chrome_e2e.py` | 模块 | Clarify refresh Chrome MCP E2E（READ×4 SHPOIB：`seed-clarify-refresh-fixture` pending/answered/regenerate_sibling/structured_form → F5 hydrate 断言 composer 态） |
| `e2e/test_clarify_skip_chrome_e2e.py` | 模块 | Clarify skip LIVE×1 SHPOIB：真实 LLM HITL → Skip → resume（`E2E_SIGNOFF=1` API fallback）；M3 stub 签收腿已删 |
| `e2e/test_connect_wizard_plugin_zip_chrome_e2e.py` | 模块 | Connect Wizard Agent Plugins bundle zip 下载 Chrome MCP E2E（SHARED+NAMESPACE_WRITE×1：Memory → Connect → 生成 bundle → 「Download All (.zip)」→ 捕获 `HTMLAnchorElement.click` 断言 zip 文件名 `<agent>.zip`；`execution_mode=SHARED` 因功能为纯前端 zip 打包，依赖 shared epoch 后端 `generateAgentPluginBundle`） |
| `e2e/test_project_turn_lock_chrome_e2e.py` | 模块 | Shared-project 并发锁等待 Chrome E2E（LIVE×1 SHPOIB：`POST /projects/test/seed-turn-lock`（`hold_ms=0` 持有到显式 `POST /projects/test/release-turn-lock` 释放，免疫 attach 延迟）→ `GET /projects/test/turn-lock-status` 确定性守卫（send 前断言锁确实持有，杜绝 happy-path 假阳性）→ 真实 UI turn → `waiting_for_turn` progress step 显示 → 锁释放 `waiting_for_turn_clear` step 移除 → assistant OK 完成；另有等待期间真实用户取消场景：`stopMessage` 取消 → step 同步清除 → 二次发送仍等待（锁未被误释放、gateway 预占已清理）→ seed 释放后正常完成） |
| `e2e/test_inspector_panel_lifecycle_chrome_e2e.py` | 模块 | Inspector 面板生命周期 Chrome MCP E2E（PRIVATE+LIVE×1）：真实前端 SSE handler 驱动 turn-engagement 状态机——`simulateBrowserToolStart`/`simulateBrowserViewUpdate` 注入 TOOL_START/BROWSER_VIEW_UPDATE 生产 handler（engage turn + open 面板 + `sourceChatId` 绑定）→ 真实 LLM turn MESSAGE_END 触发 `releaseTurnInspectorControls(chatId)` 回收本 turn viewData → 手动打开的 desktop 面板（ensureComputerUseReady 无 engagement）在 turn 结束时不误关，验证多 pane 互不干扰 |
| `api/chats/test_clarify_refresh_seed_fixture.py` | 模块 | clarify refresh seed HTTP 单测（local-only gate + 三 variant mock 持久化） |
| `e2e/test_integration_catalog_loopback_guard_chrome_e2e.py` | 模块 | Integration Catalog loopback guard Chrome MCP E2E（READ×3：live API `deployment_scope` 与 `/integrations/mcp/probe` 语义断言 + 阻断链 `scan/verify` 不扇出 + `recommendedMode` 在 `connection_refused` / `probe_failed_unknown` 重试后自动续接连接） |
| `e2e/test_memory_citations_chrome_e2e.py` | 模块 | Memory Chrome MCP E2E（READ×2：设置「历史会话搜索」开关；统一「依据/Evidence N」Sheet） |
| `e2e/test_web_search_inline_citations_chrome_e2e.py` | 模块 | Web search 行内引用 Chrome READ E2E（inject sources+【N】/[N] → LinkPopover badge + 代码块 mask + 「依据 N」） |
| `e2e/test_web_search_citations_live_chrome_e2e.py` | 模块 | Web search 引用 LIVE Chrome E2E×2（PRIVATE+SHPOIB：General Agent `web_search` + Fast Search `actionMode=fast` → sources SSE → Evidence + 可点行内 badge；`seed_live_e2e_providers`） |
| `api/agent/test_citation_general_agent_web_search_e2e.py` | 模块 | General Agent web_search 引用 API E2E（`@pytest.mark.e2e`：agent-stream sources 事件 + 【1】/CITE_OK 断言；`enabledBuiltinTools=[web_search]`） |
| `e2e/test_voice_memory_acl_chrome_e2e.py` | 模块 | Voice memory ACL Chrome MCP E2E（READ×2：`/settings/memory` UI 开/关「历史会话搜索」→ `GET /config/personalSettings` 断言；token corpus 由 HTTP 集成测覆盖） |
| `api/voice/test_voice_memory_context.py` | 模块 | Voice memory ACL SSOT 单元 + policy 矩阵 |
| `api/voice/test_voice_memory_acl_api_integration.py` | 模块 | Voice memory ACL HTTP 集成（realtime/gemini token enum + tool-exec flags，ACL 路径 unmocked） |
| `e2e/test_background_tasks_panel_chrome_e2e.py` | 模块 | Background Tasks Panel Chrome MCP E2E（READ×5 SHPOIB：打开 Panel、failed/running seed、UI cancel、`vault_log` drawer、`success` finish toast；`data-testid=background-task-cancel` / `background-task-view-vault-log`） |
| `e2e/test_cron_observability_chrome_e2e.py` | 模块 | Cron observability Chrome MCP E2E（READ×1 anti-mux 单会话：settings/cron banner 隐藏 · SchedulerHealthBadge · Custom create preview · Chat banner 随 health 显隐；须 `-m chrome_e2e`） |
| `e2e/test_background_shell_live_agent_chrome_e2e.py` | 模块 | Background shell LIVE×1 SHPOIB（`lane=LIVE_AGENT`，默认 `private_backend=True`）：自然语言 user turn + `bash_code_execute_tool` stream（HITL 时 `decisions[]` approve resume）；5× stream retry + REST 20s probe + 3× chat retry；`finally` teardown cancel |
| `e2e/test_skill_marketplace_live_agent_chrome_e2e.py` | 模块 | Skill marketplace LIVE×1 SHPOIB：`skill_market_tool` 经 agent-stream 真实 LLM 调用断言；UI toggle 见 READ `test_skill_mount_builtin_gate_chrome_e2e` |
| `e2e/test_revert_files_live_agent_chrome_e2e.py` | 模块 | RevertFiles LIVE×1 SHPOIB：真实 LLM 回合 `file_edit_tool` 修改 workspace 文件 → SnapshotObserver 记录快照 → 页面刷新 hydrate `requestMessageId`（`r-` 前缀）→ probe 与 `RevertFiles` 同一解析（`requestMessageId \|\| messageId`）→ 真实 UI 回退并断言文件恢复 seed 内容 |
| `api/agent/test_memory_conversation_search_e2e.py` | 模块 | Memory + sessions opt-in API 集成（真实 LLM agent-stream；8 场景：opt-in/incognito/memory-off/多轮/passphrase） |
| `ai_agents/test_custom_agent_factory.py` | 模块 | Custom/Ephemeral 子 Agent `memory_search_tool` rebind + factory build 路径（38 项；`--cov-fail-under=90` on factory） |
| `ai_agents/test_conversation_search_opt_in_integration.py` | 模块 | conversation-search opt-in 与 tool_setup 绑定集成 |
| `e2e/test_theme_marketplace_gallery_chrome_e2e.py` | 模块 | Theme Studio Gallery 免费安装 Chrome MCP smoke（READ×1：CP seed→acquire→download→install-from-marketplace） |
| `e2e/test_subagent_dashboard_chrome_e2e.py` | 模块 | Subagent Dashboard Chrome MCP E2E（LIVE×6：cancel running、delegation pause toggle、SSE token/model 展示、budget used/limit、canvas 拓扑渲染 + 点击定位回树、fission 拓扑合并渲染） |
| `e2e/test_subagent_interrupt_live_e2e.py` | 模块 | Subagent bash HITL interrupt LIVE×4（PRIVATE+HTTP SHPOIB：`MYRM_E2E_API_ONLY` + `MYRM_E2E_HITL_MULTI_ROUND=1` BODY cap 900s；`builtin-general` + LITE 直连 model（非 auto router）+ `securityPreset:hitl` + `bash_worker` JIT；round wall 600s；`@e2e_search_policy("empty")`；approve/allow-always/edit/reject 四路径；`tests/support/subagent_hitl_stream.py`） |
| `e2e/test_subagent_approval_flow_chrome_e2e.py` | 模块 | Subagent bash HITL approval Chrome LIVE×1（`builtin-general` + `bash_worker`；API kickoff `run_until_subagent_approval` → WebUI `recoverHitlStream` + **多轮** PolymorphicApprovalCard Approve（`subagent_approval` 后再点 bash `tool_approval`）→ `/subagents` status=completed；`turnSnapshot` 在 HTTP kickoff 路径可能空白，以 API 轮询为准；`MYRM_E2E_HITL_MULTI_ROUND=1`；`@e2e_search_policy("empty")`） |
| `support/subagent_hitl_stream.py` | 辅助 | 共享 HTTP agent-stream helper（subagent HITL kickoff / interrupt flow；stderr `SUBAGENT_HITL_STREAM` 进度） |
| `support/hitl_live_e2e.py` | 辅助 | LIVE HITL pin + hitl-probe 校验（YOLO off · approval timeout ≥300s） |
| `api/eval/test_memory_ab_live_integration.py` | 模块 | Memory A/B Live 集成（`@pytest.mark.e2e`）：真实 embedding probe + WBBench office 真实下载构建 + 双臂真实 LLM 执行 + `memory_tool_calls` 报告 + 临时记忆卷清理（关键路径禁 mock；执行 case 数受限） |
| `e2e/test_memory_ab_chrome_e2e.py` | 模块 | Memory A/B Chrome E2E（READ×1 + NAMESPACE_WRITE×2）：WBBench 卡片 Memory A/B 入口 + 确认对话框取消（READ）；预置双报告渲染双臂矩阵 + Run History 表（per-arm pass-rate + `memory_tool_calls`）+ 点击历史 View 加载（NAMESPACE_WRITE）；真实 run 启动（SSE running + header Stop）+ Stop abort 清理（NAMESPACE_WRITE，run 前置配本地 embedding 端点并还原 retrieval 配置，不依赖外部 embedding 账户配额） |
| `e2e/test_memory_ab_model_disclosure_chrome_e2e.py` | 模块 | Memory A/B 模型披露 Chrome E2E（PRIVATE+LIVE）：config API 配置 providers + 本地 embedding 端点 → Eval Lab Sources 卡片 limit=1 真实 Memory A/B 双臂 run → 历史表断言 Agent Model / Judge Model 列披露（本地 embedding 端点为产品支持的自托管用法，避免外部账户配额依赖） |
| `e2e/test_memory_pending_proposal_review_chrome_e2e.py` | 模块 | 隐式纠正提案审阅 Chrome E2E（PRIVATE+NAMESPACE_WRITE×1：真实记忆 API 建目标 → `submit_pending` 入队 CORRECT/DELETE → `/settings/memory` 待审批卡片展示「将纠正已有记忆 / 将已有记忆移入回收站 + 目标」→ UI 点「接受」→ 卡片离队，生成 `correction_of` 关联的纠正记忆 / 旧记忆进入回收站（可恢复）；失败时输出卡片可见性与 `/memory` 请求状态取证） |
| `services/agent/test_subagent_rebind_event.py` | 模块 | `SUBAGENT_REBIND_REQUIRED` 事件：`subagent_ids` 变更时 publish、同值/非绑定字段不 emit |
| `services/agent/readiness/test_readiness_mcp_secrets.py` | 模块 | readiness mcp 维度密钥预检（`_check_mcp` 六分支：requiredSecrets 全齐不报 / 缺失报 / headers `{{secret:KEY}}` 引用报 / disabled 跳过 / 无声明不查 / vault 异常跳过）+ org MCP 合并单测 |
| `api/internal/test_org_mcp_sync_integration.py` | 模块 | org MCP 真实 DB 全链路集成：CP `POST /api/admin/org-mcp-sync` → ConfigService 加密落库 → `load_user_config_entry` 解密加载 → `merge_org_mcp_configs` 合并（scope=org）→ readiness `_check_mcp` 识别绑定 org server（关键路径无 mock） |
| `api/internal/test_agent_audit.py` | 模块 | Agent audit 内部 API：真实 JSONL 全链路（真实 harness FileEventLogBackend 读事件 → deny 决策计数 BLOCK/DENY/REDACT/LEAK → `security_deny_total` 聚合）、`hours` 时间窗过滤旧事件、非法 CP token 拒绝（关键路径禁 mock） |
| `services/agent/backends/test_secret_backend_list_keys.py` | 模块 | `DatabaseSecretBackend.list_secret_keys` 真实 DB（保存后键名列表、未知 agent 空列表；FK 预置 agent + 测后清理） |
| `services/skills/test_permission_service.py` | 模块 | 技能权限 service 单测：async/sync checker、per-session 缓存命中/未命中、缓存清理、DB 脏值跳过（覆盖率 100%） |
| `services/skills/test_permission_gate_integration.py` | 模块 | 技能权限 gate 装配链路集成（真实 checker + SkillBoundaryProvider + GuardrailMiddleware；授权/拒绝/无技能/MCP 绕过/网络工具） |
| `services/skills/test_permission_gate_real_db_integration.py` | 模块 | 技能权限 gate 真实 DB 全链路集成（无 mock）：grant 行写入 SQLite → 缓存读取 → gate 决策；revoke 清缓存实时失效；脏值跳过 |
| `services/skills/test_mutation_batch_stream.py` | 模块 | 批次提交事件契约：事件形状、关联到最新未关联批次的 skill_manage 步骤（连续批次各归其步、命名空间工具名、失败/他工具步骤跳过、无步骤时不建步骤、id 小写化、畸形 id 与他工具事件忽略） |
| `services/skills/test_mutation_batch_hook_announce.py` | 模块 | `ServerSkillManageBatchHook` 提交后才广播批次 id（顺序 commit→emit）、快照未解析时不广播、进度通道抛错不影响已提交批次（记 WARNING）、无通道时照常提交 |
| `integration/skills/` | 模块 | 技能管道集成测试目录：prebuilt 同步契约（`test_prebuilt_skills_e2e.py`——含 `test_tdd_skill_v120_contract_guard` 断言 TDD v1.2.0 契约字段/正文标题/边界护栏措辞/references 段落 + batch import/curator/discovery 等 7 文件） + `test_skill_rescan_supply_chain_integration.py`（供应链重扫全链路集成：真实磁盘包提取、OSV缓存/已知通告、AdvisoryAck 确认治理、自动隔离下架与事件总线广播） |
| `api/chats/test_citation_seed_fixture.py` | 模块 | citation fixture seed HTTP 单测（local-only，`/chats/test/seed-citation-fixture`） |
| `api/chats/test_deliverable_seed_fixture.py` | 模块 | deliverable link fixture seed HTTP 单测（`/chats/test/seed-deliverable-link-fixture`） |
| `e2e/test_deliverable_bundle_board_chrome_e2e.py` | 模块 | TaskDeliverableBundle 看板 Chrome MCP E2E（seed 完成态 Goal + 3 项不同类目工件 → 展开 GoalStatusCard → 验证聚合看板渲染、类目 Tab 过滤、多选动态导出按钮） |
| `core/wire/test_registry.py` | 模块 | OpenCode wire 路由 registry + enrich defaults（muse-spark `include` / reasoning effort）单测 |
| `services/copilot/test_advisor_service.py` | 模块 | Session Advisor Tier-0/Tier-1 单测（`load_llm_from_model_config` wire-aware 路径 mock 契约） |
| `api/companion/test_companion_react.py` | 模块 | Companion `/react` wire-aware LLM 单测（lite/default 模型 + `load_llm_from_model_config` mock 契约） |
| `core/artifacts/test_processor_short_file_id.py` | 模块 | LocalArtifactProcessor 透传 `short_file_id` → artifacts SSE JSON |
| `core/artifacts/test_processor_oversized_shareable.py` | 模块 | Local 超大可分享 reference-only persist + processor→deliverable 集成（sandboxes 路径、一次 resolve） |
| `core/artifacts/test_processor_upsert_emit.py` | 模块 | upsert 失败不 emit / 部分 upsert 失败只 emit 成功项 |
| `e2e/test_deliverable_link_chrome_e2e.py` | 模块 | Deliverable inline link Chrome READ E2E（seed → 自然路由 hydrate → `[data-testid=deliverable-reference-link]` → Portal 预览；**禁止 attachToChat**，store/DOM 不同步） |
| `e2e/test_chat_share_chrome_e2e.py` | 模块 | Chat Share Chrome E2E（PRIVATE exclusive_backend）— `test_chat_share_lifecycle_via_ui`：seed chat → WebUI 侧栏 More→Share → 创建分享 → 对话框 live URL + 有效期 → 公开页 HTTP 200 含内容 → 关闭重开 status 重建同一链接 → Revoke → revoked 态 + 公开页 404 → 重建链接 ≠ 复活已撤销链接；`test_chat_share_password_protected_via_ui`：对话框填密码创建 → 公开页 403 密码门 → 错误密码仍 403 → 正确密码（URL query + 表单 POST）放行内容 → 重开显示 passwordProtectedStatus（无 URL，密码不落库不可重建）→ Revoke → 公开页 404；`test_chat_share_real_conversation_via_ui`：**真实 LLM 对话全链路**（McpChatSession 驱动真实输入框，WebUI 已配模型）→ 新对话发消息 → 等待助手回复（真实模型输出）→ 侧栏分享 → 公开页 HTTP 200 且复现真实 user 消息 + 助手回复 → Revoke → 40
| `e2e/test_enterprise_agent_audit_error_state_chrome_e2e.py` | 模块 | Enterprise Agent Audit Chrome E2E（PRIVATE+READ×1 SHPOIB）：打开 `/settings/enterprise` → 点击「审计日志」子 tab → Radix Tabs 完整事件序列切到「Agent 行为」→ 断言 AgentAuditView 挂载（标题 + 组织加载失败 i18n banner 或数据态）；覆盖本地无 CP 时企业审计页的 i18n 错误态渲染与不白屏 |
| `api/wiki/test_wiki_structural_cache_invalidation.py` | 模块 | Wiki vault mutation SSOT：`_after_wiki_vault_mutation` 在 apply/move/repair-publication/delete/repair-types/pending approve 等端点触发或 skip（9 项） |
| `api/wiki/test_maintain_endpoint.py` | 模块 | POST /maintain：默认 structural mode · `?mode=full` · compile-busy 409 |
| `api/wiki/test_wiki_sources_status.py` | 模块 | Wiki sources API：status OAuth 标志位 + PUT config zotero 字段透传/回读断言 + exclude_unset 部分更新保持语义（断链防回归锚点） |
| `api/chats/test_kanban_closure_seed_fixture.py` | 模块 | Kanban closure fixture seed HTTP 单测（`/chats/test/seed-kanban-closure-fixture`） |
| `api/chats/test_kanban_closure_seed_integration.py` | 模块 | Kanban closure seed 真 DB 集成（metadata + board task） |
| `api/chats/test_citation_seed_integration.py` | 模块 | citation seed → GET messages 集成单测（真 DB metadata） |
| `api/chats/test_prior_chat_recall_integration.py` | 模块 | prior_chat seed → GET `/recall/search` SSOT + mention inject 集成（真 DB，无 mock） |
| `api/channels/test_instance_lifecycle_integration.py` | 模块 | 渠道实例真实全链路集成（`@pytest.mark.integration`，关键路径无 mock）：`POST /instances` → 真实 `channel_factory` 创建 WebhookChannel → 真实 `ChannelGateway.add_channel` 热注册 → 持久化列表落库 → `DELETE /instances` → 真实 `remove_channel` 移除 + 持久化/凭据清理；删除不存在实例 404（覆盖设置页「删除实例确认」背后后端链路） |
| `e2e/test_evicted_live_terminal_chrome_e2e.py` | 模块 | UECD EvictedOutputDrawer Chrome MCP E2E（READ×1 SHPOIB：**单 tab** 全文 spill + `navigate` 过期 chat；选择器与分页探针统一来自 `support/evicted_drawer_selectors.py`；禁止拆成 2× `open_mcp_page`，并行 mux 会 30s timeout） |
| `e2e/test_bash_failure_dual_evicted_drawer_chrome_e2e.py` | 模块 | 失败 bash 双 evicted 流 Chrome MCP E2E（SHARED+NAMESPACE_WRITE×1：seed `bash_failure` variant → LiveTerminal stdout/stderr 双入口 → 各自 Drawer 读回；`evicted_view_full_output` / `evicted_view_full_stderr_output` data-testid） |
| `api/files/test_evicted_web_fetch_spill.py` | 模块 | UECD evicted-file API 单测（`web_fetch_{hex8}.md` basename + GET content） |
| `api/files/test_evicted_background_spill.py` | 模块 | UECD bash/background spill → evicted API 单测 |
| `integration/test_evicted_uecd_live_api_integration.py` | 模块 | UECD live API 集成（`resolve_verify_api_base()` 私池 · seed POST `_LIVE_SEED_POST_TIMEOUT_SEC=60` · GET evicted · 404 `expired` envelope） |
| `integration/test_artifact_share_integration.py` | 模块 | 工件分享真实全链路集成（无 mock）：`ArtifactVault.put` 真实落盘 → DB artifact/version → create share 真实物化 → public entry redirect → 静态资源放行；密码分享 gate + 签名解锁 cookie 授权 asset；SQLite 内存库 + TestClient 进程内 |
| `integration/test_chat_share_integration.py` | 模块 | 会话分享真实全链路集成（无 mock 关键路径）：SQLite 内存库 + TestClient 进程内——create 非加密分享 → status 反映活跃链接 → public GET 200；revoke → status revoked → public GET 404 → 重建链接不可复活已撤销链接；密码分享 gate（错误密码 403）→ 签名 unlock cookie → 放行 → revoke 后死链（含**无 cookie 新访客直接 404「Link Revoked」，不显示密码 gate**）；未分享/过期链接按 unshared 上报；chat 删除后 public GET 404 |
| `api/config/test_telegram_onboarding_apply.py` | 模块 | Telegram onboarding 原子编排回归（成功、失败回滚、同名冲突复用、并发防重、跨进程锁占用冲突） |
| `api/config/test_search_services_validation.py` | 模块 | searchServices Omni 422：unknown slug、duplicate enabled priority、non-selectable enabled slug |
| `api/config/test_omni_config.py` | 模块 | Omni-Config schema/sync/history/rollback；batch sync duplicate search priority 422 |
| `e2e/test_search_priority_chain_chrome_e2e.py` | 模块 | Search priority chain signoff（API integration persist + Chrome READ `lane=READ private_backend=False` Settings priority badges；payload Tavily p1 + Perplexity p2；`@pytest.mark.timeout(180)`） |
| `integration/test_fallback_integration.py` | 模块 | Harness provider_chain 集成：invalid primary hop、legacy role 迁移；SearXNG 不可用时 skip（`AllQueriesFailedError`） |
| `integration/test_command_center_vector_persistence_integration.py` | 模块 | Command Center `vector_persistence` 真实装配集成（禁 mock 关键路径）：真实 harness `create_local_memory_manager` + 真实 embedded Qdrant 可写路径 → `persistent`；不可写路径 fallback `:memory:` → `memory_fallback`；无 vector → `unavailable` |
| `integration/test_plugin_mcp_enabled_chain_integration.py` | 模块 | 插件 MCP `enabled` 生命周期真实全链路集成（关键路径禁 mock）：真实 ConfigService + UserConfig 表——set `mcpServers`（enabled True+False 双条目 + `plugin_name` 标记）→ `list_installed_plugins` 经加密落库读回真实 enabled → `extract_mcp_configs`（运行时唯一过滤点）只放行 enabled 条目 |
| `api/files/test_revert_seed_integration.py` | 模块 | Revert seed 四 variant + production persist root hydrate + channel cleanup（6 项；无 RevertService mock） |
| `services/files/test_revert_hydrate.py` | 单元 | `revert_hydrate.py` 100% 覆盖：root 解析顺序、hydrate、cleanup |
| `services/files/test_reveal_utils_obsidian.py` | 模块 | Obsidian launch 探测：Local/Tauri gate + macOS/Windows/Linux 安装路径 |
| `e2e/test_revert_files_chrome_e2e.py` | 模块 | RevertFiles Chrome MCP E2E（READ×5：modify undo+diff+confirm；empty toast；large_skip non-revertible toast；reload hydrate undo；session SessionRevertButton）；`prepare_e2e_ui_session` + `dismiss_blocking_modals` + async Sonner wait |
| `e2e/test_channel_routing_general_only_chrome_e2e.py` | 模块 | Channel Settings 渠道路由 Chrome MCP E2E（READ×1 SHPOIB：Settings → Channel Routing；Agent 下拉 **0 Search**；General-only SSOT 签收） |
| `e2e/test_channel_delete_confirmation_chrome_e2e.py` | 模块 | 渠道实例删除确认 Chrome MCP E2E（PRIVATE×1 SHPOIB：主账号 WeChat 卡片删除确认「取消保留/确认登出」走真实 `POST /wechat-logout`；wechat extra 实例 seed `POST /instances` → 确认删除走真实 `DELETE /instances` → 卡片消失 + 后端实例清理断言；删除失败容错「404 → 对话框保持打开 → 取消关闭保留 stale 卡片」；`ConfirmDialog` data-testid 探针） |
| `e2e/test_brand_studio_reset_confirm_chrome_e2e.py` | 模块 | Brand Studio 清空二次确认 Chrome MCP E2E（PRIVATE×1 SHPOIB：`/settings/brand-studio` 真实 WebUI 全链路——seed `brand_name` profile 记忆 → 面板渲染 → 点「清空」弹 `ConfirmDialog`（`confirm-dialog-*` testid）→ 取消保留值 → 再清空确认 → 表单清空 → 保存触发真实 `DELETE /memory/{key}?memory_type=profile` → 后端记忆消失；PRIVATE 隔离后端预配本地 embedding 使 memory 系统可用；关键路径无 mock） |
| `e2e/test_allowlist_pattern_live_chrome_e2e.py` | 模块 | Allowlist pattern Chrome LIVE×1（`private_backend=True`：bash 审批→pattern allow-always→Settings 验证） |
| `e2e/test_allowlist_pattern_chrome_e2e.py` | 模块 | Allowlist pattern Settings Chrome MCP E2E（SHARED+NAMESPACE_WRITE×1：seed-pattern-fixture → `/settings/security` pattern 条目） |
| `e2e/test_data_flow_disclosure_chrome_e2e.py` | 模块 | Data Flow disclosure Settings Chrome MCP E2E（SHARED+READ×1：`/settings/security` 本地域+控制平面+egress+Your Rights+点击合规导出全流程） |
| `e2e/test_delegation_permissions_chrome_e2e.py` | 模块 | Delegation permissions Chrome READ（SHARED+READ×1：Settings 只读徽标 + spawn/external 分离） |
| `e2e/test_delegation_permissions_live_chrome_e2e.py` | 模块 | Delegation permissions Chrome LIVE（SHARED+NAMESPACE_WRITE×1：真实 agent-stream + 审批流） |
| `e2e/test_security_preset_chrome_e2e.py` | 模块 | Security preset Chrome READ（SHARED+NAMESPACE_WRITE×1：preset 初始化 / UI 切换 / fail-closed） |
| `e2e/test_security_preset_live_chrome_e2e.py` | 模块 | Security preset Chrome LIVE×1（PRIVATE+exclusive_backend×6：真实 LLM + agent 切换 + YOLO mutex；post-stream `finalizeAgentStreamTurn`） |
| `e2e/test_file_write_empty_chrome_e2e.py` | 模块 | Empty file_write Chrome E2E（READ×2 SHPOIB：`seed-file-mutation-fixture?variant=empty_write` → FileMutationWarning 横幅 + `reload_mcp_page()` metadata 持久；LIVE×1：`test_file_write_empty_live_agent_webui` — 真实 LLM `file_write_tool(content='')` + mutation failure 横幅 + **磁盘无文件**；`@e2e_search_policy("empty")` + `seed-file-edit-batch-workspace` sandbox；**solo 签收** ~618s） |
| `api/chats/test_file_mutation_seed_fixture.py` | 模块 | HTTP：file-mutation seed `empty_write` → persisted `metadata.fileMutationFailures` |
| `api/chats/test_workspace_merge_seed_fixture.py` | 模块 | HTTP：workspace-merge seed `batch_merge_fail` → persisted `metadata.workspaceMergeFailures` |
| `e2e/test_workspace_merge_chrome_e2e.py` | 模块 | Chrome READ×2 SHPOIB：seed workspace merge fixture → WorkspaceMergeWarning + reload hydrate |
| `api/chats/test_rich_media_preview_seed_fixture.py` | 模块 | 集成：rich-media seed（chat + workspace png/pdf/zip/txt）→ chat.workspace_dir 持久化 + user 消息 + browse 二进制流式全字节/MIME |
| `e2e/test_workspace_rich_media_preview_chrome_e2e.py` | 模块 | Chrome READ×1 SHPOIB：seed rich-media fixture → workspace Files tab → png 图片加载 / pdf react-pdf canvas / zip unsupported 兜底下载 / txt 文本渲染 |
| `frontend/workspace-browser` 单测 | 模块 | RichMediaFilePreview 分发 12 例（kind 覆盖/大小写/unsupported/编辑按钮禁用）+ WorkspaceFilePreview is_text 降级 2 例（未知二进制→unsupported 不 fetch / 未知文本→文本渲染） |
| `api/agent/test_stream_collector_file_mutation.py` | 模块 | StreamContentCollector `file_mutation_failed` / `workspace_merge_failed` → `extra_data.fileMutationFailures` / `workspaceMergeFailures` |
| `api/agent/test_stream_collector_skill_batch.py` | 模块 | StreamContentCollector 收到 `tool_end`(`skill_mutation_batch_id`) → 关联到对应调用的 skill_manage 步骤（后一次调用不覆盖前一次、批次事件不新建步骤、`extra_data.progressSteps` 落库携带批次 id） |
| `api/agent/test_agent_stream_retry_contract_e2e.py` | 模块 | agent-stream 重试契约：执行中同 `chat_id+message_id+content` 重试 → user turn 幂等 + SSE `AgentBusyError`(409)；mock Agent 挂起 active session；**early claim** 后须等 user persist 再 retry |
| `api/agent/test_agent_stream_concurrency_limit_e2e.py` | 模块 | agent-stream 并发上限契约：gateway 排队超时 `AgentQueueTimeout` → 结构化 SSE `error_kind=concurrency_limit`（`diagnostic_result` 含 reason/占用者/i18n 文案/resolution_steps）；holder 直接挂起 gateway 占槽位，waiter 走真实 HTTP 全链路 |
| `api/agent/test_reconnect_integration.py` | 模块 | ASGI Last-Event-ID 重连 + early busy 第二 turn 不双写 user row（mock agent） |
| `api/chats/test_stream_retry_busy_seed_fixture.py` | 模块 | stream-retry-busy seed/release HTTP + **`test_busy_fixture_query_is_not_risk_blocked`**（fixture 文案不得触发 risk gate） |
| `e2e/test_stream_retry_contract_chrome_e2e.py` | 模块 | Chrome READ×1 SHPOIB：seed busy fixture → API POST busy 断言 → **`retryStreamWithSameMessageId` UI `busy:true`** → userCount 不变 |
| `e2e/test_slash_hyphen_command_chrome_e2e.py` | 模块 | Chrome E2E（PRIVATE+NAMESPACE_WRITE×2，无 LLM）：连字符 slash 命令回归——`fix it /systematic-d` 执行 skill 后保留前缀 `fix it ` + chip + wire `[use systematic-debugging] fix it`；Esc 关闭连字符命令面板且保留前缀（对应 `useSlashCommand.ts` 统一 `SLASH_COMMAND_SUFFIX_RE` 修复） |
| `e2e/test_mention_reference_stream_chrome_e2e.py` | 模块 | Chrome LIVE E2E（PRIVATE+LIVE×3，真实 LLM + `window.fetch` 拦截 `/agents/agent-stream` 请求体，无 mock）：保留 `@chat:` 引用 → payload 含 prior_chat；删除 token 后僵尸引用被过滤；粘贴 `@wiki:Concept` → payload 含 wiki_concept + `concept_name`（对应 `messageRequest.ts` `isReferenceTokenAlive` + `extractInlineMentionReferences` 修复） |
| `api/agent/test_timestamp_integration.py` | 模块 | Web 消息 timestamp/sent_at 持久化 + `ensure_chat_and_append_user_message` 幂等（同 id+content 复用 / 不同 content 换 id）；内存 SQLite |
| `api/agent/test_shpoib_hitl_attach_replay.py` | 模块 | SHPOIB HITL attach replay 集成（subscribe / multiplexed attach / hitl-probe / CORP；无 Chrome/LLM） |
| `api/agent/test_hitl_approval_resume_e2e.py` | 模块 | HITL 审批闸与续跑真实模型 E2E（`@pytest.mark.e2e`）：回环 HTTP 探针证明停靠在审批卡期间 `curl` 未执行、用户批准续跑后已执行；同一聊天连续 3 个停靠回合，断言续跑无 rejected/error 且回复完成 |
| `api/security/test_allowlist_api.py` | 模块 | Allowlist REST list/delete + pattern 粒度 round-trip |
| `integration/test_kanban_attach_handler_integration.py` | 模块 | SQLite attach handler + orchestrator unblock tool invoke |
| `integration/test_project_workspace_bind_file_write_integration.py` | 模块 | Project bind → `convert_to_general_agent_params.declared_allowed_roots` → `file_write_tool` 磁盘断言（无 LLM） |
| `integration/test_durable_outbound_integration.py` | 模块 | Durable outbound 全链路集成（15 cases：含 QueueFull 自动 recover、edit_placeholder、send_tracked、edit fallback、null-send→DLQ） |
| `api/health/test_liveness_pending_outbound.py` | 模块 | GET `/health/liveness` 返回 `pendingOutboundCount` |
| `api/health/test_liveness_gateway_runtime.py` | 模块 | GET `/health/liveness` 返回 `gatewayRuntime` 零载荷块；gateway 异常时 `state=degraded`；Prometheus `myrm_gateway_*` gauge 刷新 |
| `api/health/test_browser_doctor.py` | 模块 | 健康 browser 端点：`/health/browser`（pool health 正常/异常降级且根因进日志）+ `/health/browser/doctor`（relay 检查作为 `extra_checks` 传入 + launch_test 透传 + 真实 `run_doctor` 下 relay 行进入 `checks` 与 `summary`）+ `/health/browser/orphans` GET/DELETE（automation 扫描、confirm 安全门、预览只报会被清理的沙箱数、预览与清理共用 harness 默认沙箱年龄阈值、failed 透传、空孤儿、失败时根因进日志） |
| `api/health/test_browser_connectivity.py` | 模块 | `/health/browser/test-cloud-connection`（not_configured/disabled/invalid/connected/failed/无 WS 库）+ `/health/browser/test-proxy-connection`（not_configured/disabled/invalid/connected/http error/异常；mock config_service + websockets/httpx） |
| `services/extension/test_relay_check.py` | 模块 | Browser Doctor 的 `extension_relay` 检查：真实 `ExtensionBridgeService` 下的各状态：relay 就绪（ok）· 已连接但无授权站点（真实警告）· 远程部署缺 auth token（真实警告，已配置则不报）· 未连接 / relay 未就绪（可选能力）· 探测异常降级为可见警告（参数化） |
| `e2e/test_browser_doctor_chrome_e2e.py` | 模块 | Browser Doctor 卡片 Chrome MCP E2E（PRIVATE+READ×1：Settings/System 渲染卡片 + 运行诊断 → 真实后端报告（引擎行 + 残留进程与缓存行 + healthy/unhealthy 徽标）） |
| `e2e/test_org_model_policy_chrome_e2e.py` | 模块 | Org model policy Chrome MCP E2E（PRIVATE×1 SHPOIB：`exclusive_backend` · SHPOIB 后 `POST /api/admin/org-model-policy-sync` seed `minimax/*` → 打开 model picker → minimax 可选 / openai-like 灰显） |
| `api/chats/test_effective_workspace_ssot.py` | 模块 | SSOT：GET chat / suggest / browse(chat_id) / PATCH 409 — project.workspace_path 优先于 stale chat.workspace_dir |
| `services/workspace/test_file_watch_service.py` | 模块 | P1：watchdog emit / release / refcount → `WORKSPACE_FILE_CHANGED` |
| `api/files/test_browse_watch_api.py` | 模块 | P1：POST/DELETE `/files/browse/watch` 注册/释放 + 危险路径拒绝 |
| `api/files/test_browse_api.py` | 模块 | browse 目录/树/搜索 + content 文本 1MB 截断 & 二进制全量流式；`FileEntry.is_text` 三态（文本/二进制/目录）；Content-Disposition RFC 5987 转义（CR/LF 注入防御 + 非 ASCII filename*） |
| `services/project/test_legacy_workspace_path_migration.py` | 模块 | 假 `workspace_path` SQL 清理语义（清 `/persistent/workspace/project_%`、保留真实 bind） |
| `api/agent/test_workspace_rules_e2e.py` | 模块 | Workspace rules First-Match-Wins 真实 LLM E2E（`@pytest.mark.e2e` + `asyncio`：AGENTS.md > .cursorrules；规则注入 harness workspace 真实路径；async SSE 收集 + auto-approve resume 循环；断言依赖规则遵守 → 使用更强 LITE_MODEL；默认套件 deselect） |
| `api/agent/test_workspace_boundary_approval_e2e.py` | 模块 | Workspace 边界确定性路径策略（`PathPolicy` 外部写文件 → ASK，无 LLM）+ 越界文件访问审批 LLM E2E（`@pytest.mark.e2e`；LLM 类默认 skip：flaky + PathPolicy 已由确定性用例覆盖） |
| `core/security/test_workspace_boundary_batch_approval.py` | 模块 | 确定性 workspace 边界批量审批（`evaluate_tool_batch`：越界 `file_write` → pending 不自动执行，无 LLM） |
| `api/projects/test_project_workspace_e2e.py` | 模块 | Project workspace 多 Agent 协作真实 LLM E2E（`@pytest.mark.e2e`：project bind → chat 归属 → agent-stream 提及内置 agent → message_end；load_user_configs patch + checkpointer 注入） |
| `api/projects/test_seed_turn_lock_integration.py` | 模块 | 确定性项目锁 seed 端点集成：创建 project + 绑定 chat + `hold_ms` 三态语义（`None` 不占锁 / `0` 持有到 `release-turn-lock` 显式释放 / `>0` 到期自动释放）+ `release-turn-lock` 幂等释放 + `turn-lock-status` 只读查询（锁定/解锁/释放后 + 400/404 门控）+ 边界校验（400/404 门控） |
| `services/kanban/test_kanban_attach_handler.py` | 模块 | attach handler 单测（path/URL/SSRF/limits） |
| `services/kanban/test_worktree_integration.py` | 模块 | worktree 真实 git 集成（16 项）：分支唯一化防并行冲突 / 串行不丢提交 / COMPLETED merge 回目标分支 / 显式 target 分支（≠当前分支）merge 落地该分支且 main 不被污染 / auto-commit 被拒时保留 worktree 与未提交编辑（防丢数据回归）/ 非法分支名（`-` 开头）merge 拒绝且保留 worktree（防选项注入）/ merge 冲突保留 worktree + 收集冲突文件列表 + abort 恢复 repo（MERGE_HEAD 不残留，后续 merge 不被阻塞）/ cleanup 保留分支、merge 后删分支 / safe cleanup 对 dirty worktree 保留（ARCHIVED 防丢数据）/ 并发 merge 串行化不失败 / merge 冲突时追加 MERGE_CONFLICT 事件（payload 含冲突文件）/ 无 git user 配置时 auto-commit+merge 注入兜底身份成功 / git identity 仅注入缺失项（已配置 author 不被覆盖）/ 分支名消毒 / merge 幂等 |
| `services/chat/test_sandbox_worktree_integration.py` | 模块 | sandbox worktree 真实 git 集成（4 项）：clean merge 成功并入 main / dirty worktree auto-commit 后 merge 保数据 / safe cleanup 保留 dirty worktree（防丢数据）/ force cleanup 删除 dirty worktree（用户明确丢弃） |
| `services/kanban/test_board_settings_roundtrip.py` | 模块 | BoardSettings 9 字段 ORM 往返完整性（三映射函数 + dataclass 字段覆盖守卫 + 旧库 ALTER 迁移默认值） |
| `services/agent/test_agent_name_resolution.py` | 模块 | Agent 同名解析确定性单测（大小写归一 + 稳定排序 + 空名短路） |
| `services/agent/test_sandbox_l3_write_gate.py` | 模块 | 沙箱/编码能力型智能体 L3 写入门控单测（`is_sandbox_capable_tools` 探测、Profile 属性、converter 默认禁用自动提取与启用待审队列、incognito 覆盖等） |
| `api/agent/test_kanban_agent_stream_e2e.py` | 模块 | Live LLM agent-stream kanban add/list（`@pytest.mark.e2e`） |
| `api/agent/test_bash_compressor_declarative_e2e.py` | 模块 | Declarative bash 压缩真实 LLM agent-stream e2e（`@pytest.mark.e2e`；TestClient 进程内；`.myrm/filters.yaml` replace+strip 生效断言；压缩断言仅针对 tool stdout，LLM 回复文本不受过滤器影响） |
| `api/agent/test_bash_compressor_live_api_e2e.py` | 模块 | Declarative bash 压缩 live API e2e（`@pytest.mark.e2e`；`resolve_verify_api_base()` 私池 + provider seed + 后端 workspace 根解析；SSE 收集 + workspace 压缩回放） |
| `api/agent/test_idle_failure_chain_live_api_e2e.py` | 模块 | 失败工具回合后 idle 链 live API e2e（`@pytest.mark.e2e`；仅隔离 runtime；读 `idle_tasks.db` 断言只含受支持的 idle 任务类型且全部 completed） |
| `e2e/test_idle_chain_chrome_e2e.py` | 模块 | 真实 WebUI 发起一轮对话后 idle 链 Chrome e2e（`chrome_e2e` PRIVATE/LIVE）：关闭标签页后读隔离 runtime 的 `idle_tasks.db`，断言本会话 idle 任务全部 completed，失败信息附队列时间线 |
| `api/agent/test_bash_compressor_make_live_api_e2e.py` | 模块 | 内置 make 过滤器 live API e2e（`@pytest.mark.e2e`；`printf %b` 生成 tab recipe Makefile 触发真实 make 输出；raw 含 BUILT_OK 但压缩未消除目录行时回退 workspace 本地 make 验证） |
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
| `api/memory/test_pattern_discovery_api_integration.py` | 模块 | Pattern discovery API 真实 DB 集成（`@pytest.mark.integration`，关键路径禁 mock）：`POST /trigger-pattern-discovery` 无 WebUI 默认模型时真实 `load_platform_llm` 读库 → 优雅 skipped；harness 结果注入时真实 ledger 落库 + `GET /pattern-discoveries` 读回（summary 用户可读、无 `duration_ms` 泄漏）；skipped report 不落库 |
| `api/memory/test_pattern_discovery_live_e2e.py` | 模块 | Pattern discovery 真实 LLM E2E（`@pytest.mark.e2e`，`-m e2e` 才收集）：mock harness manager 边界（免 embedding/Qdrant），真实 `ChatLiteLLM`（`.env.test` BASIC_*）走 `run_pattern_discovery` → `with_structured_output` → 校验产出有效 `DiscoveredPattern`；并覆盖不成熟门槛跳过。暴露并钉住 prompt/schema 字段对齐缺陷修复（`title`/`evidence_summary`/`actionable_suggestion` + `AliasChoices` 容错） |
| `services/agent/stream_session/test_migration_readiness_anchor.py` | 模块 | migration readiness 首轮结果归类单测（success/failed/no_output） |
| `services/agent/stream_session/test_migration_bound_project.py` | 模块 | migration vault bind 同窗 handoff：`persist` 后 `move_chat_to_project`；已有 project / resume 跳过 |
| `services/agent/stream_session/test_orchestrator_turn_body_e1.py` | 模块 | E1 early buffered stream 形状（SSE/JSON）+ `_background_turn` 绑定 harness `session_lock` chat_id（快照以真实 chat_id 落盘的关键前置） |
| `services/agent/params/test_routing_memory.py` | 模块 | Smart Routing 记忆：持久化 `routingTier` 历史按枚举分流（reasoning 双归属、未知值丢弃）· `load_retry_baseline` 把被重试回合记录的值映射为 complexity 档位（specialty 命中 / 未知 / 未记录为 None；无 chat 不查库；查库失败降级为 None 并告警）· HITL resume 沿用被中断回合的路由结果（模型/fallback/档位/原因；主模型变化、槽位不可解析、记忆缺失时退回重新路由；LRU 淘汰）· 槽位映射枚举全覆盖 · `complaint_floor` 重试下限（逐档爬升、跳过与上一答案同配置的档位、无更强档位时停在上一档、同模型不同 reasoning_effort / model_kwargs / temperature 算不同档位、密钥与上下文窗口不算） |
| `services/agent/params/test_converter_routing_resume.py` | 模块 | converter 经真实 `convert_to_general_agent_params` 验证 resume 路由连续性（code specialty / reasoning 档位沿用、空 query 不重新路由、非 resume 回合不读写记忆）与历史动量接线（specialty 历史不再吞掉档位动量；代码回合后的短追问留在代码模型）；`test_converter_deep_research_routing.py` 验证深度研究回合丢弃 SIMPLE / STANDARD 判定（默认模型与 fallback 保持、不记档位与原因；同一问题在 agent 模式仍走轻模型，推理类问题仍升到 reasoning 槽位） |
| `services/agent/params/test_converter_retry_ladder.py` | 模块 | converter 经真实路由验证重试（complaint-up）每次爬升都换一个不同模型：廉价主模型跳过与自身相同的 light 档、昂贵主模型首次重试仍从 light 升到主模型、无更强档位时不谎称升级（`retry_floor_held`）且不降档、同模型更高 reasoning_effort 算真实升级、非重试回合的动量与档位记录不受影响、被重试的回答未记档位（fast 模式 / 固定模型）时以主模型为基线而非更早的路由回合 |
| `api/agent/test_last_turn_routing_tier.py` | 模块 | 真实消息表上重试基线的取值：被重试回合最新一条记了档位的回答（回合末尾的后台完成通知 / 无 `extra_data` 行不遮蔽它、早先回合的档位不顶替未记档位的回答、已被重试置为非活跃的回答照常读取、非字符串值忽略、specialty 值原样返回）· 与 `deactivate_last_assistant_siblings` 在时间戳相同时选中同一批行 · `load_retry_baseline` 到 `complaint_floor` 的端到端爬升 |
| `services/agent/params/test_converter_deep_research_routing.py` | 模块 | 深度研究的路由：SIMPLE / STANDARD 判定被丢弃（规划/报告保持默认模型及其 fallback，不记档位与原因）；REASONING 升档照常并记录档位；同一 query 在其他模式仍走 light；对该次运行重试会升到 reasoning 模型 |
| `services/agent/params/test_resolvers_secret_logging.py` | 模块 | 模型配置解析日志不含 provider 密钥，且仍记录解析动作（防空断言） |
| `services/statistics/test_usage_aggregation_savings.py` | 模块 | 路由省钱估算：按 token 加权的金标准值、路由更贵/标准档样本不足/无标准档 token 时隐藏、`aggregate_usage` 端到端 |
| `services/agent/stream_session/test_orchestrator_pending_approval_gate.py` | 模块 | HITL pending 审批守卫单元测（5 态：pending 拦截 / 0 pending 放行 / resume 绕过 / store 异常 fail-open / 无 chat_id 跳过） |
| `services/agent/stream_session/test_orchestrator_pending_approval_gate_integration.py` | 模块 | HITL pending 审批守卫真 DB 集成（关键路径禁 mock：真 `ApprovalRecord` → 真 `count_pending_for_chat` → SSE AgentBusyError 且预留前触发；APPROVED/growth/他 chat 不拦；resume 带真 pending 放行） |
| `services/hosting/` | 模块 | 多 target artifact 发布 API 与 provider 单测 |
| `architecture/_ARCH.md` | 模块 | 架构约束测试（含 migration 源闭包） |
| `api/runs/test_router.py` | 模块 | Unified Runs Hub 聚合 API 单测（20 项：源合并、degraded、分页、timed_out） |
| `remote_access/` | 模块 | 远程访问 trust_zone / pairing / E2EE / mobile_gate / host_allowlist / tailscale_guard 单测（21 文件） |
| `tasks/test_task_worker_retry.py` | 模块 | TaskWorker 自动重试回归（transient 重入 pending + datetime `next_retry_at`、permanent 失败终止、retries exhausted 终止；`next_retry_at` 未到期不消费、到期后执行，终态清空 `next_retry_at` 语义） |
| `tasks/test_task_event_bus.py` | 模块 | TaskEventBus 回归（事件正常入队；队列满时淘汰最旧并投递带 `sync_required` 的最新事件，断言 emitted/dropped/replaced 指标与 queue_full warning 节流） |
| `e2e/test_team_hub_builtin_badge_chrome_e2e.py` | 模块 | Team Assets Hub 内置 Agent 徽标 + 名称本地化 Chrome E2E（PRIVATE+READ×1：API 数据契约 `is_built_in` + `/settings/memory?sub=team-hub` 渲染「内置」徽标与 `getBuiltinAgentName` 本地化名 + follow-ups 筛选下拉本地化 + zh 界面无英文名泄漏） |
| `e2e/test_pattern_digest_panel_chrome_e2e.py` | 模块 | /journey Pattern Digest 面板真实浏览器 Chrome E2E（SHARED+READ×1：`window.fetch` 页内拦截 pattern-discovery API，零后端污染）。T1 /journey 渲染 growth dashboard → 切 evolution tab；T2 seed 2 events 卡片渲染（title/confidence/durability/count，zh/en 双语断言）；T3 展开卡揭示 suggestion/evidence；T4 空态 LEDGER → 本地化空态引导 + 触发按钮；T5 点击「立即分析」捕获真实 POST `/trigger-pattern-discovery`（hook 返回 `pattern_count=0` 走 no-new-patterns 分支）。用 `pin_direct_blank_heal` 防 wait_for_state 把 /journey heal 回家 |
| `e2e/test_pending_approvals_chrome_e2e.py` | 模块 | Fleet pendingApprovals KPI Chrome E2E（PRIVATE+NAMESPACE_WRITE×1：`POST /chats/test/seed-kanban-in-review-fixture` 单写者建 IN_REVIEW 任务 → 真实 UI /agents Fleet「Pending」KPI +1 → **点击 KPI 卡片验证深链直达 `/settings/kanban?status=in_review`（看板自动选中含待审任务的 board + status 过滤条 + 任务卡片落地）** → 双击卡片开抽屉 approve/reject 双生命周期回落；fixture 绑定内置 agent，抽屉 agent 下拉断言本地化名不泄漏英文） |
| `api/statistics/test_badges.py` | 模块 | Nav badges API 单测（monkeypatch kanban 合并 + OperationalError 降级；`TestKanbanCountRealStore` 真 SQL store 链验证 `count_tasks_by_agent`/`count_tasks` 聚合） |
| `api/statistics/test_pending_approvals_integration.py` | 模块 | pendingApprovals 全链路集成（真实 store seed IN_REVIEW → badges/fleet KPI 反映真实行；approve/reject 后回落；goal+kanban 合并） |
| `api/agent/test_fleet_overview_integration.py` | 模块 | Fleet Overview API 集成（Chat/CronJob/Approval 真实 DB 聚合 + kanban IN_REVIEW 并入 pendingApprovals + kanban store 故障降级） |
| `api/chats/test_kanban_in_review_seed_integration.py` | 模块 | IN_REVIEW seed fixture 集成（fixture → badges 计数 + approve/reject 转换回落） |
| `core/web_push/test_push_deep_links.py` | 模块 | Web Push 点击路由（resolve_push_url：APPROVAL_REQUIRED 深链、pending_review+board_id 直达看板 in_review 列、非 review 状态回退聊天页、缺 chat 回首页） |
| `api/kanban/test_in_review_api.py` | 模块 | IN_REVIEW 审批 API（approve/reject 转换、守卫、pending_review 通知 payload 含 board_id） |
| `platform_utils/sandbox/_ARCH.md` | 模块 | `platform_utils/sandbox` 业务逻辑回归（platform provider seed 14 例 + tool gateway merge），见子目录清单 |
| `services/agent/test_evolution_trigger_guard.py` | 模块 | `trigger_skill_evolution` 守卫单测（同 chat 在飞任务去重、普通对话 tool_steps<3 门槛跳过、DW `conversation_text` 绕过门槛） |
| `services/agent/test_evolution_engine_task.py` | 模块 | `_run_evolution_task` 后台任务执行路径单测（短历史跳过、历史拼接、DW 文本跳过 DB、无 proposal 早退、approval+broadcast 全链、异常兜底日志） |
| `services/memory/test_import_mem0.py` | 模块 | mem0 import adapter 单测（memories/results 双键识别、字段映射、tag 过滤、空/非法 drop、auto-detect、dry-run roundtrip） |
| `e2e/test_skill_health_chrome_e2e.py` | 模块 | /journey 技能健康度面板 Chrome E2E（SHARED+READ×3：`window.fetch` 页内替换 growth-dashboard 的 `skill_health`，零后端污染）。T1 三种结论（明星/风险/待验证）渲染：风险行显示成功率，待验证行只显示「–」与「已观测/所需」且无成功率，页面无任何状态码（STAR/HEALTHY/AT_RISK/UNPROVEN/STALE）；行按 `data-testid="skill-health-row"` 定位；切到「待治理」仅剩风险行、切到「健康与明星」仅剩明星行。T2 空列表 → 一句话空态且无筛选按钮。T3 点击风险行的「管理」→ 落在 `/settings/skills`、已安装 tab 激活且搜索框预填该技能名（不落技能市场）。服务端结论由 `tests/api/statistics/skill_growth` 覆盖；`pin_direct_blank_heal` 防 wait_for_state 把 /journey heal 回家 |
| `support/offline_memory.py` | 辅助 | 离线真实记忆管理器：真实内嵌 Qdrant + SQLite，仅把 embedding 换成确定性哈希向量（无需凭据与网络），并把 Qdrant 重试退避归零；`offline_memory_manager(base_path, monkeypatch)`，用例之间须 `clear_embedded_stores()` |
| `support/in_memory_remote_backup.py` | 辅助 | 内存版 `RemoteBackupStrategy`（字典存储 + 可编排的上传失败次数），远程备份测试共用 |
| `services/memory/backup/` | 模块 | 备份域真实存储测试（关键路径无 mock）：`test_snapshot.py`（覆盖往返、合并不重复、导出被截断即失败、审批队列管理器被拒、回放短缺上报、坏文件解码）· `test_volume_store.py`（保存/列表/加载/删除、备份 id 穿越拒绝、半成品不留、坏元数据跳过）· `test_service.py`（覆盖恢复先留底、失败指向留底备份、坏备份不动记忆）· `test_remote_round_trip.py`（远程备份→新设备恢复且可重复、远程恢复不删记忆、不完整不上传、穿越文件名与临时目录清理） |
| `services/memory/test_backup_remote.py` | 模块 | 远程备份策略与调度：配置/WebDAV XML 解析、`_upload_with_retry`、`_rotate_backups`、运行互斥、下载失败与版本不符的恢复拒绝、远程备份路由（配置缺失与可达性） |
| `api/memory/test_memory_backup_smoke.py` | 集成 | 备份 HTTP 全流程（真实路由 + 服务 + 卷存储 + 离线记忆管理器）：创建→列表→覆盖恢复（含自动留底）→删除；合并恢复；未知/畸形 id 404 且不动记忆；快照不完整与备份损坏的 `success=false` 响应形状 |
| `lifecycle/test_cognitive_clock.py` | 模块 | 认知时钟调度：T2 维护流水线每一步按真实签名调用（签名约束桩 autospec，健康快照与 SQLite 备份的调用必须匹配真实签名）、T3 仅随 T2 放行的 tick 且满一周才运行、首次读取唤醒守卫前的 15 分钟空闲间隔不遮住用户活动让步、唤醒心跳随协调器启停 |
| `lifecycle/test_wakeup_guard.py` | 模块 | 唤醒平滑守卫：两次读取之间的空闲间隔本身不算唤醒、墙钟与单调时钟漂移不论间隔多长都算唤醒、心跳运行期间的漏拍算唤醒、心跳启动时忘掉此前的时间、心跳停止期间的空闲间隔不算冻结 |
| `lifecycle/test_cognitive_clock_schedule.py` | 模块 | 虚拟时钟下真实协调器循环 + 唤醒心跳 + 守卫的节拍：空闲不算唤醒、间隔中途宿主挂起不拖延下一轮 T2、轮前一分钟挂起则等宽限期后重试、整个场景里 T3 只运行一次 |
| `lifecycle/conftest.py` | 辅助 | 每个用例前后把认知时钟的进程级单例（唤醒守卫、活动感知器、暂停信号）重置为全新状态，用例之间不经全局状态互相影响 |
| `lifecycle/test_memory_guardian_sqlite_backup.py` | 模块 | 维护周期末尾的 SQLite 热备份：对真实数据库落盘并校验、非文件库安静跳过、页拷贝脱离事件循环、失败只记 WARNING 不使周期失败 |
| `ai_agents/general_agent/test_skill_tool_mount.py` | 模块 | `skill_manage` / `skill_market` 经 ToolSetupMixin 真实挂载：启用或 `/learn` 强制挂载的判定、挂载后的工具经真实创建服务落盘并在写入前拦截危险内容、factory 只经 tool_setup 挂载 |
| `api/skills/test_skill_reveal_api.py` | 模块 | `POST /skills/{id}/reveal`：打开真实技能目录、非本地模式拒绝、未知技能/无本地存储/目录缺失的错误映射 |
| `services/agent/test_shared_context_name_resolution.py` | 模块 | 共享上下文显示名经真实 `SharedContextService` 与数据库往返抵达 agent params 与 wiki lane（会话导入出错会被兜底静默吞掉，故不 mock） |
| `services/skill_optimization/test_execution_provider.py` | 模块 | `ServerSkillExecutionProvider`：未接入的数据源返回空结果而非报错，元数据查询不记 ERROR |
| `services/skills/test_evolution_review_rollback.py` | 模块 | 演化评审回滚：fork 回滚移除其文件与记录且无错误，编辑回滚还原原始内容 |

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
- **Kanban Chrome E2E**：`tests/e2e/test_kanban_chrome_e2e.py`（`execution_mode=SHARED` ×14：看板列渲染 + `?source_chat=` 深链 + Chat 成功卡 → 过滤看板 + stats bar running `N/M` 并发占用 + ready 排队 badge ±（并发占满时显示 / 未满不显示）+ 多 ready 同时排队 badge（1 running + 2 ready 全部显示）+ 真实执行排队释放闭环（UI 建卡 → dispatcher 真实 LLM 执行 → 占槽 badge 出现 → 释放后 badge 消失 → 双双完成）+ 队列按序释放 badge 递减（3 任务单槽：2 badge→1 badge→0 badge）+ model_override UI 建卡/抽屉徽章编辑清除 + 技能选择器 UI 建卡（picker 搜索选择真实技能 → `extra_skill_ids` 持久化）+ 抽屉技能编辑保存（chips → 编辑态 → picker 增选 → 保存 → 退出编辑态且 API 持久化）。marker 已用现代 profile 字段（`execution_mode/access_scope/workload`），不再支持 legacy `private_backend` 字段（`scripts/dev/e2e_session/profile.py` 强制）。
- **Wiki citation Chrome E2E**：`tests/e2e/test_wiki_citation_chrome_e2e.py`（READ lane ×2：`/chats/test/seed-citation-fixture` → citation 按钮 reload 持久；`/settings/wiki?agentId=` combobox）。Settings 用例先 `warm_ui_route` HTTP 编译再 Chrome 导航（webpack 冷启）。READ 使用共享 `:8080`（`private_backend=False`）；**`private_backend=True`（SHPOIB）测例走私池 :180xx，并行窗口内无需 restart 共享栈**；仅共享 READ 写库测例新增 server 路由后须 `./myrm restart` 或 **`./myrm isolate <id> ready --chrome`**。
- **Clarify refresh Chrome E2E**：`tests/e2e/test_clarify_refresh_chrome_e2e.py`（READ×4 SHPOIB：`POST /chats/test/seed-clarify-refresh-fixture?variant=pending|answered|regenerate_sibling|structured_form` → 深链 `/{chat_id}` → `__MYRM_E2E_CHAT__.turnSnapshot` + DOM（`data-clarification-form` / `data-chat-input`）→ `client.reload` 二次断言；无 LLM）。HTTP 覆盖：`tests/api/chats/test_clarify_refresh_seed_fixture.py`（5 项 mock）。产品 hydrate SSOT：`clarificationState.ts` + `stream_finalize._mark_pending_clarification_answered`。
- **Clarify skip LIVE Chrome E2E**：`tests/e2e/test_clarify_skip_chrome_e2e.py`（LIVE×1 SHPOIB：真实 LLM HITL → Skip → agent resume；`E2E_SIGNOFF=1` 时 API fallback 加长 SSE 预算）。日常：`./myrm test -m chrome_e2e tests/e2e/test_clarify_skip_chrome_e2e.py`。**注**：M3 `test_clarify_signoff_api_e2e`（stub LLM 签收腿）已删除（2026-08-11）。
- **Inspector 面板生命周期 Chrome E2E**：`tests/e2e/test_inspector_panel_lifecycle_chrome_e2e.py`（PRIVATE+LIVE×1：真实前端 SSE handler 驱动 turn-engagement 状态机——`simulateBrowserToolStart`/`simulateBrowserViewUpdate` 经生产 handler 注入 TOOL_START/BROWSER_VIEW_UPDATE（engage turn + open panel + `sourceChatId` 绑定）→ 真实 LLM turn MESSAGE_END 触发 `releaseTurnInspectorControls(chatId)` 回收本 turn viewData → 手动打开的 desktop 面板（无 engagement）在 turn 结束时存活；`__MYRM_E2E_CHAT__` bridge 仅注入 view-data 制造步，全部断言落在真实 store/DOM）
- **muse-spark Responses wire Chrome E2E**：`tests/e2e/test_muse_spark_responses_wire_chrome_e2e.py`（PRIVATE+LIVE×1 SHPOIB：`muse-spark-1.2-contributor` OpenCode Go Responses wire；Turn1 强制 `web_search` → `TOOL_LOOP_OK`；Turn2 reasoning blob replay → `TURN2_OK`；前置 `~/.cursor-byok/opencode-go.json`）。**shared**：`./myrm ready --attach --chrome` → `./myrm test -m chrome_e2e -n0 ::test_muse_spark_responses_wire_two_turn_tool_loop`。**争用隔离**：`./myrm isolate muse-spark-wire restart --chrome` + `MYRM_E2E_ISOLATED_RUNTIME_ID=muse-spark-wire MYRM_E2E_FULL_ISOLATED=1` 同上。Harness 集成：`myrm-agent-harness/tests/toolkits/llms/adapters/wire/test_wire_integration.py::test_chatlitellm_responses_stream`（`-m integration`）
- **RevertFiles Chrome E2E**：`tests/e2e/test_revert_files_chrome_e2e.py`（SHARED×5：modify undo+diff+confirm；empty toast；large_skip non-revertible toast；reload hydrate undo；session SessionRevertButton）。seed fixture（`app/api/chats/test_fixtures/revert.py`）模拟真实 agent 路径：快照 key 为 `r-` 前缀请求 ID、assistant 消息 DB 主键为独立 UUID、`extra_data.request_message_id` 携带 r- ID——刷新 hydrate 后前端用 `requestMessageId || messageId` 定位回退目标，E2E probe 与 `RevertFiles` 组件走同一解析逻辑，防止「消息主键 == 快照 key」的假自洽盲区
- **RevertFiles LIVE Chrome E2E**：`tests/e2e/test_revert_files_live_agent_chrome_e2e.py`（LIVE×1 SHPOIB：workspace seed 后真实 LLM 回合 `file_edit_tool` 修改文件并回复 `REVERT_LIVE_OK`；回合预算 300s、attempt=1，受 coordinator BODY_WALL 600s 约束；快照记录 → 页面刷新 hydrate `requestMessageId` → 真实 UI 回退断言文件恢复 seed 内容）
- **Memory citations Chrome E2E**：`tests/e2e/test_memory_citations_chrome_e2e.py`（READ lane ×2：`/settings/memory` 开「历史会话搜索」；聊天页注入 citations → 「依据/Evidence N」Sheet）。并行 attach 若 mux timeout drift，须 `MYRM_MUX_ALLOW_TIMEOUT_RESTART=1`（见 `chrome-e2e-preflight.sh` attach heal）。
- **Memory A/B Chrome E2E**：`tests/e2e/test_memory_ab_chrome_e2e.py`（READ×1 + NAMESPACE_WRITE×2，`e2e_search_policy("empty")`）：① 卡片入口 + 确认对话框取消（`all_cards_memory_ab_ready_js` 每卡就绪 → `click_subset_memory_ab_js`）；② `_seeded_memory_ab_reports` 预置 latest+older 双报告到 `.myrm/memory_ab_reports/` → Memory A/B tab 双臂矩阵（No/With Memory 行 + Memory Calls 列 + per-arm pass-rate `50%(0)`/`100%(5)`）+ Run History 表 + 点击 View 加载 aged 报告（case message + Current 禁用态）；③ 真实 run：确认 Start → SSE running + header Stop → Stop 清理。**注意**：历史表 pass-rate 单元格渲染为 `50%(0)`（无空格），probe 正则用 `50%\s*\(0\)`；seed 目录需同时写 timestamped JSON + `latest.json`（对齐后端 `run_memory_ab_background`）。
- **Voice memory ACL Chrome E2E**：`tests/e2e/test_voice_memory_acl_chrome_e2e.py`（READ lane ×2：Settings UI 开/关 memory+sessions → `personalSettings` API 断言；**不依赖** Providers Google key；corpus enum / tool-exec flags 见 `test_voice_memory_acl_api_integration.py`）。
- **Skill marketplace LIVE Chrome E2E**：`tests/e2e/test_skill_marketplace_live_agent_chrome_e2e.py`（LIVE×1 SHPOIB：`skill_market_tool` agent-stream 真实 LLM 断言；UI toggle 见 READ gate；见 `scripts/dev/CHROME_MCP_E2E.md`）
- **Empty file_write Chrome E2E**：`tests/e2e/test_file_write_empty_chrome_e2e.py`（READ×2 SHPOIB：seed mutation fixture → FileMutationWarning + reload 持久；LIVE×1：`agnes-2.0-flash` 真实 tool call；见 `scripts/dev/CHROME_MCP_E2E.md`）
- **Background Tasks Panel Chrome E2E**：`tests/e2e/test_background_tasks_panel_chrome_e2e.py`（READ×5 SHPOIB：panel 列表、failed/running seed、UI cancel、vault log drawer、success finish toast；见 `scripts/dev/CHROME_MCP_E2E.md` §Background Shell）
- **Background shell LIVE Chrome E2E**：`tests/e2e/test_background_shell_live_agent_chrome_e2e.py`（LIVE×1 SHPOIB：自然语言 prompt + agent-stream spawn；HITL 时 `decisions[]` approve；见 `BUGFIX_LOG.md` BUG-DG-2026-07-23-010）
- **UECD EvictedOutputDrawer Chrome E2E**：`tests/e2e/test_evicted_live_terminal_chrome_e2e.py`（READ×1 SHPOIB：`seed-evicted-live-terminal-fixture?variant=full|expired` → LiveTerminal 截断预览 → View Full Output → **`drawer_mount_wait_js` 等待 lazy drawer DOM** → Drawer 全文/过期；共享 `tests/support/evicted_drawer_selectors.py` 统一选择器与分页参数探针）。**CI anti-mux**：同一 SHPOIB + **单 `open_mcp_page`**，场景间 `client.navigate` 切 chat；**禁止**拆成 2 测例各开新 tab（并行 E2E 下第二次 `new_page` 易 30s timeout；pytest rerun 不采纳）。HTTP/API 覆盖见 `test_evicted_web_fetch_spill.py`、`test_evicted_background_spill.py`、`test_evicted_uecd_live_api_integration.py`
- **失败 bash 双 evicted Drawer Chrome E2E**：`tests/e2e/test_bash_failure_dual_evicted_drawer_chrome_e2e.py`（SHARED+NAMESPACE_WRITE×1：`variant=bash_failure` seed 一个失败 bash step 同时 evict stdout+stderr → LiveTerminal 双 "view full output" 入口 → `EvictedOutputDrawer` 分别读回两文件；共享 `ensure_chat_route` + `evicted_drawer_selectors.py`）
- **Chrome E2E 共享路由/heal helpers**：`tests/support/chrome_mcp_e2e.py` 提供 `ensure_chat_route`（复用 warm shell 时强制导航到目标 chat 路由并校验 React hydration，`errorOverlay`/`ChunkLoadError` 下 cache-bypass reload 自愈）、`wait_for_state`（含 errorOverlay 检测的 overlay-heal 阶段）、`warm_ui_route`（turbopack 预编译）。凡 `open_mcp_page` 后直接进入 chat 页的 E2E 均经 `ensure_chat_route`，禁止绕过
- **UECD LIVE fast+deep Chrome E2E**：`tests/e2e/test_fast_deep_search_evicted_read_chrome_e2e.py`（LIVE×1 SHPOIB：真实 MiniMax + fast/deep + Wikipedia `web_fetch_tool` spill → `file_read_tool`；`preserveActionMode` + progress **UI 优先 / API 自愈**（Chrome CDP flake 时 `_api_deep_search_progress` 不断言中断））
- **UECD LIVE bash foreground Chrome E2E**：`tests/e2e/test_bash_foreground_evicted_live_chrome_e2e.py`（LIVE×1 SHPOIB：yolo code_execute agent → 前台 `bash_code_execute_tool` 大输出 spill → GET `/files/evicted` + LiveTerminal Drawer；**无 enrich 端点**，断言真实 `tool_call_id` 绑定 reload 路径）
- **Subagent Dashboard Chrome E2E**：`tests/e2e/test_subagent_dashboard_chrome_e2e.py`（LIVE lane ×6：`subagent-dashboard-e2e-prepare.mjs` delegate → Dashboard cancel / pause toggle / token+model / budget used-limit / canvas 拓扑渲染+点击节点定位回树 / fission 拓扑经 store bridge 注入后合并渲染；`open_mcp_page(..., timeout_ms=MAX_PAGE_TIMEOUT_MS)`）
- **Subagent rebind 单测**：`tests/services/agent/test_subagent_rebind_event.py`（`AgentService.update_agent` 变更 `subagent_ids` → `SUBAGENT_REBIND_REQUIRED`）
- **Citation seed 集成单测**：`tests/api/chats/test_citation_seed_integration.py`（seed → GET messages 断言 `citedMemoryIds`；默认 CI 套件执行，不依赖 Chrome）
- **Prior chat recall SSOT 集成单测**：`tests/api/chats/test_prior_chat_recall_integration.py`（seed-prior-chat-fixture → GET `/recall/search` → mention inject；默认 CI，不依赖 Chrome）
- **MCP reload confirm Chrome E2E**：`tests/e2e/test_mcp_reload_confirm_chrome_e2e.py`（READ×1 SHPOIB 单会话：toggle · delete · import · add/save → `MCPReloadConfirmDialog`；见 `CHROME_MCP_E2E.md` §MCP reload confirm）
- `tests/services/code_graph/test_code_graph_service.py`：AST 抽取器与 CodeGraphService 符号/调用图谱/拓扑查询单元测试
- 并行（内存充足时）：`PYTEST_XDIST_WORKERS=4 scripts/dev/run_tests_low_memory.sh`；避免 `-n auto`（多 worker RSS 叠加，`-n auto` 在 8 核上可达数 GB）
- 定位高内存文件：`uv run python scripts/dev/profile_test_memory.py tests/api/agent --top 20`
- WebUI E2E：MCP **chrome-devtools** + Myrm E2E Chrome `:9333`（`./myrm ready --chrome`）；marker **`chrome_e2e`**（`lane=READ|LIVE_AGENT`）；禁止 `@playwright/test`。正式入口 **`./myrm test -m chrome_e2e`**；`tests/e2e/test_*_chrome_e2e.py`（含 Goal、execution_cache、edge_tts、parallel_tabs READ lane、`test_channel_routing_general_only_chrome_e2e` General-only 签收、`test_push_approval_deeplink_chrome_e2e` 等）；READ 只读测例不占 LIVE_AGENT cap（`scripts/dev/e2e_session/lane.py`）
- CI 默认套件：`scripts/ci/run_default_tests.sh`（`-m 'not e2e and not performance' -n0`，workflow `server-unit-tests.yml`）
- `tests/api/skills/test_drafts_seed_mock.py`：seed-mock HTTP 单测（含 `agent_id` 查询参数，默认套件执行）
- `tests/core/cron/test_seo_weekly_audit_blueprint.py`：SEO 巡检蓝图与 `web-project-seo-optimization` 技能元数据/实例化单测
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
