# api/agents 模块架构


---

## 架构概述

AI Agent 调用接口。提供统一的 SSE 流式对话接口（支持 fast/agent/deep_research/consensus 四种 action_mode），以及用户自定义智能体的 CRUD 管理。所有 Agent 执行通过 `AgentGateway` 统一管理并发和超时。快速搜索（fast 模式）通过 `converter.py` 的参数覆盖 + `prompt_mode="search"` 复用 GeneralAgent 统一路径，不再维护独立端点。相关辅助接口（追问建议、媒体验证、会话管理、澄清交互）按单一职责原则独立拆分为子模块。

**HITL 支持**：`general_agent.py` 支持 `resume_value` 参数，配合 LangGraph checkpointer 实现跨请求的 Human-in-the-Loop 审批流程。当 SSE 流中检测到 `TOOL_APPROVAL_REQUEST` 事件时，自动注册框架层超时守卫（`ApprovalTimeoutScheduler`），防止 Agent 因浏览器关闭或用户无响应而永久挂起。详细架构设计参见 [../myrm-agent-harness/src/myrm_agent_harness/agent/security/HITL_ARCHITECTURE.md](../../../myrm-agent-harness/src/myrm_agent_harness/agent/security/HITL_ARCHITECTURE.md)

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `params/`（`app/services/agent/params/`） | ✅ 核心 | Agent 参数转换层。Pydantic 请求模型 + 模型解析 + API Key 查找 + 智能路由 + `convert_to_general_agent_params` | ✅ |
| `general_agent/` | ✅ 核心 | 通用 Agent / Deep Research SSE 流式对话接口模块。拆分为 `streaming.py` (核心执行与 Fast Lane 极速通道拦截, 同时输出带 `metadata.error_type` 的结构化错误事件), `clarify.py` (澄清), `suggestions.py` (追问建议), `media_config.py` (媒体测试), `active_sessions.py` (会话状态)。支持 `resume_value` HITL 恢复 + 后端超时守卫 + 风险检查。集成了 `ResilientStreamBuffer` 彻底将大模型执行协程与 HTTP 返回流解耦，支持网络闪断后的无感续传，并**实现了 PWA 断连宽限生存引擎** (PWA Disconnect Tolerance Engine)，网络断开不直接杀任务，而是进入断连宽限池等待重连，彻底解决手机端 PWA 切换后台网络断开的强杀痛点。SSE 事件通过框架层 `AgentStreamEvent` 强类型包装 + `orjson` 高速序列化输出。 | ✅ |
| `streaming_schemas.py` | ✅ 核心 | SSE 通信协议封装层。定义 `SSEEnvelope` 模型，对上游流式事件执行严格的序列化校验，作为数据发送给前端前的防腐层。 | ✅ |
| `subagents.py` | ✅ 核心 | 子 Agent 控制 API（list/steer/cancel/resume）。`list` 合并 Harness `teammate_messages`（JSONL hydrate）；通过 `ACTIVE_SUBAGENTS` 与 `SubagentCheckpointStorage` 寻址，前缀 `/chats/{chat_id}/subagents` | ✅ |
| ~~`fast_search.py`~~ | ❌ 已删除 | 快速搜索已统一到 `general_agent/streaming.py`，通过 `action_mode="fast"` 走 GeneralAgent 路径 | — |
| `stream_collector.py` | ✅ 工具 | SSE 流事件收集器，收集 content + sources + progressSteps + usage + citedMemoryRefs + memoryRetrievalTraces 等，并维护全局 ACTIVE_COLLECTORS 字典，提供原子的 subscribe() 方法下发历史快照，实现无缝断线重连。 | ✅ |
| `agent.py` | ✅ 核心 | 用户自定义智能体 CRUD 管理。负责完整 Saved Agent schema 的创建/更新/读取/导入/导出/克隆，提供按需初始化的 secrets 路由，以及基于底层量化算法的全域动作空间与决策准确度评估接口 (`/evaluate-action-space`)。**配置安全网**：`GET /{agent_id}/snapshots` 列出快照（时光机 UI）；`POST /{agent_id}/rollback` 撤销最近一次 mutable 变更；`POST /{agent_id}/rollback/{snapshot_id}` 恢复到指定快照。`GET/PUT` 响应含 `snapshot_count`。 |
| `providers.py` | ✅ 核心 | 提供商操作 API。负责提供商依赖图的查询与管理，包括使用情况查询（`/{id}/usage`）、清理失效依赖（`/{id}/clear-usage`）以及基于一键迁移的批量换绑接口（`/batch-migrate`）。 | ✅ |
| `agent_history.py` | ✅ 辅助 | Prompt 版本审计列表（`GET /{agent_id}/history`），供聊天 Prompt 编辑器本地浏览；**非** rollback SSOT | ✅ |
| `generate_prompt.py` | ✅ 辅助 | 基于用户意图流式生成 Saved Agent 的 Markdown 系统提示词。与 Fast Search / Web Agent 一致：通过 `load_user_configs` + `resolve_model_config` 解析默认模型，经 `llm_manager.get_llm_from_config` 创建 LangChain LLM 后 `asteam` SSE。 | ✅ |
| `suggestions.py` | ✅ 核心 | 根据上下文自动生成 3 条追问建议（Suggestions endpoint） | ✅ |
| `clarification.py` | ✅ 核心 | 解析并回应 pending 的 Deep Research 澄清问询请求 | ✅ |
| `media.py` | ✅ 核心 | 测试媒体配置连通性（Image/Video 生成 API key 检测及 Provider 状态查询） | ✅ |
| `session.py` | ✅ 核心 | 活跃的 Agent 会话查询及通过消息 ID 主动取消 Agent 执行 | ✅ |
| `harness_router.py` | ✅ 核心 | Harness 框架层功能开放接口。包含 `/task-adaptive/recent` 获取最近的 JIT 上下文证据。 | ✅ |
| `openapi_services.py` | ✅ 核心 | OpenAPI 服务管理 API。提供规范解析预览 (`/parse-spec`) 和连通性测试 (`/test-request`) 端点，供前端在保存前验证 OpenAPI 配置。 | ✅ |
| `templates.py` | ✅ 核心 | Agent 模板 API。列出（含 team 成员/场景摘要）和实例化预配置模板。支持 individual 和 team 两种类型：team 模板原子创建所有成员 + leader，失败时完整回滚。 | ✅ |
| `routing_api.py` | ✅ 核心 | 暴露智能路由健康度检查端点（`/provider-health`） | ✅ |

---

## 内置工具配置链路

前端通过 `AgentConfigRequest.enabled_builtin_tools: list[str]`（默认 `["web_search"]`）统一控制所有内置工具的启停。Channel 消息通过 `agent_id` 路径从数据库加载 `Agent.enabled_builtin_tools`。`convert_to_general_agent_params()` 将其转换为 `GeneralAgentParams` 中的独立布尔字段（`enable_web_search`、`enable_browser`），并传递给 `_extract_media_generation_params()` 判断是否启用图片/视频生成。

**搜索服务未配置防护**：`enable_web_search` 还受 `search_is_user_configured` 影响——若用户未配置任何搜索服务，即使 `enabled_builtin_tools` 包含 `"web_search"` 也会被设为 `False`，防止 Agent 注册不可用的搜索工具。对于 Deep Research 模式（搜索是核心能力），`streaming.py` 在流创建前额外检查 `params.enable_web_search`，若为 `False` 直接返回 422 快速失败。

## 模型解析策略

所有入口点遵循统一的模型优先级，确保用户认知与后端行为一致（无隐式 fallback）：

**模型选择优先级**：`智能体配置的 model` > `前端传入 / job 指定的 model` > `用户默认 model (defaultModelConfig)` > `resolve_model_config(providers_dict)` > `ConfigIncompleteError`（**禁止**进程 env 回退）

**凭据解析**：`agent_params/providers.py` 仅在用户 `providers_dict.providers` 中按 **`id`/`routingProfile`** 匹配密钥与 base URL；缺失则 `ConfigIncompleteError`，不读 `BASIC_*`/`LITE_*` 环境变量。

- **Web (`converter.py`)**：`request.model_selection` > `resolved.model`（安全网）> `resolve_model_config()`
- **Channel (`executor.py`)**：`resolved_profile.model` > `configs.model_cfg`
- **Cron (`agent_runner.py`)**：`resolved.model` > `job.model` > `resolve_model_config()`
- **Eval (`executor.py`)**：`resolved.model` > `configs.model_cfg`

`model_resolver._fallback_model_from_providers()` 不再包含"第一个 enabled provider"的隐式 fallback。

## 媒体生成配置链路

`_extract_media_generation_params()` 接收 `enabled_builtin_tools: list[str]` 参数。当 `"image_generation"` / `"video_generation"` 在列表中时，从用户的 `personalSettings`（DB 中的 ConfigSync 配置）提取 Provider/Model 配置，构建 `ImageGenerationParams` / `VideoGenerationParams` 传递给 `GeneralAgentParams`。前端 camelCase 键自动转换为后端 snake_case。

API Key 自动传递：若媒体生成参数中未显式指定 `api_key`，`_find_provider_api_key()` 仅在用户 `providers_dict.providers` 中匹配 **`id`/`routingProfile`**；无命中则报错，不回退 env。`ModelSelection.provider_id` 由 **`normalize_storage_provider_id`** 规范化。

配置验证：`POST /test-media-config` 端点支持验证 API Key 有效性和 video provider 连通性（调用框架层 `health_check`）。

---

## 自定义 Agent CRUD 与 Secrets

`agent.py` 负责两类接口：

1. **Agent CRUD**：创建、更新、删除、详情、列表、头像上传、统计、导入、导出、克隆（全量蓝图 JSON 序列化/反序列化，剥离隐私信息）。克隆接口 (`POST /{agent_id}/clone`) 复用导出+创建逻辑，自动清除 `home_directory` 防止目录共享，并重置 `home://` 开头的头像引用。
2. **Agent Secrets**：列出 secret 名称、写入 secret、删除 secret。

### Saved Agent 完整 schema

CRUD 路由不只处理基础字段，还会透传并回显以下运行时字段：

- `model_selection`
- `enabled_builtin_tools`
- `subagent_ids`
- `security_overrides`
- `personality_style`
- `max_iterations`
- `workspace_policy`
- `memory_policy`

### Vault 按需初始化

Secrets 路由不再在模块导入期初始化 `DatabaseSecretBackend`。  
当前策略是：

- 普通 Agent CRUD 即使在 vault 未解锁时也必须可用。
- 只有访问 secrets 路由时，才按需初始化 secret backend。
- 如果 vault 未解锁，则 secrets 路由返回 `423 Locked`，提示用户先注入 `MYRM_MASTER_KEY`、使用 OS keyring，或通过 `/api/security/vault/unlock` 解锁。

### 配置快照与时光机 API

WebUI 是唯一 Agent 配置修改入口。每次 **mutable 字段**变更保存前，`AgentService` 委托 `ProfileSnapshotService` 自动创建快照（最多保留 10 条；仅改 avatar 不 snapshot）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/user-agents/{agent_id}/snapshots?limit=10` | 列出快照历史，供 `AgentProfileTimeMachine` |
| `POST` | `/api/v1/user-agents/{agent_id}/rollback` | 撤销最近一次 mutable 变更（预览卡「撤销」） |
| `POST` | `/api/v1/user-agents/{agent_id}/rollback/{snapshot_id}` | 恢复到指定快照（时光机按版本恢复） |

- 回滚前自动写入 `pre-rollback` 保险快照。
- `GET /{agent_id}` 与 `PUT /{agent_id}` 响应含 `snapshot_count`；`PUT` 另含 `snapshot_saved`（mutable 变更前快照是否写入成功），前端据此 warning toast。

---

## Gateway 异常处理

所有 Agent 端点统一处理 `AgentGateway` 和 `AgentBusyError` 异常：
- `AgentQueueTimeout` → SSE error，携带异常消息（含并发或内存压力等级信息），例如 "Queue timeout (10s) — Memory pressure (CRITICAL)" 或 "Queue timeout (10s) — active=20/20"
- `AgentExecutionTimeout` → SSE error "Request timed out."
- `AgentBusyError` → 转换为 409 状态码的 SSE error "Agent is busy processing another request for this session."，前端据此将消息退回队列。

---

## 依赖关系

- `app/services/agent/gateway.py`：AgentGateway（并发控制、超时）
- `app/services/agent/streaming.py`：General Agent / Deep Research 流式服务
- `app/ai_agents/`：Agent 配置和创建
- `app/api/dependencies.py`：认证依赖注入
