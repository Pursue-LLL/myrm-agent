# app/services/agent/params/conversion 子包架构

请求转换的装配阶段集合。`params/converter.py` 是唯一调用方，按固定顺序调用这些阶段；阶段顺序由门面持有，本子包内的模块互不编排。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合导出六个阶段的入口与结果类型 | — |
| `model_plan.py` | 核心 | 模型槽位（主 / fallback / lite / safety / vision / video）解析、能力与上下文窗口补全、有序列 fallback 链装配 | ✅ |
| `sources.py` | 核心 | 外部数据源：搜索服务可用性、retrieval 的 embedding/reranker、MCP 服务器（请求 > 用户配置 > 组织级合并） | ✅ |
| `profile_apply.py` | 核心 | Agent profile 能力包：system_prompt、混合路由规则、team leader 协议、personality/locale 后缀、per-agent MCP 过滤、`agent_config` 覆盖、tool gateway | ✅ |
| `chat_context.py` | 核心 | 会话作用域：chat 行、workspace 解析（项目 / 已有 chat / 首轮 `workspace_dir` / 默认 workspace）、session access roots、共享记忆上下文 | ✅ |
| `tool_surface.py` | 核心 | 入口面工具挂载：fast（answer_tool-only）vs `WEB_CHAT`，产出 tool flags / prompt_mode / search_depth | ✅ |

## 依赖关系

- 上游：`params/converter.py`（唯一调用方）、`params/models.py`、`params/model_config/`
- 下游：`app.core.channel_bridge.*`（模型/搜索/检索配置）、`app.services.agent.profile.*`（Agent 档案）、`app.services.agent.tool_mount`（挂载策略）、harness 记忆与检索类型
