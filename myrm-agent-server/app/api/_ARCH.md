# api/ 模块架构

## 架构概述

FastAPI HTTP/WebSocket 入口层。`router.py` 以挂载表 `ROUTER_MOUNTS` 声明每个子路由，由 [`app/server/lazy_routes.py`](../server/lazy_routes.py) 聚合成挂到 `/api/v1` 的一个 `APIRouter`：`/api/v1` 之后的第一段是路由段，同一路由段的路由组在第一个请求（或启动后的后台预加载）需要它时才导入，启动不为整棵路由树的导入付费；`health` 随进程导入；各子目录按业务域拆分，**禁止**在 API 层写持久化或 Agent 执行逻辑（委托 `services/`）。上级：[../_ARCH.md](../_ARCH.md)。

## 根级文件

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `dependencies.py` | 核心 | FastAPI 依赖注入统一入口 | ✅ |
| `router.py` | 核心 | 路由挂载表：`ROUTER_MOUNTS` 每行声明一个子路由的路由段、模块、前缀与标签；导出 `route_loader`（`LazyRouteLoader`）与它的聚合路由 `api_router`。每个挂载的路径必须落在自己声明的路由段之下（`tests/architecture/test_route_table.py`），新增路由模块就是在表里加一行 | ✅ |

## 子模块导航（按域）

| 域 | 路径 | 职责 |
|----|------|------|
| Agent 对话 | [agents/](agents/_ARCH.md) · [agents/general_agent/](agents/general_agent/_ARCH.md) | 流式对话、模板、子 Agent、Harness 桥 |
| 审批 | [approvals/](approvals/_ARCH.md) | 全局 HITL Drawer recovery |
| 聊天/项目 | [chats/](chats/_ARCH.md) · [projects/](projects/_ARCH.md) | 会话 CRUD、项目归属 |
| 看板 | [kanban/](kanban/_ARCH.md) | Board/Task、Specify/Decompose、Pipeline |
| 批量目录 | [batch_directory/](batch_directory/_ARCH.md) | 同一 prompt × N 目录并行批次（创建/聚合/取消/重试/重跑） |
| 技能 | [skills/](skills/_ARCH.md) · [skill_optimization/](skill_optimization/_ARCH.md) | 技能 CRUD、进化、质量、版本与回滚 |
| 插件导入 | [plugins/](plugins/_ARCH.md) | Agent Plugins 1.0.0 preview/confirm |
| 记忆 | [memory/](memory/_ARCH.md) · [memory/operations/](memory/operations/_ARCH.md) | 记忆 CRUD、指挥中心、Shared Context |
| 渠道 | [channels/](channels/_ARCH.md) | Webhook/管理端点（local 模式） |
| 安全 | [security/](security/_ARCH.md) | 仪表盘、Profile、Vault、E-Stop |
| 扩展桥 | [extension/](extension/_ARCH.md) | Chrome MV3 WebSocket + 域名授权 |
| Connect | [connect/](connect/_ARCH.md) | 外部 Agent 连接向导 |
| 集成 | [integrations/](integrations/_ARCH.md) · [credentials/](credentials/_ARCH.md) | MCP/OAuth/本机 Ollama 探测 |
| 供应商状态 | [providers/](providers/_ARCH.md) | LLM Provider 额度与余额健康探针端点 |
| 配置 | [config/](config/_ARCH.md) · [features/](features/_ARCH.md) | Omni-Config、功能开关 |
| 定时/任务 | [cron/](cron/_ARCH.md) · [tasks/](tasks/_ARCH.md) · [background_tasks/](background_tasks/_ARCH.md) | Cron、异步任务、后台 worker |
| 语音/媒体 | [voice/](voice/_ARCH.md) · [stt/](stt/_ARCH.md) · [tts/](tts/_ARCH.md) · [media/](media/_ARCH.md) | 实时语音、STT/TTS、媒体生成 |
| 运维 | [health/](health/_ARCH.md) · [system/](system/_ARCH.md) · [statistics/](statistics/_ARCH.md) · [runs/](runs/_ARCH.md) | 健康检查、关机、统计、聚合运行历史 |
| 浏览器录制 | [browser_recording/](browser_recording/_ARCH.md) | Browser Skill 录制向导 — WebSocket 控制 + Skill 生成 |
| 浏览器会话 | [browser_sessions/](browser_sessions/_ARCH.md) | 已保存浏览器登录会话管理 — 列表/删除/清理过期 |
| 其他 | [wiki/](wiki/_ARCH.md) · [faq/](faq/_ARCH.md) · [eval/](eval/_ARCH.md) · [migration/](migration/_ARCH.md) · [goals/](goals/_ARCH.md) · [memory/follow_ups/](memory/follow_ups/_ARCH.md) · [companion/](companion/_ARCH.md) · [compounding_playbook/](compounding_playbook/_ARCH.md) · [budget/](budget/_ARCH.md) · [risk/](risk/_ARCH.md) · [audit/](audit/_ARCH.md) · [internal/](internal/_ARCH.md) · [instance_archive/](instance_archive/_ARCH.md) · [webui/](webui/_ARCH.md) · [openai_compat/](openai_compat/_ARCH.md) · [mem0_compat/](mem0_compat/_ARCH.md) · [widget_storage/](widget_storage/_ARCH.md) | 各产品子功能 HTTP 薄层 |

## 约束

- 单租户：路由与依赖**无** `user_id` 多租户语义（`tests/architecture/test_no_user_id.py`）。
- SaaS sandbox：认证经 `middleware/auth.py` HMAC；部分端点拉 Control Plane internal API（见 `services/security/`）。
- 渠道 Webhook 动态注册见 `main.py` `init_channel_routes()`，非全部列于 `router.py`。
- 路由模块只能经 `ROUTER_MOUNTS` 挂载：直接在 `api_router` 上调用 `include_router` 会让该路由组随进程导入，也不在 `ROUTER_MOUNTS` 声明的路由段之内。
- **`api/` 与 `services/` 非 1:1 目录镜像**：贡献者域名词对照见根目录 [CONTRIBUTING.md § API ↔ Services domain vocabulary](../../../CONTRIBUTING.md#api--services-domain-vocabulary)；CI 锁见 [tests/architecture/test_api_services_vocabulary.py](../../tests/architecture/test_api_services_vocabulary.py)。
