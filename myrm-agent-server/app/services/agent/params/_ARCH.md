# app/services/agent/params 模块架构

Agent 参数转换层。将 HTTP 请求转换为 GeneralAgentParams，处理模型解析、API Key 查找、智能路由和配置组装。
Web 前端的 `enable_memory` 会在这里进入 Server 业务参数，统一控制记忆工具、历史会话召回和自动记忆提取开关。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `converter.py` | 核心 | HTTP 请求到 GeneralAgentParams：模型与密钥、JIT `workspace_dir`、`tool_gateway_config` 组装（无 auth_token 时禁用 gateway）、记忆开关、通过 `resolve_builtin_tool_flags()` 将 `enabled_builtin_tools`（含 `render_ui`→`enable_render_ui`、`planning`→`enable_planning`、`answer_tool`→`enable_answer_tool`、`cron`→`enable_cron_eager`）统一映射为布尔 flag；`action_mode='fast'` 时覆盖 `enabled_builtin_tools` 为 `["answer_tool"]`、强制 `enable_web_search=True`、清空 skills/MCP/subagents，设置 `prompt_mode="search"`；`search_depth` 仅影响 SufficiencyConfig、prompt 后缀与迭代/tool-call 上限（**不加载 browser**）。 | — |
| `models.py` | 核心 | Pydantic 请求模型（AgentRequest, ModelSelection, MentionReferenceRequest, ArchiveRestoreActionRequest, AgentConfigRequest 等），声明前端记忆开关、`search_depth`、GUI @ 结构化引用、typed archive restore action 契约以及 `tool_gateway_config`。 | — |
| `resolvers.py` | 核心 | 模型配置解析（ModelSelection → ModelConfig）；base URL 来自 selection 或 providers 行配置 | — |
| `providers.py` | 辅助 | 规范化 providerId、行匹配解析密钥；**仅** WebUI providers，无 env 回退；显式加载 `shared/config/provider_legacy_remap.json`（monorepo / Docker `/shared` / PyInstaller bundle / `MYRM_SHARED_CONFIG_ROOT`）；normalize 算法见 [shared/config/_ARCH.md](../../../../../shared/config/_ARCH.md) | ✅ |
| `mcp_selection.py` | 核心 | Per-agent MCP server+tool 过滤。`apply_agent_mcp_selection()` 按 `mcp_ids` 过滤服务器、按 `mcp_tool_selections` 注入 `tool_include`；`coerce_tool_selections()` 规范化原始元数据。被 converter/executor/agent_bridge/eval/custom_agent_factory 五个入口统一调用 | ✅ |
| `helpers.py` | 辅助 | 文本提取等辅助函数 | — |
| `media.py` | 辅助 | 多模态媒体参数处理 | — |
| `mention.py` | 辅助 | 上下文富引用预处理器。支持 workspace 文件/目录、上传/生成文件、@staged、@diff、@codebase（轻量文件统计 + grep/glob 引导）、@folder:path、@url:https://...，进行安全校验后注入用户查询 | ✅ |
| `upload_sync.py` | 辅助 | 上传文件 workspace 同步与 RAG 智能路由。将用户拖拽上传的大文件（>100KB）从 StorageProvider 复制到 `{workspace}/_uploaded/`。大型文档（PDF/DOCX >100KB）自动标记 `action="wiki_ingest_then_query"`，引导 Agent 使用 wiki_ingest + wiki_query 进行 RAG 检索而非全文读取 | ✅ |

## Uploaded File Workspace Sync

- 前端通过 `AgentRequest.uploaded_file_ids` 传递本次消息附带的文件 ID 列表。
- `converter.py` 在 workspace 目录确定后调用 `sync_uploaded_files_to_workspace()`，将超过 100KB 的文件从 StorageProvider 复制到 `{workspace}/_uploaded/`。
- 文件路径以 XML 标签注入 user message 的 query context，不影响 system prompt 和 tool definitions 的 prompt cache 前缀：
  - 普通文件：`<uploaded_files_in_workspace>` 标签，Agent 可直接读取
  - 大文档（PDF/DOCX >100KB）：`<large_documents_for_knowledge_base>` 标签，引导 Agent 使用 wiki_ingest_tool 入库后用 wiki_query_tool 检索
- 安全保障：文件名清洗（去除路径分隔符和空字节）、50MB/chat 总量限制、10 文件/请求限制、同名文件自动编号。

## @codebase Mention

- 前端 `@codebase` 经 `MentionReferenceRequest(type="codebase")` 进入 `mention.py::_codebase_overview_part`。
- Server 侧 **轻量 os.walk 扫描**（无 SQLite/FTS/向量索引），输出文件数与扩展名分布，并提示 Agent 使用 `grep_tool` / `glob_tool` 探索代码。
- 注入 XML 类型为 `codebase-overview`；扫描上限 10,000 文件，排除 `.git`、`node_modules`、`.myrm` 等目录。
- 工作区代码探索 SSOT 仍为 harness `FilesystemFileSearchMiddleware`（grep/glob），见 `app/services/context/_ARCH.md`。

## Typed Archive Restore

- `AgentRequest.archive_restore_actions` 接收前端结构化恢复动作，作为归档范围恢复的控制协议。
- `converter.py` 提供流式入口预校验和参数转换期校验：先校验 typed restore action，再持久化用户回合；单请求最多接收 3 个恢复范围，超过时返回结构化错误；校验成功才把恢复后的精确范围注入本轮 Agent 输入，并返回不含正文的 restore result 元数据供 SSE 结果卡片展示。
- 前端请求使用 snake_case `archive_restore_actions[].restore_arg`，Server Pydantic 模型接收后传入 harness 恢复上下文构建，不依赖 camelCase 边界字段。

## Fast Search（`action_mode='fast'`）

- `converter.py` 覆盖 Agent profile 的 `enabled_builtin_tools` 为 `["answer_tool"]`，并强制 `enable_web_search=True`；skills / MCP / subagents / 媒体生成置空。
- Normal 与 Deep 共享同一 builtin 开关集；`search_depth=deep` 仅追加 `SEARCH_DEEP_SUFFIX` prompt、`tool_setup` 内 SufficiencyConfig，以及更高的 `max_tool_calls` / `max_iterations`。
- Turn1：`web_search_tool`、`web_fetch_tool`、`request_answer_user_tool`、记忆三件套（`enable_memory` 且非无痕，COMMON 层）；`conversation_search_tool` 仅 `memoryEnableConversationSearch=true` 时装载（EXTENDED）。**不默认 bind browser**；browser 仅当用户选用带 `browser` 开关的 Agent profile 时加载。
- SSOT：`myrm-agent-server/app/services/agent/builtin_tool_ids.py`（全局默认 4 项开关）；Fast 模式运行时覆盖见 `converter.py`。
