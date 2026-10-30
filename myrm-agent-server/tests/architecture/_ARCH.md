# tests/architecture/ 模块架构

## 架构概述

Server 层架构约束测试：禁止新增 harness 深导入、禁止 `uv.lock` editable harness pin、禁止跟踪文本文件出现私有开发壳的规划目录、名称、维护者速查文档名与规划条目编号、禁止测试目录提交完整厂商格式凭据、定时任务 REST 的请求与响应字段漏转（路由没读的请求字段、响应映射没填的响应字段）、蓝图填充响应的服务端与前端字段不一致。

## 文件清单

| 文件 | 职责 |
|------|------|
| `test_sse_event_type_parity.py` | harness `AgentEventType` ⊆ 前端 `knownSseEventTypes` 清单 |
| `test_spillover_limits_parity.py` | 前端 `spillover.ts` 的长粘贴阈值（字数、词元压力、预览长度）与六类字符权重（小写与空白、大写、数字、其余 ASCII、非 ASCII 窄字符、宽字符）必须等于 harness `ContextGuardConfig` / `estimate_token_pressure`（输入框提示「将存为文件」与服务端落盘必须对同一段文本同时成立） |
| `test_harness_api_export_parity.py` | server 引用的 `myrm_agent_harness.api.X` 必须已在该层 `_EXPORTS`/`__all__` 导出（消费侧护栏：harness 内部重构漏导出会让后端启动 `ImportError`）|
| `test_doctor_component_names_parity.py` | 体检页组件标题表：后端所有 `HealthReport(component_name="…")` 字面量 == 前端 `doctorReportView.ts` 的 `COMPONENT_NAMES`（后端新增探针漏登记，或前端留着已删探针的名字与六语言文案，都会失败）|
| `test_tool_stuck_pause_clients.py` | loop guard 暂停：Web 前端 `toolsProgressEvents.ts` 与扩展侧栏 `approval.js` 比较 `action_type` 用的字面量必须含 harness 的 `TOOL_STUCK_ACTION_TYPE`（改了标记而客户端没跟，暂停会在那里被当成待回答的审批）；检出里没有该客户端的源码时跳过 |
| `test_approval_reason_code_parity.py` | 审批理由码：harness 引擎会发的 `ApprovalReasonCode` == 前端 `approvalReasonCode.ts` 的 `APPROVAL_REASON_CODES`（引擎新增码漏了卡片文案，或前端留着引擎不再发的码与六语言文案，都会失败）|
| `test_litellm_routing_frontend_parity.py` | 前端 `litellmRouting.generated.ts` 的路由前缀列表（含顺序）与 provider → 前缀映射必须等于 harness 路由表（`known_litellm_route_segments_ordered`、`BUILTIN_PROVIDER_LITELLM_SEGMENT`），只比较取值、不比较引号与写法；映射缺项时前端回落到 provider id，请求会因 LiteLLM 不认识该路由而失败；自带五种漂移（缺前缀、顺序、缺或多出 provider、映射到别的前缀）的反例；检出里没有前端源码时跳过；该产物文件的改动单独触发 `server-architecture.yml` |
| `test_privacy_entrypoints.py` | 每个构造 `GeneralAgentParams` 的服务端入口（IM、cron、语音、目标、看板）必须展开 `**privacy_agent_params(...)`，wakeup 复制路径必须调用它；否则设置页的隐私开关只覆盖 Web 对话（豁免：Web converter、eval executor）。AST 逐调用点检查，并自带正反例自检 |
| `test_text_entry_risk_gate.py` | 接受用户键入的指令文本的入口（聊天回合、steer / redirect、子智能体与后台任务 steer、定时任务与心跳提示词、看板任务（创建、编辑、移动、驳回、回收）与评论、目标文案、子目标 / 草稿与复核驳回备注、重新生成的补充指引、旁路顾问提问、Wiki 知识库查询、看板分解的子任务标题、智能体档案、AI 创建与提示词生成、批量目录提示词、技能派生、IM 的轮次 / 委派与进行中委派的转向 / 回合进行中记作上下文的群聊闲聊 / 系统命令 / 事件触发派发 / `/deny` 理由；续跑请求里审批的驳回理由与指引在聊天回合入口一并过闸）必须各调用自己的风险闸门，四个闸门（`check_stream_risk`、`_risk_refusal`、`reject_if_risky`、`hold_risky_inbound`）必须都以 `screen_user_text` 收尾；另扫描 `app/api` 全部 POST / PUT / PATCH 处理函数（请求模型含继承与嵌套），请求里带 `prompt` / `instruction` / `intent` / `objective` / `goal` / `message` / `question` / `answer` / `comment` / `modified_plan` 字段的必须登记或写入 `_EXEMPT`（附「文本不是给智能体照做的」理由；澄清、人工闸门与计划编辑的回答把智能体写的选项和用户键入的文字混在一起，审批 REST 的 `comment`、诊断工单的日志与任务时间线的打断指令都没有智能体读它，都按理由豁免），过期的豁免也失败；新增这类端点未登记即失败。没有调用方的路由（前端源码里没有能到达它的路径字面量，带动态段的 `/agents/chats/${id}/${kind}` 可以是同形状的任一路由，也没有登记的外部调用方；字面量与 `test_api_route_consumers.py` 共用，该门禁按「有无调用证据」严格读，这里按「能否排除有人调用」宽读）没有用户往里键入，不进该扫描，由路由消费者门禁要求删除或接上调用方，接上的那一刻起按普通端点扫描；豁免过期与否按未过滤的扫描判断；校准用例：已登记入口里一半以上读成无调用方即失败（前端若不写路径字面量，所有端点都会读成无调用方，扫描会空转）。有调用方的新端点（含工作区里他人未提交、已接上前端的）未登记会让该扫描变红，这是预期行为。AST 检查，并自带探测器与扫描器正反例自检 |
| `test_chat_scoped_vault_roots.py` | 服务端每处构造 `ArtifactVault` 的函数必须用 `resolve_chat_workspace_root` / `find_chat_workspace_root` 取会话根，否则登记进 `_ROOT_FROM_CALLER` 并写明根为什么已经对（运行内写入、调用方传入、清理目录）；过期登记也失败，并自带检测器正反例自检——读写根不一致时接口对刚生成的文件报 404、文件还会写进服务进程目录 |
| `test_git_spawn_sites.py` | 读取或改写索引、工作树与引用的 git 命令（`status`/`diff`/`add`/`commit`/`merge`/`checkout`/`worktree`/`branch`/`update-ref`…）一律经 harness 的 `hardened_git_argv`（仓库自己的配置能指定 git 运行的程序、钩子、过滤器、合并驱动、签名程序，部分克隆还能借惰性抓取联网），或登记在 `_BARE_GIT_SITES` 并写明理由；现登记项为空，已登记项消失即失败；自带扫描器正反例 |
| `test_event_writers_redact.py` | 在 `EventLogger` 之外自己构造 `StructuredEvent` 并直接写后端的服务端模块必须登记在 `_DIRECT_WRITERS` 并写明理由；登记项里带自由文本的（接管轨迹的页面状态）必须调用 `sanitize_event_data`；已登记项消失即失败 |
| `test_html_pages_contrast_gate.py` | 写整页 HTML 的 `app/` 模块（源码里有 `<!DOCTYPE html>` 或 `<html` 开标签）必须登记对应的对比度测试（文件须存在且真的调用 `assert_readable` / `assert_visible` / `contrast`，只导入不算），或列入 `_NOT_A_PAGE` 并写明它不展示页面的理由；登记项对应的模块不再写页面即失败，同一模块不得两边都登记；自带开标签探测器与「只导入不调用」的正反例自检 |
| `test_outbound_model_calls.py` | `app/` 内直接调用 litellm 对话接口的文件必须登记：要么先用 `sanitize_outbound_text` 脱敏（文件内须真有该调用），要么写明其文本不含对话内容的理由；否则隐私开关挡不住它。自带检测器正反例与过期登记检查 |
| `test_answer_text_consumers.py` | 每个 `process_stream` / `ai_agent_service_stream` 调用点必须归类：自己或其委托的协作者用 `AnswerDraft` / `StreamContentCollector` 拼装回复，或不拼装文本（语音、丢弃事件、网关出口，附理由），使恢复重启只替换在途段落；新增调用点未归类即失败，并自带探测器自检 |
| `test_agent_run_tracking.py` | 每个 `process_stream` 调用点必须登记：经 `AgentGateway.execute_stream`（计入 `activeCount`）或文件内 `with track_background_agent_run()`（计入 `backgroundRunCount`），否则托管空闲回收器会在该运行中途暂停沙箱；新增/删除调用点未登记即失败，并自带探测器正反例自检 |
| `test_memory_injection_contract_parity.py` | 前端 `MemoryBriefStatus(source)/MemoryBriefInjectionStatus` union 与 server+harness 状态契约严格同构 |
| `test_acp_sdk_dependency.py` | server 的 `myrm-agent-harness[...]` 依赖必须带 `acp` extra（外部智能体可配 `type: "acp"`，缺 SDK 会在首个 ACP 回合 ImportError），且 `agent-client-protocol<1` 约束保留（server 用 `prerelease = "allow"` 解析，否则会取到 1.0 候选版）|
| `test_settings_deep_links.py` | 前端源码、server 推送/提示、harness 诊断恢复按钮与预置技能资产里写死的 `/settings/<tab>` 深链必须落在前端路由 SSOT `settingsRoutes.ts`（`SETTINGS_TABS` ∪ `SETTINGS_TAB_REDIRECTS`）内，杜绝 404 死链 |
| `test_memory_brief_prometheus_rules_contract.py` | memory brief 告警规则契约（flush HTTP attempts-based ratio + strict dedup reject ratio/burst 关键片段；直接跑 pytest 时本地无 promtool 可 skip；`scripts/ci/run_architecture_gates.sh` 与 CI 均强制 promtool `check rules`） |
| `test_memory_brief_telemetry_layout.py` | memory brief CP 遥测须位于 `app/services/agent/memory_brief_telemetry/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_builtin_specs_layout.py` | 预置智能体规格须位于 `app/services/agent/builtin_specs/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_memory_guardian_guard_telemetry_layout.py` | memory guardian guard CP 遥测须位于 `app/services/agent/memory_guardian_guard_telemetry/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_marketplace_layout.py` | Agent Marketplace 导入/导出须位于 `app/services/agent/marketplace/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_app_package_init_layout.py` | `app/**` 含 `.py` 的目录须声明 `__init__.py`（禁止隐式 namespace 包） |
| `test_conversation_recall_layout.py` | Conversation Recall 仓储须位于 `app/database/repositories/conversation_recall/` 子包，禁止 repositories 根 legacy 平铺文件复活 |
| `test_e2ee_layout.py` | Mobile remote E2EE 须位于 `app/remote_access/e2ee/` 子包，禁止 remote_access 根 legacy 平铺文件复活 |
| `test_builtin_agent_i18n_parity.py` | 前端 `builtin-agent-i18n-data.ts` 的 key 集合须与 server `_BUILTIN_AGENTS` id 严格同构 |
| `test_blueprint_template_tools_parity.py` | 前端聊天配置面板 `BLUEPRINT_TEMPLATES`（JIT 一键编队）里每个成员的 `tools` 必须非空（空 = 继承父级全部工具）且都是 harness 注册的工具全名（`web_search` 这类界面名不会匹配任何工具，子智能体最后零工具）；自带扫描校准用例 |
| `test_cron_route_field_parity.py` | 定时任务 REST 的字段对齐：创建 schema 的每个字段都被 `create_job` 路由读取（唯一的登记例外 `override_prerequisite`：界面会发、服务端从不执行；该字段一旦被路由读取，登记即过期并失败），更新 schema 的每个字段都被 `update_job` 路由读取，`CronJobResponse` 的每个字段都由 `_to_response` 填写（路由漏转一个字段，设置会被接收、校验后丢弃）；自带校准用例证明读取器看得出被删掉的那一行 |
| `test_blueprint_fill_response_parity.py` | 蓝图填充响应的字段对齐：服务端 `BlueprintFillResponse` 的字段 == 前端 `cron.types.ts` 里 `BlueprintFillResponse` 接口的顶层字段（服务端多返回的字段前端读不到，蓝图的值被丢掉；前端多声明的字段读出来永远是 undefined，任务悄悄回落默认值）；前端源码不在检出里时跳过 |
| `test_channel_catalog_i18n_boundary.py` | server 渠道 JSON catalog 边界：键集 ⊆ 白名单、全语种同构、禁止 fork harness 诊断目录（SSOT） |
| `test_app_has_no_test_env_reads.py` | `app/**` 禁止读测试开关（`MYRM_E2E_*` / `MYRM_TEST_*` / `E2E_*`，豁免 pytest 自设的 `PYTEST_CURRENT_TEST`），也禁止读业务凭据类 env（`EMBEDDING_*` / `RERANKER_*` / `BASIC_*` / `LITE_*` / `TAVILY_*`）：前者让测试脚手架能改变生产语义，后者让「WebUI 配置」与「进程 env」两套来源并存（曾导致 FAQ 拦截在生产永远返回 None）。业务能力差异用 `DeploymentCapabilities` 语义位表达，凭据一律经 WebUI 配置注入 |
| `test_env_templates_have_no_dead_keys.py` | 三个已入库 env 模板（`.env.example` / `.env.test.example` / `.env.sandbox.example`）里的每个键必须在代码里有读者；无读者的键等于让维护者改一个永远不会生效的值（`BASELINE_SYNC_INTERVAL` 与 `RERANKER_*` 就是这样存活的）。扫描范围覆盖 server app/tests/scripts、harness src、仓库 scripts 与 Dockerfile/compose；`SettingsConfigDict(env_prefix=...)` 拼出的键与 compose 变量按前缀放行，不需要逐键白名单。自带路径存在性守卫（路径算错时直接失败而不是空扫通过）与反向用例（注入死键必须报红）|
| `test_catalog_category_locales.py` | 集成目录 API 返回的每个分类，六种语言的 `settings.integrationCatalog.categories` 都有显示名（目录页按 `categories.${id}` 动态取词，缺失会静默露出内部分类 id） |
| `test_storage_category_locales.py` | 存储占用台账能上报的每个类别（harness `StorageCategory`），六种语言的 `settings.storageGovernance.categories` 都有名称，且前端 `StorageCategoryKey` 与该枚举同构（治理卡按 `categories.${category}` 动态取词，缺失会静默露出原始消息键） |
| `../fixtures/frontend_sse_event_types.json` | 由 frontend `scripts/export-known-sse-event-types.ts` 生成 |
| `test_server_harness_imports.py` | 相对 baseline 禁止新增 server→harness 内部 import；禁止 import 含 ``._`` 的 harness 私有模块路径；并校验每个被 import 的 harness 模块在 harness 源包里**真实存在**（harness 单侧改名/移动时，服务端测试期即红，而不是等首个真实回合 `ImportError`） |
| `test_runtime_image_x11_tools.py` | 两个运行时镜像（`Dockerfile`、`docker/Dockerfile.official`）的 `apt-get install` 必须在 xdotool 旁同时装 xclip 与 x11-utils（含非 ASCII 字符的文本走 xclip 剪贴板粘贴，缺失则中日韩文本整体失败；`xprop`、`xdpyinfo` 来自 x11-utils，缺失则前台窗口类名为空、屏幕分辨率回退成错误的 1920x1080） |
| `test_dev_pid_path_ssot.py` | `scripts/**` 禁止读取子目录 `.myrm-dev-*` pid（cleanup rm 豁免） |
| `test_server_pyproject_lock_parity.py` | pyproject 主依赖/optional extras 与 uv.lock requires-dist 同构；harness 须为 in-repo editable path source，且 lock 不解析出平台 core 轮子包（`compiled-core` extra 里的需求声明不算）；lock 只含 `pypi.org`/`files.pythonhosted.org`；禁止 GPL/optional 包与 harness 已 pin 的 `litellm`/`langchain`/`langchain-core` 回流 main |
| `test_no_user_id.py` | 单机 server 禁止多租户 user_id 泄漏 |
| `test_no_private_references.py` | 开源仓全部已跟踪文本文件（不限 `*.md`）禁止出现私有开发壳的规划目录、名称、维护者速查文档名与 `topic_NN` 规划条目编号；一次 `git grep -I -i -E` 扫描（不区分大小写，目录名带不带斜杠都命中），编号用显式边界，紧贴中文的写法也命中；模式与样例由片段拼成，守卫文件不会命中自己；自带模式正反例自证；整树扫描另由不带路径过滤的 `.github/workflows/public-tree-guards.yml` 在每次 push main 与 PR 上独立运行（前端、桌面、脚本、根目录文档的改动同样被覆盖） |
| `test_no_provider_shaped_secrets_in_tests.py` | server 测试目录禁止出现完整的厂商格式凭据（Stripe 密钥、Slack token），否则 GitHub push protection 会拒绝整个推送；假值统一经 `tests/support/fake_secrets.py` 拼装。含守卫自检：正则必须仍能匹配夹具输出，避免扫描空转 |
| `test_arch_no_placeholder.py` | 产品树 `_ARCH.md` 禁止「见源码」等占位短语（含 `myrm-agent-extension/`） |
| `test_server_scripts_arch.py` | `myrm-agent-server/scripts/**` 子树必须有 `_ARCH.md` |
| `test_sync_arch_guard.py` | `sync_arch_file_tables.py` 不得覆盖已人工维护的 `_ARCH.md`（混合 stub/✅ 或多余章节） |
| `test_no_app_main_in_tests.py` | `tests/**` 禁止 AST 级 `import app.main`（须用 `build_minimal_app`） |
| `test_memory_search_declares_recall.py` | `app/**` 里每个 `manager.search(...)` 必须写明 `track_access`：检索默认把命中的记忆记为已使用（7 天内用过的记忆不被遗忘），取用类写 `True`，去重、诊断、存在性检查写 `False`；自带检测器正反例，接收者改名致扫描落空时失败 |
| `test_unit_test_layout.py` | 禁止 `tests/unit/**/api/`（与 `tests/api/` importlib 包名冲突） |
| `test_instance_archive_report_contract.py` | 整实例备份预览报告的计数键：服务端输出的键集 == 前端 `COUNT_KEYS`，且六种语言都有对应标签（前端缺标签或服务端改名都会失败） |
| `test_offline_persistable_keys_parity.py` | 前端离线队列可明文落盘的键（`offlinePersistableKeys.ts`）== 前端全部配置键减去服务端 `SENSITIVE_CONFIG_KEYS`：被加密的键不会写进 `localStorage`，新增非敏感键也不会静默丢失离线持久化 |
| `test_integrations_hardware_routes.py` | `/api/v1/integrations/hardware/*` 路由已注册（防 prefix 回归） |
| `test_frontend_api_client_paths.py` | 前端 `src/**` 调用必须命中真实路由：apiRequest/apiClient 字面量（路径+方法，含 `/webui`）；任意形式写出的 `/api/v1/...` 字面量（raw fetch、展示给用户的 webhook URL）须命中路由或路由基路径；`/api/<root>` 字面量的 root 须由 Next route handler、控制平面或渠道入口提供；已知缺失显式登记，路由出现后条目必须删除 |
| `test_api_routers_are_imported.py` | `app/api/**` 里每个定义了模块级 `APIRouter` 的模块都要被另一个 `app` 模块导入（含相对导入与字面量 `import_module`）：没有导入方就没有地方挂载它，里面的路由全部 404。不依赖前端是否写出过路径，补上路径门禁看不到的那一类；已导入但没传给 `include_router` 的情形不在它的范围内；带类型注解的赋值也算路由定义，扫描不到任何路由模块时直接失败，三个 `tmp_path` 用例钉住这两条与「有导入方则不报」 |
| `test_api_route_consumers.py` | 每个 API 路由都要有调用方：前端非测试源码里有路径字面量（任意调用形式，按路径而非方法匹配；`/webui/**` 额外按去掉挂载前缀匹配 `getWebuiUrl` 调用），或登记在 `data/route_external_consumers.txt`（每条写明调用方 file:line，被引用的行必须还写着这条路由，见 `test_route_evidence.py`）；存量无调用路由登记在 `data/route_consumer_baseline.txt`，只许缩小（路由已删除、已有调用方或已登记都会失败）；路由不得重复声明已挂载的 `/api/v1` 前缀。路由表、前端匹配与登记文件的读取在 `support/route_consumers.py`，风险闸门的用户文本入口扫描共用同一判定 |
| `data/route_external_consumers.txt` | 前端不调用、但有外部调用方的路由登记：`METHOD /path \| 调用方 (file:line)`，调用方不拼写路径时在括号里再写锚点文字 |
| `test_route_evidence.py` | 外部调用方登记里引用的 file:line 仍然有效：被引用的行拼写了路由最后一段静态路径（整词），或包含登记里写明的锚点；文件不存在、行号越界、引用格式不对都失败；检出里没有被引用的目录时跳过并如实计数，不算通过；校验函数的各分支（整词、锚点、越界、缺文件、跳过、多根目录）逐条钉住 |
| `data/route_consumer_baseline.txt` | 门禁引入前就没有调用方的存量路由；删路由或接上前端后必须同步删行 |
| `test_memory_router_mounts.py` | `app/api/memory/router.py` 里无条件挂载（对所有用户可见）的子路由必须登记在 `data/memory_default_mounts.txt`：新增路由要么收进 `settings.memory_labs_enabled` 开关，要么写明默认可见调用方 file:line；路由消费者门禁会把「只有隐藏面板的 service 引用」算作调用方，拦不住进程内演示引擎，所以单独把关。解析源码而非导入；写明的调用方必须是真实存在的非测试文件里的有效行号；自带检测器正反例自检 |
| `data/memory_default_mounts.txt` | 无条件挂载的记忆子路由台账：裸行是门禁引入前的存量，只许删除；`挂载名 \| 调用方 file:line` 是引入后经论证放行的新增 |
| `test_public_mutating_routes.py` | 变更类路由（POST/PUT/PATCH/DELETE）跳过认证中间件只有一种合法理由：handler 自己认证调用方；此类路由必须登记在测试内的表里并写明认证方式，未登记（例如公开前缀把运维动作一并放行）或登记后不再公开都会失败 |
| `test_openapi_operation_ids.py` | 全量公开 API 的 OpenAPI operationId 必须唯一：同一 (method, path) 重复注册（后者被静默遮蔽）或单个 `api_route` 挂多个 method 都会失败，一个路径只允许一个 handler |
| `test_openapi_schema_refs.py` | 公开 API 快照（`tests/support/public_api_app.py`，不含 `app/main.py` 直接挂载的内部/管理/兼容路由）的 OpenAPI 里每个 `#/components/schemas/…` 引用都必须在组件表里：请求或响应模型含任意类、生成不出 JSON schema 时，FastAPI 会放弃该组件却留下引用，`/openapi.json` 与 Swagger UI 就解析不了那个操作的请求体；只有服务端独自注入、客户端从不发送的字段才可以用 `SkipJsonSchema` 藏起来 |
| `test_api_services_vocabulary.py` | `app/api/` 与 `app/services/` 顶域分区 + 别名表与 `CONTRIBUTING.md` 同步 |
| `test_calendar_schema_retired.py` | 磁盘无 calendar ORM/API；`migrations.py` 尾部 DROP calendar_events 表/索引 |
| `test_project_legacy_workspace_migration.py` | `CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL` 须注册于 `MIGRATION_STATEMENTS` 尾部 |
| `test_migration_source_closure.py` | Wizard 封闭源集合：probe 导出 ≡ manifest 本地扫描 id ≡ loader 注册 |
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
| `test_telegram_channel_mixin_mro.py` | `TelegramChannel._pre_emit_hook` 必须来自 hooks mixin；inbound、inbound_message、inbound_poll 三个 mixin 不得定义同名方法（源码里 `TYPE_CHECKING` 下给类型检查器的声明不算）；MRO 中话题 mixin 先于 hooks mixin；`collect_issues` 必须来自诊断 mixin，而不是 `BaseChannel` 的默认实现 |
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
