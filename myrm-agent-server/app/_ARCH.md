# app 模块架构


---

## 架构概述

MyrmAgent 后端应用主体。Claw-class AI 助手的业务逻辑层，采用分层架构：API → Services → AI Agents → Core（基于 Myrm Agent Harness 框架）。
每层职责清晰，依赖方向单一（上层依赖下层，下层不依赖上层）。

---

## 分层架构

```
api/          HTTP 接口层（路由、请求验证、响应格式化）
  ↓
services/     业务服务层（业务逻辑编排、Agent 调用协调）
  ↓
ai_agents/    Agent 定义层（业务 Agent 配置、定制中间件和工具）
  ↓
core/         核心基础设施层（安全、沙箱、存储）
```

---

## 子模块清单

| 模块 | 地位 | 职责 | 文档 |
|------|------|------|------|
| `api/` | ✅ 核心 | FastAPI 路由层，HTTP 接口定义 | [_ARCH.md](api/_ARCH.md) |
| `services/` | ✅ 核心 | 业务服务层，按域组织（agent/chat/webui/infra/auth 等） | [_ARCH.md](services/_ARCH.md) |
| `ai_agents/` | ✅ 核心 | 业务 Agent 配置和定制 | [_ARCH.md](ai_agents/_ARCH.md) |
| `core/` | ✅ 核心 | 核心基础设施（安全、存储、监控、记忆等） | [_ARCH.md](core/_ARCH.md) |
| `database/` | ✅ 核心 | SQLAlchemy ORM 模型、Repository 仓储和数据库操作 | [_ARCH.md](database/_ARCH.md) |
| `config/` | ✅ 辅助 | 环境变量、日志、部署模式配置 | [_ARCH.md](config/_ARCH.md) |
| `middleware/` | ✅ 辅助 | FastAPI 全局中间件（认证、安全、缓存） | [_ARCH.md](middleware/_ARCH.md) |
| `platform_utils/` | ✅ 辅助 | 平台适配层（Sandbox/Local 差异化实现） | [_ARCH.md](platform_utils/_ARCH.md) |
| `adapters/` | ✅ 辅助 | Harness Protocol 实现（当前主要为 skill_optimization） | [_ARCH.md](adapters/_ARCH.md) |
| `lifecycle/` | ✅ 辅助 | 应用生命周期（启动/关闭编排） | [_ARCH.md](lifecycle/_ARCH.md) |
| `server/` | ✅ 辅助 | 服务器配置（lifespan、异常处理、中间件注册） | [_ARCH.md](server/_ARCH.md) |
| `startup/` | ✅ 辅助 | 启动编排（环境加载、配置校验、进程锁、服务器启动器） | [_ARCH.md](startup/_ARCH.md) |
| `tasks/` | ✅ 辅助 | 异步任务（图片生成等后台任务执行器） | [_ARCH.md](tasks/_ARCH.md) |

---

## 核心文件

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `main.py` | FastAPI 应用入口（创建实例、注册路由/中间件、lifespan 管理） | ✅ |
| `lifecycle_tasks.py` | 异步任务 worker 生命周期管理（包含 Vault GC 定时清理任务） | ✅ |

## 架构约束与类型安全防线 (Zero-Trust Progressive Typing)

- **100% Strict 模式**：核心调度区（`api/`、`core/`、`services/`、`ai_agents/`）已全面开启 MyPy Strict 模式，**绝对禁止**使用 `Any` 类型。
- **强制防腐层 (Anti-Corruption Layer)**：核心区**绝对禁止**直接操作 ORM 模型（`app/database/models/`）。所有进出核心区的数据必须在 Repository 边界层转换为严格的 Pydantic DTO 或 `dataclass`。
- **状态机类型守卫**：LangGraph 等底层依赖禁止使用松散字典，必须通过泛型和 `TypedDict` 强制约束节点契约。

---

## 依赖方向

```
api/ → services/ → ai_agents/ → myrm_agent_harness/
                              ↘ core/
```

- 上层可以依赖下层
- 下层不应依赖上层
- `myrm_agent_harness/` 是独立包，不依赖 app 其他模块
