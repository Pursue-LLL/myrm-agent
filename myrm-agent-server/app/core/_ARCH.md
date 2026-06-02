# core 模块架构


---

## 架构概述

独立的业务核心包，提供 Agent、工具、检索、存储等基础能力。设计为可独立拆分的包，与 myrm-agent-harness（通用框架）形成互补关系。

---

## 文件清单

| 文件/目录 | 地位 | 职责 | I/O/P |
|----------|------|------|-------|
| `__init__.py` | 核心 | 模块入口，公共 API 导出 | ⚠️ 待补 |
| `types/` | 核心 | 业务层类型定义（业务类型、文件引用类型） | ⚠️ 待补 |
| `memory/` | 核心 | 记忆系统（多类型记忆存储和检索） | ⚠️ 待补 |
| `retriever/` | 核心 | 检索引擎（向量存储、图存储、混合检索） | ⚠️ 待补 |
| `security/` | 核心 | 安全模块（MCP SSRF 防护、凭证存储、浏览器会话保管） | ⚠️ 待补 |
| `skills/` | 核心 | 技能管理（技能存储适配器） | ⚠️ 待补 |
| `channels/` | 核心 | 多平台消息通道业务层（注册、凭证、Agent 执行、策略、话题配置） | ⚠️ 待补 |
| `cron/` | 核心 | 定时任务引擎（调度器、执行器、cron 解析） | ⚠️ 待补 |
| `storage/` | 核心 | 存储服务 | ⚠️ 待补 |
| `eval/` | 核心 | 评估引擎（桥接 Harness 的 AgentExecutor，提供异步服务） | ⚠️ 待补 |
| `infra/` | 辅助 | 基础设施（限流器、端口管理、CORS验证、前端启动、服务器全局状态） | ⚠️ 待补 |
| `artifacts/` | 辅助 | 产物处理 | ⚠️ 待补 |
| `utils/` | 辅助 | 工具函数（错误处理、文件工具、响应工具等） | ⚠️ 待补 |
| `monitoring/` | 辅助 | 监控与可观测性（Prometheus 指标、LLM/Slack 指标导出、OpenTelemetry 追踪初始化） | [_ARCH.md](monitoring/_ARCH.md) |
| `notifications/` | 辅助 | 系统通知分发 | ⚠️ 待补 |
| `subagents/` | 核心 | 子 Agent 模型解析（`ModelResolver` 业务实现） | [_ARCH.md](subagents/_ARCH.md) |
| `errors/` | 辅助 | LLM 错误类型定义 | ⚠️ 待补 |
| `media/` | 辅助 | 媒体处理（批量编排） | ⚠️ 待补 |
| `kanban/` | 核心 | Kanban 持久化适配器（SqlAlchemyKanbanStore、ORM 映射） | [_ARCH.md](kanban/_ARCH.md) |

---

## 依赖关系

**内部依赖**：
- `myrm-agent-harness` — 通用 Agent 框架
- `langchain` — LangChain 框架
- `qdrant-client` — Qdrant 客户端
- `sqlalchemy` — ORM 框架

**被依赖**：
- `app/services/` — 业务服务层
- `app/ai_agents/` — Agent 定义层
- `app/api/` — API 路由层
