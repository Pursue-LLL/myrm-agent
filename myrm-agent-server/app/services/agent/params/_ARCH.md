# app/services/agent/params 模块架构

Agent 参数转换层。将 HTTP 请求转换为 GeneralAgentParams，处理模型解析、API Key 查找、智能路由和配置组装。
Web 前端的 `enable_memory` 会在这里进入 Server 业务参数，统一控制记忆工具、历史会话召回和自动记忆提取开关。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `converter.py` | 核心 | HTTP 请求到 GeneralAgentParams：模型与密钥、JIT `workspace_dir`、网关全局 PAT 降级与工具配置注入、记忆开关、通过 `resolve_builtin_tool_flags()` 将 `enabled_builtin_tools` 统一映射为布尔 flag；`action_mode='fast'` 时动态限制工具集、设置 `prompt_mode="search"` 并按 `search_depth` 配置迭代限制。 | — |
| `models.py` | 核心 | Pydantic 请求模型（AgentRequest, ModelSelection, MentionReferenceRequest, ArchiveRestoreActionRequest, AgentConfigRequest 等），声明前端记忆开关、`search_depth`、GUI @ 结构化引用、typed archive restore action 契约以及 `tool_gateway_config`。 | — |
| `resolvers.py` | 核心 | 模型配置解析（ModelSelection → ModelConfig）；base URL 来自 selection 或 providers 行配置 | — |
| `providers.py` | 辅助 | 规范化 providerId、行匹配解析密钥；**仅** WebUI providers，无 env 回退；显式加载 `shared/config/provider_legacy_remap.json`（monorepo / Docker `/shared` / PyInstaller bundle / `MYRM_SHARED_CONFIG_ROOT`）；normalize 算法见 [shared/config/_ARCH.md](../../../../../shared/config/_ARCH.md) | ✅ |
| `mcp_selection.py` | 核心 | Per-agent MCP server+tool 过滤。`apply_agent_mcp_selection()` 按 `mcp_ids` 过滤服务器、按 `mcp_tool_selections` 注入 `tool_include`；`coerce_tool_selections()` 规范化原始元数据。被 converter/executor/agent_bridge/eval/custom_agent_factory 五个入口统一调用 | ✅ |
| `helpers.py` | 辅助 | 文本提取等辅助函数 | — |
| `media.py` | 辅助 | 多模态媒体参数处理 | — |
| `mention.py` | 辅助 | 上下文富引用预处理器。支持 workspace 文件/目录、上传/生成文件、@staged、@diff、@folder:path、@url:https://...，进行安全校验后注入用户查询 | ✅ |
| `upload_sync.py` | 辅助 | 上传文件 workspace 同步。将用户拖拽上传的大文件（>100KB）从 StorageProvider 复制到 `{workspace}/_uploaded/`，使 agent 的 file_read_tool 和 bash_tool 可直接访问完整文件内容。注入文件路径到 user query context | ✅ |

## Uploaded File Workspace Sync

- 前端通过 `AgentRequest.uploaded_file_ids` 传递本次消息附带的文件 ID 列表。
- `converter.py` 在 workspace 目录确定后调用 `sync_uploaded_files_to_workspace()`，将超过 100KB 的文件从 StorageProvider 复制到 `{workspace}/_uploaded/`。
- 文件路径以 XML 标签 `<uploaded_files_in_workspace>` 注入 user message 的 query context，不影响 system prompt 和 tool definitions 的 prompt cache 前缀。
- 安全保障：文件名清洗（去除路径分隔符和空字节）、50MB/chat 总量限制、10 文件/请求限制、同名文件自动编号。

## Typed Archive Restore

- `AgentRequest.archive_restore_actions` 接收前端结构化恢复动作，作为归档范围恢复的控制协议。
- `converter.py` 提供流式入口预校验和参数转换期校验：先校验 typed restore action，再持久化用户回合；单请求最多接收 3 个恢复范围，超过时返回结构化错误；校验成功才把恢复后的精确范围注入本轮 Agent 输入，并返回不含正文的 restore result 元数据供 SSE 结果卡片展示。
- 前端请求使用 snake_case `archive_restore_actions[].restore_arg`，Server Pydantic 模型接收后传入 harness 恢复上下文构建，不依赖 camelCase 边界字段。
