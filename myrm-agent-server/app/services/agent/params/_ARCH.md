# app/services/agent/params 模块架构

Agent 参数转换层。将 HTTP 请求转换为 GeneralAgentParams，处理模型解析、API Key 查找、智能路由和配置组装。
Web 前端的 `enable_memory` 会在这里进入 Server 业务参数，统一控制记忆工具、历史会话召回和自动记忆提取开关。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `archive_restore.py` | 核心 | Typed archive restore 校验与 prompt 物化（`prevalidate_archive_restore_actions`、XML 注入） | ✅ |
| `workspace_resolve.py` | 辅助 | Chat 级 harness workspace JIT 解析、DB 回写与 Agent 模板物料（`template_workspace_files`，存储格式与释放逻辑见 `services/plugins/template_workspace.py`）安全解压；纯路径函数 `default_chat_workspace_path` / `default_workspaces_root` 不落盘，供 Context Guard 在新会话（尚无 DB 行）把超长提示词溢出到 Agent 实际所在 workspace，并作为 spillover 清扫根目录 | ✅ |
| `converter.py` | 核心 | HTTP 请求到 GeneralAgentParams 主编排：模型分流与归因解析（返回 6 元组含 `routing_reason`；无 `regenerate_instruction` 的 sibling 重试即 complaint-up 升档（经 `complaint_floor()` 只爬到换了模型配置的档位，无处可爬时原因记 `retry_floor_held`），深度研究只采纳 REASONING 判定，其余判定丢弃且不记档位与原因，决策日志含 `routing_ms`）；`regenerate_instruction` 在 fast / agent 两种模式下都作为 `[Regeneration guidance: …]` 追加到 user_instructions；personality_style 与 **response_locale_policy** 经 `profile_output_suffixes.apply_profile_output_suffixes` 追加至 user_instructions 末尾；请求级安全覆盖（会话预设、远程准入、/learn 授权）装配为 `SecurityOverlaySpec` 随参数下发，在 learn 重写之后一次性 `apply` 到已保存的 securityConfig（实现见 `core/security/session_overlay.py`）。 | — |
| `profile_output_suffixes.py` | 核心 | `apply_profile_output_suffixes()` — personality + harness `build_response_locale_suffix` 注入 instructions 尾（Web/Channel/Cron/Kanban/Eval/Voice×3/Subagent/Goal stream SSOT）。 | ✅ |
| `models.py` | 核心 | Pydantic 请求模型（AgentRequest, ModelSelection, …），含 `use_workflow`、`workflow_template_id`、`workflow_template_args`（pinned DW rerun）、前端记忆开关、`search_depth`、`reasoning_display_mode`、`active_moa_preset_id`、GUI @ 结构化引用、archive restore、`kanban_default_board_id`、`tool_gateway_config`、`turn_capability_telemetry`、`security_preset`。 | — |
| `resolvers.py` | 核心 | 模型配置解析（ModelSelection → ModelConfig）；base URL 来自 selection 或 providers 行配置 | — |
| `routing_memory.py` | 核心 | Smart Routing 的跨请求记忆：`load_recent_routing()` 把持久化的 `routingTier` 历史按 `RoutingTier` / `TaskSpecialty` 分流为 complexity 动量与 specialty 动量输入；`load_retry_baseline()` 读出被重试回合自己持久化的档位（该回合最新一条记了档位的回答，回合末尾系统自己追加的行——后台任务完成通知、auto-continue——不算回答；没有记档位的回答即跑的是主模型），`complaint_floor()` 以它为基线（缺省按 STANDARD），给出重试的档位下限及其是否换了模型配置；`remember_turn_routing()` / `resolve_turn_routing()` 记住用户回合的路由结果（以不含密钥的 `ModelSelection` 保存，resume 时重新解析凭据），HITL resume 沿用被中断回合的模型而非重新路由空 query | ✅ |
| `providers.py` | 辅助 | 规范化 providerId、行匹配解析密钥；**仅** WebUI providers，无 env 回退；显式加载 `shared/config/provider_legacy_remap.json`（monorepo / Docker `/shared` / PyInstaller bundle / `MYRM_SHARED_CONFIG_ROOT`）；normalize 算法见 [shared/config/_ARCH.md](../../../../../shared/config/_ARCH.md) | ✅ |
| `mcp_selection.py` | 核心 | Per-agent MCP server+tool 过滤。`apply_agent_mcp_selection()` 按 `mcp_ids` 过滤服务器、按 `mcp_tool_selections` 注入 `tool_include`；`coerce_tool_selections()` 规范化原始元数据。被 converter/executor/agent_bridge/eval/custom_agent_factory 五个入口统一调用 | ✅ |
| `helpers.py` | 辅助 | 文本提取等辅助函数；`_requested_privacy_params` 提取请求自带的隐私字段（converter 再与已保存设置合并：请求写明的优先，没说的跟随设置）；`_declared_capabilities` 合并多份安全配置里声明的能力名 | — |
| `media.py` | 辅助 | 多模态媒体参数处理 | — |
| `mention.py` | 辅助 | 上下文富引用预处理器。支持 workspace 文件/目录、上传/生成文件、@staged、@diff、@codebase、@folder:path、@url:、@wiki:、**prior_chat (@chat:)**，进行安全校验后注入用户查询 | ✅ |
| `upload_sync.py` | 辅助 | 上传文件 workspace 同步与 RAG 智能路由。将用户拖拽上传的大文件（>100KB）从 StorageProvider 复制到 `{workspace}/_uploaded/`。大型文档（PDF/DOCX >100KB）自动标记 `action="wiki_ingest_then_query"`，引导 Agent 使用 wiki_ingest + wiki_query 进行 RAG 检索而非全文读取 | ✅ |

## Uploaded File Workspace Sync

- 前端通过 `AgentRequest.uploaded_file_ids` 传递本次消息附带的文件 ID 列表。
- `converter.py` 在 workspace 目录确定后调用 `sync_uploaded_files_to_workspace()`，将超过 100KB 的文件从 StorageProvider 复制到 `{workspace}/_uploaded/`。
- 归档恢复：`archive_restore.py` 校验 `archive_restore_actions` 并注入 XML；`converter.py` 在参数转换期调用。
- 文件路径以 XML 标签注入 user message 的 query context，不影响 system prompt 和 tool definitions 的 prompt cache 前缀：
  - 普通文件：`<uploaded_files_in_workspace>` 标签，Agent 可直接读取
  - 大文档（PDF/DOCX >100KB）：`<large_documents_for_knowledge_base>` 标签，引导 Agent 使用 wiki_ingest_tool 入库后用 wiki_query_tool 检索
- 安全保障：文件名清洗（去除路径分隔符和空字节）、50MB/chat 总量限制、10 文件/请求限制、同名文件自动编号。

## @codebase Mention

- 前端 `@codebase` 经 `MentionReferenceRequest(type="codebase")` 进入 `mention.py::_codebase_overview_part`。
- Server 侧 **轻量 os.walk 扫描**（无 SQLite/FTS/向量索引），输出文件数与扩展名分布，并提示 Agent 使用 `grep_tool` / `glob_tool` 探索代码。
- 注入 XML 类型为 `codebase-overview`；扫描上限 10,000 文件，排除 `.git`、`node_modules`、`.myrm` 等目录。
- 工作区代码探索 SSOT 仍为 harness `FilesystemFileSearchMiddleware`（grep/glob），见 `app/services/context/_ARCH.md`。

## prior_chat (@chat:) Mention

- 前端 `@chat:` 经 `MentionReferenceRequest(type="prior_chat")` 进入 `mention.py::_prior_chat_part`，从 FTS recall 索引注入 summary+snippet。
- `@chat:` picker 走 `GET /chats/recall/search`（conversation_recall SSOT，与 inject 同索引）；Cmd+K 仍走 `/chats/search` 消息级发现。
- `mention.py::_prior_chat_part` 在 recall doc 缺失时 lazy `rebuild_chat`；错误码区分 unavailable / excluded / incognito；incognito 只拒绝网页无痕会话（`source == "web"`），外部转录导入的会话借用无痕标记只为不进侧栏，选择器会列出它，引用同样放行。
- `converter.py` 在 workspace 尚未就绪时仍注入 `prior_chat`；file/workspace 引用跳过并写入 warning。prior_chat 路径不使用 workspace 内容，fallback 见 `mention.py::_MENTION_PRIOR_CHAT_FALLBACK_WORKSPACE`。
- 注入 append 到 user query 的 `<mentioned_files>`，不修改 system prompt / tool schema（prompt cache 安全）。

## artifact_range Mention

- 前端表格/文档选区经 `MentionReferenceRequest(type="artifact_range")` 协议接受，`range`（范围标签）与 `content`（选区文本，字段级 500KB 上限）由前端产点直传。
- `mention.py` 消费分支：content 存在且满足 inline 预算（100KB 单条 + 500KB 总量）时以 `type="artifact-range"` XML 注入选区内容；content 缺失降级 `empty selection` error 标签；超预算输出 too-large 元数据标注。

## Typed Archive Restore

- `AgentRequest.archive_restore_actions` 接收前端结构化恢复动作，作为归档范围恢复的控制协议。
- `archive_restore.py` 提供流式入口预校验；`converter.py` 参数转换期物化并注入 query。单请求最多 3 个恢复范围；校验成功才把精确范围注入本轮 Agent 输入，并返回不含正文的 restore result 元数据供 SSE 结果卡片展示。
- 前端请求使用 snake_case `archive_restore_actions[].restore_arg`，Server Pydantic 模型接收后传入 harness 恢复上下文构建，不依赖 camelCase 边界字段。

## General Agent tool loading（非 fast Web、Channel/IM）

- **轨道**：默认 Saved Agent、Channel/IM/Cron/Kanban/Eval/Voice 等非 fast Web 入口。
- **CORE file/bash**：Harness `tool_layers.py` CORE 层 Turn1 eager；前端无开关。
- **Server 执行层**：`resolve_builtin_tool_flags()` 后调用 `tool_mount.resolve_agent_mount()`，再传入 harness `get_meta_tools`。
- **Web Search 动态配置与弹性激活**：当 `enabled_builtin_tools` 包含 `web_search` 且初始未拿到搜索配置时，`converter.py` 主动触发 `invalidate_user_configs_cache()` 与 `reload_user_configs()` 刷新配置；一旦存在有效搜索配置，保障 `search_available=True` 注入，避免因即时网络探测延迟或 TTL 探针抖动导致 `web_search_tool` 被误剥离。
- **Channel/IM**：仅绑定 General Agent（`SqlTopicManager.bind_topic` 拒绝 `prompt_mode=search`；`resolve_topic` / `get_all_topics` 读时清除 legacy Search 绑定）；未绑定时 `DEFAULT_ENABLED_BUILTIN_TOOLS` + baseline。
- **persist 语义**：`enabled_builtin_tools` 不含 `file_ops` / `code_execute`；写入 DB 时 strip baseline ID。

## Search/Fast（Web `action_mode=fast`）

- **唯一无 file/bash 的入口**：`converter.py` 在 `action_mode=fast` 时 `resolve_agent_mount(WEB_FAST, …)`，设 `prompt_mode=search`。仍挂载 **UECD 只读** `file_read_tool`（`.context/{chat_id}/evicted/` + `_uploaded/`），不挂载 write/edit/glob/grep/bash。
- Quick Search / Deep Search 预置 Agent（`builtin_specs/search.py`）供 Web UI 选用；非 fast Web 聊天仍加载 General CORE，仅 prompt/skills 走 search 语义。

## Fast Search（`action_mode='fast'`）

- `converter.py` 覆盖 Agent profile 的 `enabled_builtin_tools` 为 `["answer_tool"]`，并强制 `enable_web_search=True`；skills / MCP / subagents / 媒体生成置空。
- Normal 与 Deep 共享同一 builtin 开关集；`search_depth=deep` 仅追加 `SEARCH_DEEP_SUFFIX` prompt、`tool_setup` 内 SufficiencyConfig，以及更高的 `max_tool_calls` / `max_iterations`。
- Turn1：`web_search_tool`、`web_fetch_tool`、记忆三件套（`enable_memory` 且非无痕，COMMON 层）；`file_read_tool`（UECD 只读，读 evicted spill + `_uploaded/`）；`request_answer_user_tool`（`answer_tool` opt-in，EXTENDED 层）。历史会话搜索不单独 bind 工具：`memoryEnableConversationSearch=true` 时在 `memory_search_tool` 上启用 `corpus=sessions` ACL。**不默认 bind browser**；browser 仅当用户选用带 `browser` 开关的 Agent profile 时加载。
- Browser 开启时，`browser-automation` peripheral skill 在 `AgentFactory.create_general_agent` 合并（非 converter），保证 Cron/Channel/Kanban 与 Web 一致；`prompt_mode="search"` 跳过绑定。
- SSOT：`myrm-agent-server/app/services/agent/builtin_specs/builtin_tool_ids.py`（全局默认 4 项开关）；Fast 模式运行时覆盖见 `converter.py`。

## 隐身会话（incognito）

- `converter.py` 在 `incognito_mode` 下把 `enable_wiki` 置为 False，与会话检索、记忆自动提取的隐身归一在同一处完成。Wiki 工具、长回复自动归档、压缩后归档、深度研究入库都以 `params.enable_wiki` 为开关，转换器是这几个开关在隐身下归一的唯一收口点。
- 隐身会话的消息与普通会话一样落本地库：标题与消息预览不存（`chat_repo.py`），侧栏、搜索、召回、追赶收件箱与记忆导出都排除它，闲置满 1 小时由 `services/chat/chat_retention.py` 永久删除。

## Smart Routing（converter.py）

- 触发条件：`light_model_selection` / `reasoning_model_selection` 任一存在时调用 harness `route_task`，三档模型路由（SIMPLE / STANDARD / REASONING），产物覆盖 `model_cfg` / `fallback_model_cfg` 并返回 `routing_tier`。
- 两阶段判定（引擎语义 SSOT 见 `myrm-agent-harness/.../toolkits/llms/routing/_ARCH.md`）：规则评分优先；规则无法判定时走 **LLM judge**。judge 模型取自 `lite_model_selection` 解析出的 `lite_model_cfg`，经 `llm_manager.get_llm_from_config(lite_model_cfg.model_copy(update={"temperature": 0.0}))` 创建 —— 只传 config 一个位置参数，`api_keys` / `credential_pool_strategy` 由 manager 内部从 `ModelConfig` 字段自动提取；judge 是**确定性判定角色**，创建时固化低温 0.0（与 harness 评估器一致，保证分类稳定），`temperature` 走「顶层优先合并 model_kwargs」统一语义。
- 深度研究：只采纳 `route_task` 的 REASONING 判定，SIMPLE / STANDARD 判定丢弃，规划与报告撰写保持默认模型（研究报告是交付物，且研究课题天然短，规则会把它们误判为 SIMPLE）。被丢弃的判定不持久化档位与原因：路由没有选择本回合的模型，所以下一回合的重试从主模型起爬，研究子 agent 跑在 light 模型上的 token 也不会混进统计里的 standard 档而拉偏其单 token 价（节省估算以它为基线）；研究子 agent 的 light 模型由 `orchestrator_turn_body` 独立解析，REASONING 升档照常生效并记录档位。
- 可观测：每次路由决策的 `Smart routing:` 日志含 `routing_ms`（`route_task` 耗时，含 judge 调用）。
- 降级策略：judge 创建失败仅回退规则路由（`logger.warning` 可观测，不阻断主流程）；整个路由块异常时回退默认模型并 `logger.warning`。
- 会话动量与纠偏：`chat_id` 历史档位供 momentum 与 complaint-up 升级（无指令的 regenerate 抬档；带指令的 regenerate 不升档）；重试只抬高本回合的档位下限，不向任何全局状态写入惩罚。抬档由 `routing_memory.complaint_floor()` 决定：自动挑选的 light / reasoning 槽位不排除主模型，名义上的下一档可能就是刚答过的那个模型，所以从被重试回合的回答自己持久化的档位起（`routing_memory.load_retry_baseline()` 取该回合最新一条记了档位的回答，回合末尾系统自己追加的行不算回答、会被跳过；该回合没有任何记档位的回答——fast 模式、固定模型、未升档的深度研究——即跑的是主模型，按 STANDARD 起），跳到第一个模型配置（model / base_url / temperature / reasoning_effort / model_kwargs / wire_protocol，不含密钥与上下文窗口）与上一答案不同的档位；已无更强档位时下限停在上一档，原因由 `min_tier_escalation(...)` 改写为 `retry_floor_held`（前端对未知原因不展示，不会谎称“已升级”）；无历史时同样从 STANDARD 起。`routingTier` 列同时存放 complexity 档位与 specialty 槽位命中值，`routing_memory.load_recent_routing()` 按枚举分流后分别传给 `route_task(recent_tiers=)` 与 `route_task_specialty(recent_specialties=)`。
- HITL resume 连续性：审批 / 计划确认的 resume 请求体只带主模型选择、不带路由槽位，若重新路由会让被中断回合在另一个模型上继续（provider 缓存按模型隔离，等于冷缓存）。`orchestrator_turn_body` 在每个非 resume 用户回合后调用 `remember_turn_routing()`；converter 遇到 `resume_value` 时经 `resolve_turn_routing()` 复用该回合的模型、fallback、档位与原因并跳过两段路由。记忆为进程内 LRU（与 `ApprovalTimeoutScheduler` 同一单进程假设），主模型选择变化、记忆缺失或槽位模型不可解析时退回重新路由。prewarm / wakeup / OpenAI 兼容入口不读写该记忆。
