# core 模块架构


---

## 架构概述

独立的业务核心包，提供 Agent、工具、检索、存储等基础能力。设计为可独立拆分的包，与 myrm-agent-harness（通用框架）形成互补关系。

---

## 文件清单

| 文件/目录 | 地位 | 职责 | I/O/P |
|----------|------|------|-------|
| `__init__.py` | 核心 | 模块入口，公共 API 导出 | — |
| `types/` | 核心 | 业务层类型定义（业务类型、文件引用类型） | [_ARCH.md](types/_ARCH.md) |
| `memory/` | 核心 | 记忆系统（多类型记忆存储和检索） | [_ARCH.md](memory/_ARCH.md) |
| `retriever/` | 核心 | 检索引擎（向量存储、图存储、混合检索） | [_ARCH.md](retriever/_ARCH.md) |
| `security/` | 核心 | 安全模块（MCP SSRF 防护、凭证存储、浏览器会话保管） | [_ARCH.md](security/_ARCH.md) |
| `skills/` | 核心 | 技能管理（技能存储适配器） | [_ARCH.md](skills/_ARCH.md) |
| `channel_bridge/` | 核心 | 渠道业务适配层（配对、Agent 执行、策略、BTW 通知；框架在 `app/channels/`） | [_ARCH.md](channel_bridge/_ARCH.md) |
| `commitment/` | 核心 | Commitment 领域原语（HTTP 在 `api/commitment/`） | [_ARCH.md](commitment/_ARCH.md) |
| `integrations/` | 核心 | 集成目录数据模型与校验（编排 HTTP 在 `api/integrations/`） | [_ARCH.md](integrations/_ARCH.md) |
| `cron/` | 核心 | 定时任务引擎（调度器、执行器、cron 解析） | [_ARCH.md](cron/_ARCH.md) |
| `storage/` | 核心 | 存储服务 | [_ARCH.md](storage/_ARCH.md) |
| `eval/` | 核心 | 评估引擎（桥接 Harness 的 AgentExecutor，提供异步服务） | [_ARCH.md](eval/_ARCH.md) |
| `infra/` | 辅助 | 基础设施（限流器、端口管理、CORS验证、前端启动、服务器全局状态） | [_ARCH.md](infra/_ARCH.md) |
| `artifacts/` | 辅助 | 产物处理 | [_ARCH.md](artifacts/_ARCH.md) |
| `utils/` | 辅助 | 工具函数（错误处理、文件工具、响应工具等） | [_ARCH.md](utils/_ARCH.md) |
| `monitoring/` | 辅助 | 监控与可观测性（Prometheus 指标、LLM/Slack 指标导出、OpenTelemetry 追踪初始化） | [_ARCH.md](monitoring/_ARCH.md) |
| `notifications/` | 辅助 | 系统通知分发 | [_ARCH.md](notifications/_ARCH.md) |
| `subagents/` | 核心 | 子 Agent 模型解析（`ModelResolver` 业务实现） | [_ARCH.md](subagents/_ARCH.md) |
| `errors/` | 辅助 | LLM 错误类型定义 | [_ARCH.md](errors/_ARCH.md) |
| `media/` | 辅助 | 媒体处理（批量编排） | [_ARCH.md](media/_ARCH.md) |
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
