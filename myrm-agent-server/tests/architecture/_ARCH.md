# tests/architecture/ 模块架构

## 架构概述

Server 层架构约束测试：禁止新增 harness 深导入、禁止 `uv.lock` editable harness pin、禁止跟踪 markdown 链到私有开发壳 `temp-docs/`、禁止测试目录提交完整厂商格式凭据。

## 文件清单

| 文件 | 职责 |
|------|------|
| `test_sse_event_type_parity.py` | harness `AgentEventType` ⊆ 前端 `knownSseEventTypes` 清单 |
| `test_harness_api_export_parity.py` | server 引用的 `myrm_agent_harness.api.X` 必须已在该层 `_EXPORTS`/`__all__` 导出（消费侧护栏：harness 内部重构漏导出会让后端启动 `ImportError`）|
| `test_doctor_component_names_parity.py` | 体检页组件标题表：后端所有 `HealthReport(component_name="…")` 字面量 == 前端 `doctorReportView.ts` 的 `COMPONENT_NAMES`（后端新增探针漏登记，或前端留着已删探针的名字与六语言文案，都会失败）|
| `test_privacy_entrypoints.py` | 每个构造 `GeneralAgentParams` 的服务端入口（IM、cron、语音、目标、看板）必须展开 `**privacy_agent_params(...)`，wakeup 复制路径必须调用它；否则设置页的隐私开关只覆盖 Web 对话（豁免：Web converter、eval executor）。AST 逐调用点检查，并自带正反例自检 |
| `test_text_entry_risk_gate.py` | 接受用户键入的指令文本的入口（聊天回合、steer / redirect、子智能体与后台任务 steer、定时任务与心跳提示词、看板任务（创建、编辑、移动、驳回、回收）与评论、目标文案与子目标 / 草稿、重新生成的补充指引、旁路顾问提问、Wiki 知识库查询、看板分解的子任务标题、智能体档案、AI 创建与提示词生成、批量目录提示词、技能派生、IM 的轮次 / 忙时转向 / 系统命令 / 事件触发派发 / `/deny` 理由；续跑请求里审批的驳回理由与指引在聊天回合入口一并过闸）必须各调用自己的风险闸门，四个闸门（`check_stream_risk`、`_risk_refusal`、`reject_if_risky`、`hold_risky_inbound`）必须都以 `screen_user_text` 收尾；另扫描 `app/api` 全部 POST / PUT / PATCH 处理函数（请求模型含继承与嵌套），请求里带 `prompt` / `instruction` / `intent` / `objective` / `goal` / `message` / `question` / `answer` / `comment` / `modified_plan` 字段的必须登记或写入 `_EXEMPT`（附「文本不是给智能体照做的」理由；澄清、人工闸门与计划编辑的回答把智能体写的选项和用户键入的文字混在一起，审批 REST 的 `comment` 没有智能体读它，都按理由豁免），过期的豁免也失败；新增这类端点未登记即失败。没有调用方的路由（前端源码里没有能到达它的路径字面量，带动态段的 `/agents/chats/${id}/${kind}` 可以是同形状的任一路由，也没有登记的外部调用方；字面量与 `test_api_route_consumers.py` 共用，该门禁按「有无调用证据」严格读，这里按「能否排除有人调用」宽读）没有用户往里键入，不进该扫描，由路由消费者门禁要求删除或接上调用方，接上的那一刻起按普通端点扫描；豁免过期与否按未过滤的扫描判断；校准用例：已登记入口里一半以上读成无调用方即失败（前端不再写路径字面量会让所有端点读成无调用方，扫描会空转）。有调用方的新端点（含工作区里他人未提交、已接上前端的）未登记会让该扫描变红，这是预期行为。AST 检查，并自带探测器与扫描器正反例自检 |
| `test_outbound_model_calls.py` | `app/` 内直接调用 litellm 对话接口的文件必须登记：要么先用 `sanitize_outbound_text` 脱敏（文件内须真有该调用），要么写明其文本不含对话内容的理由；否则隐私开关挡不住它。自带检测器正反例与过期登记检查 |
| `test_memory_injection_contract_parity.py` | 前端 `MemoryBriefStatus(source)/MemoryBriefInjectionStatus` union 与 server+harness 状态契约严格同构 |
| `test_settings_deep_links.py` | 前端源码、server 推送/提示与预置技能资产里写死的 `/settings/<tab>` 深链必须落在前端路由 SSOT `settingsRoutes.ts`（`SETTINGS_TABS` ∪ `SETTINGS_TAB_REDIRECTS`）内，杜绝 404 死链 |
| `test_memory_brief_prometheus_rules_contract.py` | memory brief 告警规则契约（flush HTTP attempts-based ratio + strict dedup reject ratio/burst 关键片段；直接跑 pytest 时本地无 promtool 可 skip；`scripts/ci/run_architecture_gates.sh` 与 CI 均强制 promtool `check rules`） |
| `test_memory_brief_telemetry_layout.py` | memory brief CP 遥测须位于 `app/services/agent/memory_brief_telemetry/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_builtin_specs_layout.py` | 预置智能体规格须位于 `app/services/agent/builtin_specs/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_memory_guardian_guard_telemetry_layout.py` | memory guardian guard CP 遥测须位于 `app/services/agent/memory_guardian_guard_telemetry/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_marketplace_layout.py` | Agent Marketplace 导入/导出须位于 `app/services/agent/marketplace/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_app_package_init_layout.py` | `app/**` 含 `.py` 的目录须声明 `__init__.py`（禁止隐式 namespace 包） |
| `test_conversation_recall_layout.py` | Conversation Recall 仓储须位于 `app/database/repositories/conversation_recall/` 子包，禁止 repositories 根 legacy 平铺文件复活 |
| `test_e2ee_layout.py` | Mobile remote E2EE 须位于 `app/remote_access/e2ee/` 子包，禁止 remote_access 根 legacy 平铺文件复活 |
| `test_builtin_agent_i18n_parity.py` | 前端 `builtin-agent-i18n-data.ts` 的 key 集合须与 server `_BUILTIN_AGENTS` id 严格同构 |
| `test_channel_catalog_i18n_boundary.py` | server 渠道 JSON catalog 边界：键集 ⊆ 白名单、全语种同构、禁止 fork harness 诊断目录（SSOT） |
| `test_catalog_category_locales.py` | 集成目录 API 返回的每个分类，六种语言的 `settings.integrationCatalog.categories` 都有显示名（目录页按 `categories.${id}` 动态取词，缺失会静默露出内部分类 id） |
| `../fixtures/frontend_sse_event_types.json` | 由 frontend `scripts/export-known-sse-event-types.ts` 生成 |
| `test_server_harness_imports.py` | 相对 baseline 禁止新增 server→harness 内部 import；并禁止 import 含 ``._`` 的 harness 私有模块路径 |
| `test_dev_pid_path_ssot.py` | `scripts/**` 禁止读取子目录 `.myrm-dev-*` pid（cleanup rm 豁免） |
| `test_server_pyproject_lock_parity.py` | pyproject 主依赖/optional extras 与 uv.lock requires-dist 同构；禁止 GPL/optional 包与 harness 已 pin 的 `litellm`/`langchain`/`langchain-core` 回流 main |
| `test_uv_lock_harness_registry.py` | 主 wheel + 平台 core 均上 PyPI 后，`uv.lock` 须 registry pin（否则 skip，允许 monorepo editable） |
| `test_no_user_id.py` | 单机 server 禁止多租户 user_id 泄漏 |
| `test_no_temp_docs_links.py` | 跟踪的 `*.md` 禁止 `temp-docs/` 相对路径（私有开发壳） |
| `test_no_provider_shaped_secrets_in_tests.py` | server 测试目录禁止出现完整的厂商格式凭据（Stripe 密钥、Slack token），否则 GitHub push protection 会拒绝整个推送；假值统一经 `tests/support/fake_secrets.py` 拼装。含守卫自检：正则必须仍能匹配夹具输出，避免扫描空转 |
| `test_arch_no_placeholder.py` | 产品树 `_ARCH.md` 禁止「见源码」等占位短语（含 `myrm-agent-extension/`） |
| `test_server_scripts_arch.py` | `myrm-agent-server/scripts/**` 子树必须有 `_ARCH.md` |
| `test_sync_arch_guard.py` | `sync_arch_file_tables.py` 不得覆盖已人工维护的 `_ARCH.md`（混合 stub/✅ 或多余章节） |
| `test_no_app_main_in_tests.py` | `tests/**` 禁止 AST 级 `import app.main`（须用 `build_minimal_app`） |
| `test_unit_test_layout.py` | 禁止 `tests/unit/**/api/`（与 `tests/api/` importlib 包名冲突） |
| `test_integrations_hardware_routes.py` | `/api/v1/integrations/hardware/*` 路由已注册（防 prefix 回归） |
| `test_frontend_api_client_paths.py` | 前端 `src/**` 调用必须命中真实路由：apiRequest/apiClient 字面量（路径+方法，含 `/webui`）；任意形式写出的 `/api/v1/...` 字面量（raw fetch、展示给用户的 webhook URL）须命中路由或路由基路径；`/api/<root>` 字面量的 root 须由 Next route handler、控制平面或渠道入口提供；已知缺失显式登记，路由出现后条目必须删除 |
| `test_api_route_consumers.py` | 每个 API 路由都要有调用方：前端非测试源码里有路径字面量（任意调用形式，按路径而非方法匹配；`/webui/**` 额外按去掉挂载前缀匹配 `getWebuiUrl` 调用），或登记在 `data/route_external_consumers.txt`（每条写明调用方 file:line）；存量无调用路由登记在 `data/route_consumer_baseline.txt`，只许缩小（路由已删除、已有调用方或已登记都会失败）；路由不得重复声明已挂载的 `/api/v1` 前缀。路由表、前端匹配与登记文件的读取在 `support/route_consumers.py`，风险闸门的用户文本入口扫描共用同一判定 |
| `data/route_external_consumers.txt` | 前端不调用、但有外部调用方的路由登记：`METHOD /path \| 调用方 file:line` |
| `data/route_consumer_baseline.txt` | 门禁引入前就没有调用方的存量路由；删路由或接上前端后必须同步删行 |
| `test_memory_router_mounts.py` | `app/api/memory/router.py` 里无条件挂载（对所有用户可见）的子路由必须登记在 `data/memory_default_mounts.txt`：新增路由要么收进 `settings.memory_labs_enabled` 开关，要么写明默认可见调用方 file:line；路由消费者门禁会把「只有隐藏面板的 service 引用」算作调用方，拦不住进程内演示引擎，所以单独把关。解析源码而非导入；写明的调用方必须是真实存在的非测试文件里的有效行号；自带检测器正反例自检 |
| `data/memory_default_mounts.txt` | 无条件挂载的记忆子路由台账：裸行是门禁引入前的存量，只许删除；`挂载名 \| 调用方 file:line` 是引入后经论证放行的新增 |
| `test_public_mutating_routes.py` | 变更类路由（POST/PUT/PATCH/DELETE）跳过认证中间件只有一种合法理由：handler 自己认证调用方；此类路由必须登记在测试内的表里并写明认证方式，未登记（例如公开前缀把运维动作一并放行）或登记后不再公开都会失败 |
| `test_openapi_operation_ids.py` | 全量公开 API 的 OpenAPI operationId 必须唯一：同一 (method, path) 重复注册（后者被静默遮蔽）或单个 `api_route` 挂多个 method 都会失败，一个路径只允许一个 handler |
| `test_api_services_vocabulary.py` | `app/api/` 与 `app/services/` 顶域分区 + 别名表与 `CONTRIBUTING.md` 同步 |
| `test_calendar_schema_retired.py` | 磁盘无 calendar ORM/API；`migrations.py` 尾部 DROP calendar_events 表/索引 |
| `test_project_legacy_workspace_migration.py` | `CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL` 须注册于 `MIGRATION_STATEMENTS` 尾部 |
| `test_migration_source_closure.py` | Wizard 封闭 4 源：probe 导出 ≡ `supported_source_ids()` ≡ loader 注册 |
| `test_cookbook_specs_asset.py` | `assets/cookbook_specs.json` bundled 结构校验 |
| `test_prebuilt_skill_bash_contract.py` | 引用 `bash_code_execute_tool` 的 prebuilt `SKILL.md` 必须含 `## Bash execution contract` |
| `test_prebuilt_skill_evidence_discipline.py` | `evidence-discipline` skill 契约防漂移：六态机/证明义务/边界否定/归因/冲突/反剧场/安全契约 marker + 注入预算上限 |
| `test_prebuilt_skill_browser_automation.py` | `browser-automation` skill 契约防漂移：三轨决策树/Write Probe/Clear & Replace/声明式 steps[]/verify_goal/HITL 护栏（单测覆盖） |
| `test_prebuilt_skill_web_scraping.py` | `web-scraping` skill 契约防漂移：三维加载模式/双哨兵防死循环/流式落盘缓存/双引擎输出工件规程（单测 100% 覆盖） |
| `test_prebuilt_skill_voice_memo_synthesizer.py` | `voice-memo-synthesizer` skill 契约防漂移：四维解构/Actionability 门禁/唯一幂等键/UTF-8-SIG 规程 |
| `test_prebuilt_skill_voice_corpus_review.py` | `voice-corpus-review` skill 契约防漂移：跨会话多素材聚合/看板真实验收/阻碍归因/周度复盘工件规程 |
| `test_prebuilt_skills_frontmatter_keys.py` | 出厂 prebuilt `SKILL.md` 的 frontmatter 只能声明运行时认识的键（loader 对未知键只告警，写错的键会静默失效）；`pipeline_spec` 为看板流水线专用豁免；自带反向对照防空转 |
| `data/server_harness_import_baseline.txt` | harness import 允许 baseline |
| `test_no_core_services_api_imports.py` | `app/{core,services,lifecycle}/` 禁止 import `app.api` |
| `test_telegram_channel_mixin_mro.py` | `TelegramChannel._pre_emit_hook` 必须来自 hooks mixin；inbound 不得定义同名方法 |
| `test_openai_compat_agent_api_boundary.py` | `/v1` 仅 Agent API：`openai_compat/` 文件白名单 + 禁止 LLM gateway 模块（passthrough/ProxySettings/combo 等）复活 |
| `test_kanban_attachment_storage_ssot.py` | Kanban 附件字节读取必须使用 `files_service.get_content`，禁止误用 `get_file_content(file_id)` |
| `test_nas_docker_compose_template.py` | NAS / HomeLab Docker Compose 覆盖编排契约与三卷持久化挂载验证 |
| `data/server_api_import_baseline.txt` | 上述门禁 baseline（须保持为空） |
| `../../scripts/ci/file_line_budget_baseline.txt` | `check_file_line_budget.py` 的超标模块台账（本地自查用，非 CI 阻断） |

## 依赖

- `myrm-agent-server/pyproject.toml` — harness 版本 pin
- `myrm-agent-server/uv.lock` — OSS `main` 须 PyPI registry pin；本地 editable harness 仅用于开发联调（勿提交到 OSS `main`）

## 运行

- 本地：`bash myrm-agent-server/scripts/ci/run_architecture_gates.sh`（fractal + `--no-stub` + `promtool check rules` + architecture pytest）
- CI：`myrm-agent/.github/workflows/server-architecture.yml`（无 PyPI 且无 checkout harness 时失败闭合）
