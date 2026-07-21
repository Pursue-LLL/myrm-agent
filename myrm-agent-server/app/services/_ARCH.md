# services 模块架构


---

## 架构概述

业务服务层。协调 Agent、工具和数据库，实现具体业务逻辑。被 API 层调用，调用 ai_agents 和 core 层。
按业务域组织为子模块。

### 桌宠术语（companion vs mascot）

| 名称 | 路径 | 职责 |
|------|------|------|
| **Companion** | `companion/` + `api/companion/` | 桌宠 Observer 反应、进化资格查询（用户可见「伴侣」行为） |
| **Mascot** | `mascot/` | XP / 状态映射、情绪转换、LRU 缓存清理（流式事件 `mascot_xp` 驱动） |

前端桌宠 UI 在 `myrm-agent-frontend/src/components/features/companion/`；SSE 事件经 `messageStream/handlers/companionEvents.ts` 分发。

---

## 子模块清单

| 模块 | 地位 | 职责 | 文档 |
|------|------|------|------|
| `agent/` | ✅ 核心 | Agent 相关服务（CRUD、流式执行、搜索、进化引擎） | [_ARCH.md](agent/_ARCH.md) |
| `chat/` | ✅ 核心 | 聊天服务（会话管理、消息处理、压缩、对话召回） | [_ARCH.md](chat/_ARCH.md) |
| `project/` | ✅ 核心 | 项目管理服务（CRUD + 会话归属移动/批量移动） | [_ARCH.md](project/_ARCH.md) |
| `auth/` | ✅ 核心 | 认证服务（OAuth、本地认证） | [_ARCH.md](auth/_ARCH.md) |
| `config/` | ✅ 核心 | 配置管理服务（CRUD、加密、迁移、健康监控、首次配置） | [_ARCH.md](config/_ARCH.md) |
| `memory/` | ✅ 核心 | 记忆业务服务（备份/恢复、Shared Context 共享上下文治理） | [_ARCH.md](memory/_ARCH.md) |
| `skills/` | ✅ 核心 | 技能相关服务（权限、经验账本、草稿通知、自动提取） | [_ARCH.md](skills/_ARCH.md) |
| `skill_optimization/` | ✅ 核心 | Skill 优化服务（AB 测试、基线同步、LLM 优化、回滚） | [_ARCH.md](skill_optimization/_ARCH.md) |
| `event/` | ✅ 核心 | 事件记录（Agent 运行时事件持久化 + Turn 生命周期管理） | [_ARCH.md](event/_ARCH.md) |
| `kanban/` | ✅ 核心 | Kanban 看板业务编排（mixin facade + orchestrator 模块 + TaskRunner + diagnostics） | [_ARCH.md](kanban/_ARCH.md) |
| `budget/` | ✅ 核心 | 预算治理服务（BudgetPolicy 持久化 + DailyBudgetGuard） | [_ARCH.md](budget/_ARCH.md) |
| `connect/` | ✅ 核心 | 外部 Agent 连接管理（Profile 注册、Token 生成/验证/吊销、Doctor 健康检查） | [_ARCH.md](connect/_ARCH.md) |
| `external_agents/` | ✅ 辅助 | 外部 CLI 委托 RuntimePool 按 chat 复用、per-chat turn lock、idle 回收 | [_ARCH.md](external_agents/_ARCH.md) |
| `risk/` | ✅ 核心 | 风险检测服务（规则引擎、常量、检测逻辑） | [_ARCH.md](risk/_ARCH.md) |
| `security/` | ✅ 核心 | 安全配置服务（Profile 管理：CRUD、激活、克隆、内置 profile 种子） | [_ARCH.md](security/_ARCH.md) |
| `message_filter/` | ✅ 核心 | 消息过滤服务（审计、配置管理、版本控制） | [_ARCH.md](message_filter/_ARCH.md) |
| `features/` | ✅ 核心 | Feature Flags 服务（注册、用户覆盖配置持久化） | [_ARCH.md](features/_ARCH.md) |
| `progression/` | ✅ 辅助 | 用户能力进度服务（里程碑追踪、等级计算、Feature Gate 联动） | — |
| `repair/` | ✅ 核心 | 运行时修复动作契约与白名单执行服务 | [_ARCH.md](repair/_ARCH.md) |
| `approvals/` | ✅ 核心 | 审批注册表（Agent 操作审批流） | [_ARCH.md](approvals/_ARCH.md) |
| `channels/` | ✅ 核心 | 渠道业务编排（实例配置、CP egress、配对绑定） | [_ARCH.md](channels/_ARCH.md) |
| `checkpoint/` | ✅ 核心 | 会话检查点业务服务 | [_ARCH.md](checkpoint/_ARCH.md) |
| `companion/` | ✅ 辅助 | 桌宠 Observer 反应与进化状态（见上方术语表） | [_ARCH.md](companion/_ARCH.md) |
| `mascot/` | ✅ 辅助 | Mascot XP / 状态映射与缓存清理（见上方术语表） | [_ARCH.md](mascot/_ARCH.md) |
| `context/` | ✅ 核心 | Shared Context / Context Bundle 业务编排 | [_ARCH.md](context/_ARCH.md) |
| `artifacts/` | ✅ 核心 | 产物业务编排与 API 侧用例 | [_ARCH.md](artifacts/_ARCH.md) |
| `audit/` | ✅ 辅助 | 审计日志业务服务 | [_ARCH.md](audit/_ARCH.md) |
| `integrations/` | ✅ 核心 | 集成连接编排与用户配置 | [_ARCH.md](integrations/_ARCH.md) |
| `webui/` | ✅ 辅助 | WebUI 专用服务（Remote 模式认证、二维码） | [_ARCH.md](webui/_ARCH.md) |
| `locked_use/` | ✅ 辅助 | Locked Use 协调层（Computer Use 锁屏解锁编排，集成 SleepInhibitor + Tauri IPC） | [_ARCH.md](locked_use/_ARCH.md) |
| `infra/` | ✅ 辅助 | 基础设施维护（沙箱清理、防休眠、系统通知） | [_ARCH.md](infra/_ARCH.md) |
| `power/` | ✅ 辅助 | 电源与系统状态管理（智能防休眠锁、电量感知） | [_ARCH.md](power/_ARCH.md) |
| `background/` | ✅ 辅助 | 后台守护任务 | [_ARCH.md](background/_ARCH.md) |
| `wiki/` | ✅ 辅助 | Wiki 服务（记忆转 Wiki） | [_ARCH.md](wiki/_ARCH.md) |
| `migration/` | ✅ 辅助 | 外部助手数据迁移（Wizard 封闭 4 源：Hermes/OpenClaw/Claude Code/Codex） | [_ARCH.md](migration/_ARCH.md) |
| `deploy/` | ✅ 核心 | 产物一键部署（Vercel API 客户端、SPA 路由注入、网络重试） | [_ARCH.md](deploy/_ARCH.md) |
| `files/` | ✅ 辅助 | 非 HTTP 文件内容提取（PDF/Office bytes→text） | [_ARCH.md](files/_ARCH.md) |
| `extension/` | ✅ 辅助 | 浏览器扩展桥 WebSocket 生命周期与 CDP 代理 | [_ARCH.md](extension/_ARCH.md) |
---

## 依赖关系

### 内部依赖
- `app/ai_agents/`：Agent 配置和工厂
- `app/core/`：核心基础设施（安全、工具、存储）
- `app/database/`：数据模型和会话管理

### 被依赖方
- `app/api/`：HTTP 接口层调用 services 层
- `app/main.py`：生命周期管理（cleanup 启停）

### 与 `api/` 的目录对应

`services/` 子目录名常与 `api/` 不同（如 `agent/` ↔ `agents/`）。完整对照表见根目录 [CONTRIBUTING.md § API ↔ Services domain vocabulary](../../../CONTRIBUTING.md#api--services-domain-vocabulary)；CI 锁见 [tests/architecture/test_api_services_vocabulary.py](../../../tests/architecture/test_api_services_vocabulary.py)。
