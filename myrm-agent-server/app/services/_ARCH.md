# services 模块架构


---

## 架构概述

业务服务层。协调 Agent、工具和数据库，实现具体业务逻辑。被 API 层调用，调用 ai_agents 和 core 层。
按业务域组织为子模块。

---

## 子模块清单

| 模块 | 地位 | 职责 | 文档 |
|------|------|------|------|
| `agent/` | ✅ 核心 | Agent 相关服务（CRUD、流式执行、搜索、进化引擎） | [_ARCH.md](agent/_ARCH.md) |
| `chat/` | ✅ 核心 | 聊天服务（会话管理、消息处理、压缩、对话召回） | [_ARCH.md](chat/_ARCH.md) |
| `project/` | ✅ 核心 | 项目管理服务（CRUD + 会话归属移动/批量移动） | [_ARCH.md](project/_ARCH.md) |
| `auth/` | ✅ 核心 | 认证服务（OAuth、本地认证） | — |
| `config/` | ✅ 核心 | 配置管理服务（CRUD、加密、迁移、健康监控、首次配置） | [_ARCH.md](config/_ARCH.md) |
| `memory/` | ✅ 核心 | 记忆业务服务（备份/恢复、Shared Context 共享上下文治理） | [_ARCH.md](memory/_ARCH.md) |
| `skills/` | ✅ 核心 | 技能相关服务（权限、经验账本、草稿通知、自动提取） | — |
| `skill_optimization/` | ✅ 核心 | Skill 优化服务（AB 测试、基线同步、LLM 优化、回滚） | — |
| `event/` | ✅ 核心 | 事件记录（Agent 运行时事件持久化 + Turn 生命周期管理） | [_ARCH.md](event/_ARCH.md) |
| `kanban/` | ✅ 核心 | Kanban 看板业务编排（Board/Task CRUD、Run/Event 查询） | [_ARCH.md](kanban/_ARCH.md) |
| `budget/` | ✅ 核心 | 预算治理服务（BudgetPolicy 持久化 + DailyBudgetGuard） | [_ARCH.md](budget/_ARCH.md) |
| `connect/` | ✅ 核心 | 外部 Agent 连接管理（Profile 注册、Token 生成/验证/吊销、Doctor 健康检查） | — |
| `risk/` | ✅ 核心 | 风险检测服务（规则引擎、常量、检测逻辑） | [_ARCH.md](risk/_ARCH.md) |
| `security/` | ✅ 核心 | 安全配置服务（Profile 管理：CRUD、激活、克隆、内置 profile 种子） | — |
| `message_filter/` | ✅ 核心 | 消息过滤服务（审计、配置管理、版本控制） | [_ARCH.md](message_filter/_ARCH.md) |
| `features/` | ✅ 核心 | Feature Flags 服务（注册、用户覆盖配置持久化） | — |
| `repair/` | ✅ 核心 | 运行时修复动作契约与白名单执行服务 | — |
| `approvals/` | ✅ 核心 | 审批注册表（Agent 操作审批流） | [_ARCH.md](approvals/_ARCH.md) |
| `webui/` | ✅ 辅助 | WebUI 专用服务（Remote 模式认证、二维码） | [_ARCH.md](webui/_ARCH.md) |
| `locked_use/` | ✅ 辅助 | Locked Use 协调层（Computer Use 锁屏解锁编排，集成 SleepInhibitor + Tauri IPC） | — |
| `infra/` | ✅ 辅助 | 基础设施维护（沙箱清理、防休眠、系统通知） | [_ARCH.md](infra/_ARCH.md) |
| `power/` | ✅ 辅助 | 电源与系统状态管理（智能防休眠锁、电量感知） | — |
| `background/` | ✅ 辅助 | 后台守护任务 | — |
| `wiki/` | ✅ 辅助 | Wiki 服务（记忆转 Wiki） | [_ARCH.md](wiki/_ARCH.md) |
| `migration/` | ✅ 辅助 | 竞品数据迁移服务（本地 AI 助手数据自动发现） | [_ARCH.md](migration/_ARCH.md) |
| `reasoning_content_manager.py` | ✅ 核心 | reasoning_content 生命周期管理（MiMo/DeepSeek/Kimi 模型回传支持） | — |

---

## 依赖关系

### 内部依赖
- `app/ai_agents/`：Agent 配置和工厂
- `app/core/`：核心基础设施（安全、工具、存储）
- `app/database/`：数据模型和会话管理

### 被依赖方
- `app/api/`：HTTP 接口层调用 services 层
- `app/main.py`：生命周期管理（cleanup 启停）
