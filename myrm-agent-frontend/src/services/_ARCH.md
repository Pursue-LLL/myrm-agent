# services/

## 架构概述

对 `myrm-agent-server` REST/SSE 的类型化客户端（约 55 个模块）。按业务域单文件或小子目录组织；**禁止**桶导出（barrel index）。

## 域划分（文件 → API）

| 文件 / 模式 | 职责 |
|-------------|------|
| `chat.ts` | 会话 CRUD、流式聊天 |
| `cron.ts` / `cron.types.ts` | `/cron/*` REST 客户端；类型在 `cron.types.ts` |
| `channels.ts` | 渠道配置与状态 |
| `connect.ts` | Connect Wizard：`/connect/profiles|generate|doctor|revoke|status`；外部 Agent MCP 连接管理 |
| `extension.ts` | 浏览器扩展桥：`/extension/status|domains|tabs|disconnect|setup-hints`；`getExtensionWebSocketUrl()` |
| `llm-config.ts` | Provider / 模型探测 |
| `webui-auth.ts` | 本地 WebUI 登录/setup token |
| `projects.ts` | 项目 CRUD、会话归属移动 |
| `skill*.ts` / `skills-*.ts` | 技能 CRUD、进化、打包 |
| `skill-optimization.ts` | `/skill-optimization/*` 质量历史、版本列表/对比/回滚、Shadow A/B 启动；另封装 `/batch-optimization/tasks/{id}/cancel` 与 `rollback` |
| `memory*.ts` / `memoryArchive.ts` | 记忆、Shared Context、导入 dry-run |
| `migrationDiscovery.ts` | Local/Tauri 外部助手数据自动发现（Hermes / OpenClaw / Claude Code / Codex） |
| `google-workspace-oauth.ts` | `/integrations/google-workspace/oauth/*`：config/start/poll/status/disconnect；Tauri 用 shell.open |
| `kanban.ts` | `/kanban/*`：Board/Task CRUD、move/promote/reclaim、bulk、依赖边、Specify/Decompose、Pipeline 实例化 |
| `hosting.ts` | `/artifacts/hosting/*`、publish、publications、WS URL |
| `artifact*.ts` | 工件相关 REST |
| `subscription*.ts` / `entitlements*.ts` | **仅 SaaS/sandbox** 构建使用的 CP 配额 |
| `marketplace.ts` | **仅 SaaS/sandbox** Org Marketplace CRUD：browse/install/publish/force-push |
| `enterprise-org.ts` | **仅 SaaS/sandbox** Enterprise Org 管理：create/members/offboard/transfer |
| `*-api.ts` | 零散 REST 封装 |

## 依赖

- `@/lib/utils/authHeaders` — 认证头
- `@/lib/api` — `API_BASE_URL`、通用 fetch
- `@/lib/deploy-mode.ts` — 部署模式
- 本地模式：**不**调用 CP（`cp-base-url.ts` 仅 sandbox 前端）

## 约束

- 错误文案通过调用方 + `locales/*` 呈现；service 层抛英文 `Error` message 供日志。
- 单文件 >800 行应拆分（当前 `chat.ts`、`channels.ts` 为 P0 候选）。
