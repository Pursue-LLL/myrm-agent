# api/ 模块架构

## 架构概述

FastAPI HTTP/WebSocket 入口层。`router.py` 聚合子路由挂载到 `/api/v1`；各子目录按业务域拆分，**禁止**在 API 层写持久化或 Agent 执行逻辑（委托 `services/`）。上级：[../_ARCH.md](../_ARCH.md)。

## 根级文件

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `dependencies.py` | 核心 | FastAPI 依赖注入统一入口 | ✅ |
| `router.py` | 核心 | 全量子路由注册表 | — |

## 子模块导航（按域）

| 域 | 路径 | 职责 |
|----|------|------|
| Agent 对话 | [agents/](agents/_ARCH.md) · [agents/general_agent/](agents/general_agent/_ARCH.md) | 流式对话、模板、子 Agent、Harness 桥 |
| 审批 | [approvals/](approvals/_ARCH.md) | 全局 HITL Drawer recovery |
| 聊天/项目 | [chats/](chats/_ARCH.md) · [projects/](projects/_ARCH.md) | 会话 CRUD、项目归属 |
| 看板 | [kanban/](kanban/_ARCH.md) | Board/Task、Specify/Decompose、Pipeline |
| 技能 | [skills/](skills/_ARCH.md) · [skill_optimization/](skill_optimization/_ARCH.md) | 技能 CRUD、进化、质量、批量优化 |
| 记忆 | [memory/](memory/_ARCH.md) · [memory/operations/](memory/operations/_ARCH.md) | 记忆 CRUD、指挥中心、Shared Context |
| 渠道 | [channels/](channels/_ARCH.md) | Webhook/管理端点（local 模式） |
| 安全 | [security/](security/_ARCH.md) | 仪表盘、Profile、Vault、E-Stop |
| 扩展桥 | [extension/](extension/_ARCH.md) | Chrome MV3 WebSocket + 域名授权 |
| Connect | [connect/](connect/_ARCH.md) | 外部 Agent 连接向导 |
| 集成 | [integrations/](integrations/_ARCH.md) · [credentials/](credentials/_ARCH.md) | MCP/OAuth/Hardware Cookbook |
| 配置 | [config/](config/_ARCH.md) · [features/](features/_ARCH.md) | Omni-Config、功能开关 |
| 定时/任务 | [cron/](cron/_ARCH.md) · [tasks/](tasks/_ARCH.md) · [background_tasks/](background_tasks/_ARCH.md) | Cron、异步任务、后台 worker |
| 语音/媒体 | [voice/](voice/_ARCH.md) · [stt/](stt/_ARCH.md) · [tts/](tts/_ARCH.md) · [media/](media/_ARCH.md) | 实时语音、STT/TTS、媒体生成 |
| 运维 | [health/](health/_ARCH.md) · [system/](system/_ARCH.md) · [statistics/](statistics/_ARCH.md) | 健康检查、关机、统计 |
| 浏览器录制 | [browser_recording/](browser_recording/_ARCH.md) | Browser Skill 录制向导 — WebSocket 控制 + Skill 生成 |
| 浏览器会话 | [browser_sessions/](browser_sessions/_ARCH.md) | 已保存浏览器登录会话管理 — 列表/删除/清理过期 |
| 画布 | [canvas/](canvas/_ARCH.md) | 无限画布工作台 CRUD、snapshot、selection、SSE |
| 其他 | [wiki/](wiki/_ARCH.md) · [eval/](eval/_ARCH.md) · [migration/](migration/_ARCH.md) · [goals/](goals/_ARCH.md) · [memory/follow_ups/](memory/follow_ups/_ARCH.md) · [companion/](companion/_ARCH.md) · [budget/](budget/_ARCH.md) · [risk/](risk/_ARCH.md) · [audit/](audit/_ARCH.md) · [internal/](internal/_ARCH.md) · [webui/](webui/_ARCH.md) · [openai_compat/](openai_compat/_ARCH.md) · [mem0_compat/](mem0_compat/_ARCH.md) · [widget_storage/](widget_storage/_ARCH.md) | 各产品子功能 HTTP 薄层 |

## 约束

- 单租户：路由与依赖**无** `user_id` 多租户语义（`tests/architecture/test_no_user_id.py`）。
- SaaS sandbox：认证经 `middleware/auth.py` HMAC；部分端点拉 Control Plane internal API（见 `services/security/`）。
- 渠道 Webhook 动态注册见 `main.py` `init_channel_routes()`，非全部列于 `router.py`。
- **`api/` 与 `services/` 非 1:1 目录镜像**：贡献者域名词对照见根目录 [CONTRIBUTING.md § API ↔ Services domain vocabulary](../../../CONTRIBUTING.md#api--services-domain-vocabulary)；CI 锁见 [tests/architecture/test_api_services_vocabulary.py](../../../tests/architecture/test_api_services_vocabulary.py)。
