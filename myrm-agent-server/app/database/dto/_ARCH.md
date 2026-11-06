# app/database/dto 子包架构

数据传输对象（DTO）。按使用面向拆模块，纯 pydantic 模型、无运行时状态；`app.database.dto` 导入路径不变（120 个模块）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合全部 31 个 DTO、8 个 Literal 别名、`T`、`normalize_workspace_policy`（保持原模块的完整公开面） | — |
| `literals.py` | 辅助 | 存储值词表（personality / 记忆衰减 / 提取预设 / prompt / 安全 / workspace / agent 类型 / 会话重置）与 `normalize_workspace_policy` | ✅ |
| `message.py` | 核心 | `MessageBase` / `MessageDTO` / `MessageCreate`（含 extra 折叠校验）/ `MessageResponse` / `CursorPage` | — |
| `chat.py` | 核心 | `ChatDTO`、聊天列表/详情、标题与摘要请求、`TurnOutlineItem` | — |
| `pagination.py` | 辅助 | 通用分页契约：`PaginationParams` / `PaginationMeta` / `PaginatedResponse[T]` | — |
| `agent_config.py` | 辅助 | agent 嵌套配置模型：模型选择、记忆策略、会话策略、技能、命令绑定、工具网关 | — |
| `agent.py` | 核心 | agent 请求/响应形状：`AgentBase` / `Create` / `Update` / `Response` / `ProfileSnapshotItem` / `ListItem` | — |

## 约定

- 字段默认值一律写成 `Field(default=…)` 关键字形式，未装 pydantic 插件的 mypy 才能把带默认值的字段识别为可省略参数。
- 模块之间只允许 `->` 单向依赖：`chat → message`、`agent → agent_config / literals`；无环。

## 依赖关系

- 上游：`pydantic`、`app.services.agent.builtin_specs.builtin_tool_validation`、harness `toolkits.memory.config`
- 下游：`app/api/**`、`app/services/**`、`app/database/repositories/**`（120 个模块）
