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
| `connect.ts` | Connect Wizard：`/connect/profiles|generate|doctor|revoke|status`；外部 Agent MCP 连接管理（generate 携带 agent_id 实现 per-agent 记忆作用域） |
| `extension.ts` | 浏览器扩展桥：`/extension/status|domains|tabs|disconnect|setup-hints`；`getExtensionWebSocketUrl()`。**REST 须传 `apiRequest('/extension/...')` 相对路径**（禁止 `getApiUrl()` 再包一层，否则 `fetchWithTimeout` 二次前缀 → `/api/v1/api/v1/...` 404）；loopback dev WS 回退端口 **8080**（`isLoopbackDevHost()`） |
| `llm-config.ts` | Provider / 模型探测 |
| `webui-auth.ts` | 本地 WebUI 登录/setup token |
| `web-push.ts` | Web Push VAPID REST：`/web-push/vapid-key`, subscribe/unsubscribe/test |
| `projects.ts` | 项目 CRUD、会话归属移动 |
| `milestones.ts` | `/projects/*/milestones` CRUD、progress/roadmap、`import-assessment` 导入回执（含 `import_id`）；并复用 `/files/artifacts?limit=N&project_id=...&assessment_import_candidate=true` 拉取当前项目最近工件候选供里程碑导入入口，优先返回后端语义探测为 `importable` 的候选（`already_imported` 与 `not_importable` 均视为不可导入，无 importable 命中时回退时间排序）；导入失败时可从标准错误结构 `error.details[field=import_reason]` 读取机器可读原因 |
| `skill*.ts` / `skills-*.ts` | 技能 CRUD、进化、打包 |
| `archiveSecurityErrorCore.ts` | 批量导入 `archive_security.*` 错误码解析与 i18n key 映射纯函数，供技能导入 UI 稳定消费 |
| `skill-growth.ts` | `/skill-growth/*`：cases（含 `total`）、detail、stats、audit |
| `skill-optimization.ts` | `/skill-optimization/*` 质量历史、版本列表/对比/回滚、Shadow A/B 启动；另封装 `/batch-optimization/tasks/{id}/cancel` 与 `rollback` |
| `memory*.ts` / `memoryArchive.ts` | 记忆、Shared Context、导入 dry-run/confirm（含 post-import readiness 合同 + `readiness-recheck`）、Memory Guardian `safe/force` 触发 + 策略配置 + `overview` 单接口（health/policy/alerts+digest，携带客户端时区头）+ 守卫不可用告警阈值契约 |
| `migrationDiscovery.ts` | Local/Tauri 外部助手数据自动发现（Hermes / OpenClaw / Claude Code / Codex）+ server 下发 `source_manifest`（display/import/deep-link）与 `source_manifest_authoritative` 覆盖语义消费 |
| `onboarding.ts` | Onboarding readiness/complete + Telegram assistant 一键接入编排接口 `/config/onboarding/telegram-assistant/apply` |
| `google-workspace-oauth.ts` | `/integrations/google-workspace/oauth/*`：config/start/poll/status/disconnect；Tauri 用 shell.open |
| `kanban.ts` | `/kanban/*`：Board/Task CRUD、move/promote/reclaim、bulk、依赖边、Specify/Decompose、Pipeline 实例化；`listBoards({ projectId })` + `createBoard({ project_id, milestone_id })` 作用域链路 |
| `agent.ts` | `/user-agents/*` CRUD、密钥、快照回滚、导入导出；`getAgent(..., signal)` 支持请求级 abort；fetch 错误与 secret list normalize 见 `agentFetchErrorCore.ts` |
| `agentFetchErrorCore.ts` | 纯函数：`parseUserAgentFetchErrorMessage`（detail/顶层 message）、`normalizeAgentSecretKeyNames`（`{key_name}[]` → `string[]`） |
| `runs.ts` | `GET /runs`：Cron / Kanban / Shell 后台任务统一运行历史（只读聚合） |
| `background-tasks.ts` | `GET/POST /background-tasks/*`：Panel 列表、cancel、steer、**shell stdin**（`sendShellBackgroundStdin` → `POST …/stdin`） |
| `mediaTasks.ts` | `GET/POST /api/v1/tasks/*`：Panel 媒体分区（活跃 + 近期 terminal image/video list/cancel/fetch） |
| `taskEventStream.ts` | 共享 `/api/v1/tasks/stream` SSE 多播（Chat 任务卡 + Panel 媒体 + Tray + 完成通知复用单连接） |
| `tauriNativeNotification.ts` | Tauri 桌面原生通知 helper（media 完成 + budget 告警复用） |
| `backgroundTasksRefresh.ts` | Panel/tray 即时刷新：`notifyBackgroundTasksChanged` + `notifyBackgroundTasksChangedForShellJobFinish`（global SSE finish） |
| `hosting.ts` | `/artifacts/hosting/*`、publish、publications、WS URL |
| `artifact*.ts` | 工件相关 REST |
| `subscription*.ts` / `entitlements*.ts` | **仅 SaaS/sandbox** 构建使用的 CP 配额 |
| `marketplace.ts` | **仅 SaaS/sandbox** Org Marketplace CRUD：browse/install/publish/force-push |
| `themeMarketplace.ts` | **仅 SaaS/sandbox** 公开主题市场：CP catalog/checkout + admin suspend/restore + server install-from-marketplace |
| `enterprise-org.ts` | **仅 SaaS/sandbox** Enterprise Org 管理：create/members/offboard/transfer |
| `org-model-policy.ts` | **仅 SaaS/sandbox** 组织模型白名单客户端：`fetchOrgModelPolicy` + `isModelAllowedByPolicy` glob 匹配 |
| `*-api.ts` | 零散 REST 封装 |
| `file.ts` | HTTP 上传、`UploadProgress`、PDF/文档内容提取（**非**本地选文件） |
| `file-service/` | 平台 `FileService` 策略（Tauri FS vs Sandbox）；见 [_ARCH.md](file-service/_ARCH.md) |
| `wikiService.ts` | `/wiki/*` 客户端：概念树/队列/导入/审批与 query；`queryWiki` 返回结构化 `source_snippets(level/path/section/snippet)` 供设置页与聊天证据链复用 |
| `wikiEvidenceContextCore.ts` | Wiki 证据 query 上下文解析核心（chat `context_key` 回溯边界 + `turn_distance` 计算），供输入 Hook 与流式发送链路复用统一口径 |
| `wikiEvidenceQuerySuccessPendingCore.ts` | Chat steer query success 延迟确认核心：按 `chatId + expectedMessageId` 注册待确认 success，在首个匹配业务 SSE 帧到达时消费，避免 accepted 即 success 的提前误计 |
| `wikiEvidenceMetrics.ts` | `/statistics/wiki-evidence/*` 客户端：记录证据曝光/展开/核验停留/query attempt+success/负向结果事件（按 `context_key` 隔离复问口径，query 事件携带 `turn_distance`；离线丢样聚合上报 `dropped_report`，`quality_outcome_negative` 用于答案负反馈锚点；chat 输入侧由 `useMessageInputWikiEvidenceCore.ts` 解析上下文并上报），并查询聚合摘要（expansion/deep verification/re-query/quick bounce/dwell/negative outcome + query success rate）。 |
| `turnCapabilityMetrics.ts` | `/statistics/turn-capability/*` 客户端：记录单轮 Skill/MCP 能力覆写的提交/生效/noop/排队/完成/失败/busy 重排队事件（含 selected/effective 能力规模与 `failure_reason` 枚举：`network_error/archive_restore_invalid/abort/server_error/unknown_error`）；支持离线丢样按 source 分桶聚合回补 `dropped_report`，并查询 apply/noop/queue/completion/failure 率聚合。 |
| `expertSummonMetrics.ts` | `/statistics/expert-summon/*` 客户端：记录专家召唤漏斗事件（surface/search/attempt/success/fail/route apply/first send/dropped），并按 surface 聚合离线丢样回补；支持查询召唤成功率、路由应用率、首条发送转化率等口径。 |
| `assessmentImportMetrics.ts` | `/statistics/assessment-import/*` 客户端：记录评估导入漏斗事件（import_attempted/import_succeeded/import_failed/dropped，维度含 trigger=manual_input/recent_candidate 与 failure_reason），并按 trigger 聚合离线丢样回补；支持查询导入成功率、失败率、recent-candidate 入口占比与失败原因分布；支持读取导入后价值锚点 `value-summary`（任务完成率/里程碑完成率/激活率）。 |
| `templateDiscovery.ts` | 模板发现层共享纯函数：检索标准化、命中过滤、模板类别归一化（TemplateMarket 与 FlowPad 复用，避免口径漂移）。 |
| `templateSummon.ts` | 模板召唤共享执行层：统一实例化 + 观测事件写入（attempt/success/fail），收敛 TemplateMarket 与 FlowPad 的重复逻辑。 |
| `config/` | `ConfigSyncManager` + 适配器 + `themePersonalSettingsSync` 主题 fast-path · [_ARCH.md](config/_ARCH.md) |
| `deliverable/` | Workspace 交付物 Portal 打开 SSOT · [_ARCH.md](deliverable/_ARCH.md) |
| `theme-packages/` | `.myrmtheme` inspect / install / export · [_ARCH.md](theme-packages/_ARCH.md) |
| `theme-assets/` | 主题背景上传 + `file:` 资产解析 + MP4 poster 提取 |
| `deliverable/` | workspace deliverable 打开编排（ArtifactPortal + `/files/browse/content`） |
| `companion/` | Petdex 客户端 · [_ARCH.md](companion/_ARCH.md)（install/doctor/spritesheet/i18n core） |

## 依赖

- `@/lib/utils/authHeaders` — 认证头
- `@/lib/api` — `API_BASE_URL`、通用 fetch
- `@/lib/deploy-mode.ts` — 部署模式
- 本地模式：**不**调用 CP（`cp-base-url.ts` 仅 sandbox 前端）

## 约束

- 错误文案通过调用方 + `locales/*` 呈现；service 层抛英文 `Error` message 供日志。
- 单文件 >800 行应拆分（`channels.ts` 已分片；`chat.ts` 仍为 P0 候选）。
