# services/

## 架构概述

对 `myrm-agent-server` REST/SSE 的类型化客户端（约 55 个模块）。按业务域单文件或小子目录组织；**顶层单文件禁止** `index.ts` barrel，跨域门面见根 [_ARCH.md](../../_ARCH.md)「桶导出政策」与 `scripts/ci/barrel_whitelist.txt`。

## 域划分（文件 → API）

| 文件 / 模式 | 职责 |
|-------------|------|
| `chat.ts` | 会话 CRUD、流式聊天 |
| `cron.ts` / `cron.types.ts` | `/cron/*` REST 客户端；类型在 `cron.types.ts`（含 monitor contract error 与连续失败计数元数据） |
| `channels.ts` | 渠道 facade → `channels/` 分片 |
| `channels/` | 核心工厂、管理 API、Provider 凭证、登录协议 · [_ARCH.md](channels/_ARCH.md) |
| `connect.ts` | Connect Wizard：`/connect/profiles|generate|doctor|revoke|status`；外部 Agent MCP 连接管理 |
| `extension.ts` | 浏览器扩展桥：`/extension/status|domains|tabs|disconnect|setup-hints`；`getExtensionWebSocketUrl()` |
| `llm-config.ts` | Provider / 模型探测 |
| `webui-auth.ts` | 本地 WebUI 登录/setup token |
| `web-push.ts` | Web Push VAPID REST：`/web-push/vapid-key`, subscribe/unsubscribe/test |
| `projects.ts` | 项目 CRUD、会话归属移动 |
| `skill*.ts` / `skills-*.ts` | 技能 CRUD、进化、打包 |
| `archiveSecurityErrorCore.ts` | 批量导入 `archive_security.*` 错误码解析与 i18n key 映射纯函数，供技能导入 UI 稳定消费 |
| `skill-growth.ts` | `/skill-growth/*`：cases（含 `total`）、detail、stats、audit |
| `skill-optimization.ts` | `/skill-optimization/*` 质量历史、版本列表/对比/回滚、Shadow A/B 启动；另封装 `/batch-optimization/tasks/{id}/cancel` 与 `rollback` |
| `memory*.ts` / `memoryArchive.ts` | 记忆、Shared Context、导入 dry-run、Memory Guardian `safe/force` 触发 + 策略配置 + `overview` 单接口（health/policy/alerts+digest，携带客户端时区头）+ 守卫不可用告警阈值契约 |
| `migrationDiscovery.ts` | Local/Tauri 外部助手数据自动发现（Hermes / OpenClaw / Claude Code / Codex） |
| `google-workspace-oauth.ts` | `/integrations/google-workspace/oauth/*`：config/start/poll/status/disconnect；Tauri 用 shell.open |
| `kanban.ts` | `/kanban/*`：Board/Task CRUD、move/promote/reclaim、bulk、依赖边、Specify/Decompose、Pipeline 实例化 |
| `agent.ts` | `/user-agents/*` CRUD、密钥、快照回滚、导入导出；`getAgent(..., signal)` 支持请求级 abort；fetch 错误与 secret list normalize 见 `agentFetchErrorCore.ts` |
| `agentFetchErrorCore.ts` | 纯函数：`parseUserAgentFetchErrorMessage`（detail/顶层 message）、`normalizeAgentSecretKeyNames`（`{key_name}[]` → `string[]`） |
| `runs.ts` | `GET /runs`：Cron / Kanban / Shell 后台任务统一运行历史（只读聚合） |
| `background-tasks.ts` | `GET/POST /background-tasks/*`：Panel 列表、cancel、steer |
| `backgroundTasksRefresh.ts` | Panel/tray 即时刷新：`notifyBackgroundTasksChanged` + `notifyBackgroundTasksChangedForShellJobFinish`（global SSE finish） |
| `hosting.ts` | `/artifacts/hosting/*`、publish、publications、WS URL |
| `artifact*.ts` | 工件相关 REST |
| `subscription*.ts` / `entitlements*.ts` | **仅 SaaS/sandbox** 构建使用的 CP 配额 |
| `marketplace.ts` | **仅 SaaS/sandbox** Org Marketplace CRUD：browse/install/publish/force-push |
| `enterprise-org.ts` | **仅 SaaS/sandbox** Enterprise Org 管理：create/members/offboard/transfer |
| `*-api.ts` | 零散 REST 封装 |
| `file.ts` | HTTP 上传、`UploadProgress`、PDF/文档内容提取（**非**本地选文件） |
| `file-service/` | 平台 `FileService` 策略（Tauri FS vs Sandbox）；见 [_ARCH.md](file-service/_ARCH.md) |
| `config/` | `ConfigSyncManager` + 适配器（local `TauriConfigAdapter` 处理 Next 代理 5xx 与离线队列；sandbox `SandboxConfigAdapter`） |

## 依赖

- `@/lib/utils/authHeaders` — 认证头
- `@/lib/api` — `API_BASE_URL`、通用 fetch
- `@/lib/deploy-mode.ts` — 部署模式
- 本地模式：**不**调用 CP（`cp-base-url.ts` 仅 sandbox 前端）

## 约束

- 错误文案通过调用方 + `locales/*` 呈现；service 层抛英文 `Error` message 供日志。
- 单文件 >800 行应拆分（`channels.ts` 已分片；`chat.ts` 仍为 P0 候选）。
