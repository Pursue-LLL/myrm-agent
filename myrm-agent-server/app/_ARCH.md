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
services/     业务服务层（用例编排、Agent 调用协调、Repository 边界外逻辑）
  ↓
ai_agents/    Agent 定义层（业务 Agent 配置、定制中间件和工具）
  ↓
core/         领域原语层（无 HTTP 的领域能力、适配器、持久化桥接）
  ↘ channels/  消息渠道框架（Provider/Gateway/Routing，横切子系统）
```

`channels/` 与 `api/` 同级，体量 ~220 个 Python 文件，不是 `services/` 子目录。业务适配（配对、Agent 绑定）在 `core/channel_bridge/`。

`schemas/` 为 API 与 services 共享的 Pydantic DTO，两者均可导入，**禁止** services 反向依赖 `app.api`。

### core/ vs services/ 同名目录边界

| 同名目录 | `core/` 职责 | `services/` 职责 |
|----------|--------------|------------------|
| `artifacts/` | 产物存储/读取原语 | 产物业务编排与 API 侧用例 |
| `infra/` | 端口、CORS、健康、全局状态 | 沙箱清理、防休眠、系统通知维护 |
| `integrations/` | 集成目录数据模型与校验 | 集成连接编排与用户配置 |
| `kanban/` | SqlAlchemy 持久化适配器 | Board/Task CRUD 与调度编排 |
| `memory/` | 记忆引擎、向量/图存储 | 备份恢复、Shared Context 治理 |
| `security/` | MCP SSRF、凭证保管、浏览器会话 | Security Profile CRUD 与种子 |
| `skills/` | 技能存储适配器 | 权限、经验账本、自动提取 |

**规则**：`core/` = 可复用领域能力 + 适配器；`services/` = HTTP 用例编排，调用 `core/` + `database.repositories` + harness。

### 进程启动 vs 运行时 Lifespan

```
run.py
  → startup/     进程级：env 分层加载、配置迁移、健康检查、文件锁、uvicorn/granian
  → server/      FastAPI lifespan Phase 1/2/3 + 中间件 + 优雅关闭
  → lifecycle/   运行时后台：Gateway、Cron、Kanban Dispatcher、记忆守护、浏览器池
```

权威分工：`startup/_ARCH.md`（进程入口）、`server/_ARCH.md`（lifespan 阶段）、`lifecycle/_ARCH.md`（常驻调度器）。

---

## 子模块清单

| 模块 | 地位 | 职责 | 文档 |
|------|------|------|------|
| `api/` | ✅ 核心 | FastAPI 路由层，HTTP 接口定义 | [_ARCH.md](api/_ARCH.md) |
| `services/` | ✅ 核心 | 业务服务层，按域组织（agent/chat/webui/infra/auth 等） | [_ARCH.md](services/_ARCH.md) |
| `channels/` | ✅ 核心 | 多平台消息渠道框架（Provider/Gateway/Routing/Rendering） | [_ARCH.md](channels/_ARCH.md) · [CHANNELS_SYSTEM.md](channels/CHANNELS_SYSTEM.md) |
| `ai_agents/` | ✅ 核心 | 业务 Agent 配置和定制 | [_ARCH.md](ai_agents/_ARCH.md) |
| `core/` | ✅ 核心 | 领域原语（安全、存储、监控、记忆适配等） | [_ARCH.md](core/_ARCH.md) |
| `database/` | ✅ 核心 | SQLAlchemy ORM 模型、Repository 仓储和数据库操作 | [_ARCH.md](database/_ARCH.md) |
| `schemas/` | ✅ 核心 | 共享 Pydantic DTO（api ↔ services 契约） | [_ARCH.md](schemas/_ARCH.md) |
| `config/` | ✅ 辅助 | 环境变量、日志、部署模式配置 | [_ARCH.md](config/_ARCH.md) |
| `middleware/` | ✅ 辅助 | FastAPI 全局中间件（认证、安全、缓存） | [_ARCH.md](middleware/_ARCH.md) |
| `platform_utils/` | ✅ 辅助 | 平台适配层（Sandbox/Local 差异化实现） | [_ARCH.md](platform_utils/_ARCH.md) |
| `adapters/` | ✅ 辅助 | Harness Protocol 实现（当前主要为 skill_optimization） | [_ARCH.md](adapters/_ARCH.md) |
| `lifecycle/` | ✅ 辅助 | 运行时后台调度（Gateway/Cron/守护进程，非进程入口） | [_ARCH.md](lifecycle/_ARCH.md) |
| `server/` | ✅ 辅助 | FastAPI lifespan、异常处理、中间件注册 | [_ARCH.md](server/_ARCH.md) |
| `startup/` | ✅ 辅助 | 进程级启动（env/锁/runner，由 `run.py` 调用） | [_ARCH.md](startup/_ARCH.md) |
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
         ↓              ↘ core/ ← channels/（框架层，被 core/channel_bridge 与 services 消费）
         ↘ schemas/（DTO 契约，无业务逻辑）
         ↘ database.repositories/（防腐层，禁止 core 直接操作 ORM）
```

- 上层可以依赖下层；`channels/` 不依赖 `api/`
- 下层不应依赖上层
- `myrm_agent_harness/` 是独立 PyPI 包，不依赖 app 其他模块
