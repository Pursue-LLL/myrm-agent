# app/api 模块架构


---

## 架构概述

FastAPI 路由层。纯 HTTP 接口定义，不包含业务逻辑（业务逻辑在 `app/services/` 和 `app/core/`）。
按领域划分子模块，通过 `router.py` 统一注册。支持部署模式条件路由（Sandbox/Local）。
已全面剥离多租户感知（去除路由和 Query 中的 `user_id`），以纯单租户沙箱模式运行。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 模块入口 | 空（避免桶文件导出触发路由树加载） | ❌ |
| `router.py` | ✅ 核心 | 主路由注册中心，按职责分组注册所有子路由 | ⚠️ 待补 |
| `dependencies.py` | ✅ 核心 | 全局依赖注入（`get_deploy_identity`、数据库会话、部署模式守卫、`verify_voice_enabled` 语音特性门控） | ✅ |
| `workspace_rules.py` | ✅ 核心 | 项目级规则文件自省（GET /workspace/rules），供前端展示已发现的 workspace 规则文件 | ✅ |
| `health/` | ✅ 基础设施 | 健康检查与诊断端点 | ⚠️ 待补 |

---

## 子模块清单

### 核心 AI 能力

| 模块 | 路由前缀 | 职责 |
|------|---------|------|
| `agents/` | `/agents`, `/user-agents` | AI Agent 统一调用接口（fast/agent/deep_research/consensus 模式）+ 用户智能体 CRUD |
| `external_agents.py` | `/external-agents` | 外部委托 Agent 订阅鉴权（登录状态徽章、SSE 交互式登录、凭据导入/登出）— local+SaaS 全模式注册 |
| `chats/` | `/chats` | 聊天会话管理（创建、列表、删除、重命名、上下文压缩） |
| `eval/` | `/eval` | Agent 评估与回归测试（运行、状态查询、用例管理、报告） |
| `skills/` | `/skills`, `/evolution`, `/skill-quality`, `/experience-ledger`, `/migrations`, `/reviews` | 技能管理全域（CRUD、进化、质量、经验账本、迁移、审查收件箱；本地/预置/技能池、打包、一键回滚） |
| `skill_optimization/` | `/skill-optimization` | Skill优化系统（仪表盘、质量监控、版本管理、A/B测试、批量优化） |

### 核心业务

| 模块 | 路由前缀 | 职责 |
|------|---------|------|
| `projects/` | `/projects` | 项目管理（CRUD + 会话归属移动/批量移动） |
| `files/` | `/files` | 文件管理（上传、静态服务、存储、加密、一键部署） |
| `memory/` | `/memory` | 用户记忆管理（CRUD、待处理记忆；审批动作会写入 Experience Ledger） |
| `cron/` | `/cron` | 定时任务管理（CRUD、暂停/恢复、触发、执行记录） |
| `notifications/` | `/notifications` | 系统通知管理（列表查询、单条/全部已读、DLQ 重试、action_url 跳转、过期清理） |

### 数据迁移

| 模块 | 路由前缀 | 职责 | 文档 |
|------|---------|------|------|
| `migration/` | `/migration` | 竞品数据自动发现（local/Tauri only，扫描本地竞品 AI 助手数据目录） | [_ARCH.md](migration/_ARCH.md) |

### 集成与基础设施

| 模块 | 路由前缀 | 职责 |
|------|---------|------|
| `features/` | `/features` | Feature Flags 管理（状态查询、实验功能切换、重置） |
| `integrations/` | `/integrations` | 外部服务验证（LLM、搜索、MCP、检索）+ 沙箱 MCP 代理 |
| `system/` | `/system` | 系统信息、公网 ingress、优雅停机（`/shutdown`） |
| `config/` | `/config` | 用户配置管理（带版本控制） |
| `webui/` | `/webui` | WebUI 辅助接口（二维码、欢迎页面、认证） |
| `system/` | `/system` | 系统信息与环境配置解析（如公网入站地址 ingress-url） |

### 用户体验

| 模块 | 路由前缀 | 职责 | 文档 |
|------|---------|------|------|
| `companion/` | `/companion` | 宠物伙伴（Observer 反应生成 + 进化状态查询） | [_ARCH.md](companion/_ARCH.md) |
| `statistics/` | `/statistics` | 用量统计（Token 用量、会话统计、NavBar Badge 聚合） | ⚠️ 待补 |
| `budget/` | `/budget` | 预算治理（日预算策略 CRUD + 实时花费状态） | [_ARCH.md](budget/_ARCH.md) |
| `kanban/` | `/kanban` | Kanban 看板管理（Board/Task CRUD、移动、Run/Event 查询、摘要） | [_ARCH.md](kanban/_ARCH.md) |

### OpenAI 兼容 API

| 模块 | 路由前缀 | 职责 |
|------|---------|------|
| `openai_compat/` | `/v1` | OpenAI 兼容 API（双模式：Agent 执行 + LLM passthrough 直通代理） |
| `api_keys/` | `/api-keys` | API Key 管理（创建、列表、撤销、删除） |

### 安全

| 模块 | 路由前缀 | 职责 |
|------|---------|------|
| `security/` | `/security/allowlist` | 工具调用白名单管理（列表、删除、清空） |

### 消息与语音

| 模块 | 路由前缀 | 职责 | 文档 |
|------|---------|------|------|
| `channels/` | `/channels/manage`, `/channels` | Channel 管理（状态、绑定、群组）+ Webhook 入站 | [_ARCH.md](channels/_ARCH.md) |
| `stt/` | `/stt`, `/ws/stt` | 语音转文字 API（REST 批量 + WS 流式） | [_ARCH.md](stt/_ARCH.md) |
| `tts/` | `/tts` | 文字转语音 API | [_ARCH.md](tts/_ARCH.md) |
| `voice/` | `/ws/voice` | 全双工语音会话 WebSocket（并发 STT+TTS，barge-in） | [_ARCH.md](voice/_ARCH.md) |

### 条件路由

| 模块 | 路由前缀 | 条件 | 职责 |
|------|---------|------|------|
| `channels/router` | `/channels/manage` | 仅 Local | Channel 管理界面 |
| `events/` | `/events` | 仅 Local | Agent 事件流、权限策略查询 |

---

## 路由注册分组

```
api_router
  ├─ AI Agents (general unified endpoint, user-agents)
  ├─ 核心业务 (chats, projects, files, skills, memory, wiki, cron, eval, code-brain)
  ├─ 用户体验 (companion, statistics, budget, kanban)
  ├─ 语音 (stt, tts, voice/ws)
  ├─ 安全 (security/allowlist)
  ├─ 开发者 (workspace_rules)
  ├─ 集成与基础设施 (features, integrations, config, webui)
  ├─ OpenAI 兼容 (/v1 — Agent + LLM passthrough)
  ├─ [Local] migration/ (竞品数据自动发现)
  ├─ [Local] channels/manage (Channel 管理)
  └─ [Local] events/ (Agent 事件流)
```

---

## 依赖关系

### 内部依赖
- `app/services/`：业务逻辑层
- `app/core/security/`：认证、安全
- `app/database/`：数据库连接和模型
- `app/config/`：部署模式配置
- `myrm_agent_harness/`：Agent 核心能力

### 外部依赖
- `fastapi`：Web 框架
- `pydantic`：请求/响应模型
