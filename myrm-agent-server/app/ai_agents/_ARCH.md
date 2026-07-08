# ai_agents 模块架构


---

## 架构概述

AI Agent 定义层。基于 myrm-agent-harness 的基础能力，配置和组装业务 Agent。
以 GeneralAgent 为核心，搜索能力通过 `prompt_mode="search"` 走 GeneralAgent 路径，享有 SkillAgent 记忆与 PWA 断连恢复。共享提示词与中间件由 `prompts/` 和 `agent_middlewares/` 提供。
其中与“用户当前在解决什么任务”直接相关的语义推断保留在本层，
例如 GeneralAgent 生成并注入 `compression_intent`，把聚焦文件、模块、用户目标和失败工具调用等信号
交给 harness 执行通用上下文压缩。

---

## 模块加载策略

**两层延迟加载**防止启动时导入 litellm/langchain 等重型依赖：
1. `__init__.py` 使用 PEP 562（`__getattr__`），避免 `from app.ai_agents import X` 触发模块级加载
2. `agents.py` 中 `GeneralAgent` 在 `AgentFactory.create_*()` 工厂方法内延迟导入，避免 `__getattr__` 解析 `GeneralAgentParams` 时连带加载 Agent 类

## 文件清单

| 文件/目录 | 地位 | 职责| I/O/P |
|----------|------|------|-------|
| `__init__.py` | ✅ 核心 | PEP 562 延迟加载入口 | ✅ |
| `agents.py` | ✅ 核心 | AgentFactory 统一创建入口（Agent 类延迟导入），含 ImageGenerationParams / VideoGenerationParams（支持 api_key 传递）、GeneralAgentParams（含 `auto_restore_domains`、`enable_browser`、`enable_render_ui`、`unattended_mode`、`max_iterations`、`quote`、`engine_params`、`search_depth`、`prompt_mode`） |
| `personality_templates.py` | ✅ 辅助 | Personality 风格模板定义（17 种预置风格：8 实用型 + 9 趣味型，含中英双语描述、emoji、system prompt suffix）。类型定义从 `dto.PersonalityStyleLiteral` 单一数据源导入。导出 `DEFAULT_PERSONALITY_STYLE` 常量供全局引用 | ✅ |
| `team_protocol.py` | ✅ 核心 | 团队型 Agent Leader Operating Protocol — 当 `agent_type='team'` 时，`build_leader_protocol_prompt()` 解析 `subagent_ids` 为成员名册（名称+描述），`dynamic_discovery=True` 时通过 `_resolve_roster()` 异步扫描用户全部 Agent（排除 leader 自身、无描述者、allow_discovery=False者，上限15），渲染 Leader 调度协议模板，在 Web/Channel/Cron/Kanban 四入口自动注入 `user_instructions` |
| `subagent_catalog.py` | ✅ 核心 | DatabaseSubagentCatalog — SubagentCatalog Protocol 实现，解析 YAML 预设（注入 `_LLMModelResolver` 作为 ModelResolver）+ DB 自定义智能体（注入 CustomAgentFactory + display_name）。DB 自定义智能体会继承业务层保存的 `workspace_policy`，并统一映射为运行时 `SubagentConfig.workspace_policy`；同时强制 `LEAF` 控制范围和 `READ_ONLY_GLOBAL` 记忆隔离。`_LLMModelResolver` 通过 `resolve_model_config()` 从用户 provider 配置获取完整模型配置 |
| `custom_agent_factory.py` | ✅ 核心 | CustomAgentFactory — AgentFactory Protocol 实现，从 DB Profile 构建完整 SkillAgent（技能、记忆、MCP），并为子 Agent 装配 Server-governed `conversation_search_tool`。通过 `apply_agent_mcp_selection()` 统一执行 server-level + tool-level MCP 过滤。支持大上下文静态前缀锁定、资源缓存和 asyncio.Lock 并发初始化保护。 |
| `subagent_presets.py` | ✅ 核心 | 子 Agent 配置预置（adversarial-reviewer/analysis/browser/coding/deep-audit/search），启动时注册 |
| `general_agent/` | ✅ 核心 | 通用对话 Agent（配置、中间件、工具） |
| `media_tools/` | ✅ 核心 | 产品层媒体 LangChain 适配器（image/video/tts）；引擎在 harness `toolkits/llms/` |
| `prompts/fast_search_agent_prompt.py` | ✅ 核心 | 搜索模式提示词（供 general_agent_prompt.py search 模式 + builtin_initializer 动态解析） |
| `extensions/` | ✅ 核心 | AgentExtension 具体实现（ZeroCostMemory、Security、Subagent、TaskAdaptive），由 factory.py 注册到 BaseAgent |
| `prompts/` | ✅ 辅助 | 共享提示词（通用 Agent 多模式提示词、搜索建议、共享规则） |
| `agent_middlewares/` | ✅ 辅助 | 共享中间件（用户指令注入） |

---

## 子模块详情

### general_agent/

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `agent.py` | 核心 | 通用 Agent 定义 | — |
| `agent_middlewares/citation_rules_middleware.py` | 核心 | 引用规则中间件 | — |
| `agent_middlewares/tool_selection_middleware.py` | 核心 | 工具约束中间件 — tool_choice 状态机 + 收敛保护 | — |
| `tools/answer_user_tool.py` | 核心 | 回答用户工具 | — |
| harness `agent/meta_tools/clarification/clarification_agent_tools.py` | 核心 | 结构化澄清工具（ask_question）；server `_setup_clarification_tools` 按 `structured_clarify` ON + `web_chat`+`!unattended`+`prompt_mode!=search` 挂载并注入 LangGraph interrupt | — |
| harness `agent/meta_tools/interaction/render_ui_tool.py` | 核心 | UI 渲染工具（A2UI）；`enabled_builtin_tools` 含 `render_ui` 时加载 | — |

### prompts/fast_search_agent_prompt.py

搜索模式提示词。被 `general_agent_prompt.py` 静态引用为 `_SEARCH_PROMPT_BASE` 和 `SEARCH_DEEP_SUFFIX`（Kv Cache 稳定），作为 `prompt_mode="search"` 的唯一提示词来源。支持 normal 和 deep 两种深度，共享引用规则（`EXTERNAL_SOURCES_CITATION_RULES`）。Deep 后缀指引 `web_fetch_tool` 深读与 `request_answer_user_tool` 自审；Fast 模式 Turn1 工具为 web_search + web_fetch + answer_tool + memory（可选），browser 仅通过 Agent profile 的 `browser` 开关 opt-in，不由 `search_depth=deep` 自动加载。

---

## 依赖关系

- `myrm_agent_harness/agent/`：Agent 基础实现
- `app/core/`：安全、沙箱、存储等基础设施

### 被依赖

- `app/services/`：业务服务层调用 AgentFactory 创建 Agent

## GeneralAgentParams 装配点

- 新增任何 `app/**/*.py` 内对 `GeneralAgentParams(` 或 `GeneralAgentParams.model_validate` 的调用前，必须核对 Web / Channel / Cron / Eval 与 `ResolvedAgentProfile` 字段一致性（含 `auto_restore_domains`、`enable_browser`、`enable_render_ui` 等）。
- 仓库守卫单测：`tests/core/agents/test_general_agent_params_callsites_guard.py`（改点后须同步更新 allowlist）。
- 离线续跑：`app/api/agents/general_agent/streaming.py` 使用 `params.model_dump(mode="json")` 写入 `OfflineDurableTask.serialized_params`；`app/lifecycle/system.py` 用 `model_validate` 恢复，故新增到 `GeneralAgentParams` 的**运行时关键字段**应默认可被 Pydantic 序列化/反序列化；往返约束见 `tests/core/agents/test_general_agent_params_serialization_roundtrip.py`。

## 分层原则

- `app/ai_agents/` 负责业务语义装配，决定哪些运行时信号应该下传给框架。
- `myrm-agent-harness` 负责通用执行、压缩、记忆、工具编排等基础能力。
- 外部控制服务负责调度与运行基础设施，不承载对话语义推断。

## DB 自定义 Agent 作为 Subagent 的契约

数据库中的自定义 Agent 被当作子 Agent 使用时，不是简单地把一段 prompt 塞进框架，而是走统一运行时映射：

- 使用 `CustomAgentFactory` 构造完整 SkillAgent，保留技能、记忆、MCP 能力。
- `workspace_policy="ISOLATED_COPY"` 时，映射为运行时 `WorkspacePolicy.ISOLATED_COPY`；否则默认继承父工作区。
- 统一强制 `ControlScope.LEAF`，禁止递归再委派。
- 统一强制 `MemoryIsolationPolicy.READ_ONLY_GLOBAL`，避免父子 Agent 并发污染共享记忆。
