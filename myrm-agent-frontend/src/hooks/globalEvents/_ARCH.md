# hooks/globalEvents/

全局 SSE 编排与跨 feature toast。

| 文件                          | 职责                                                                                                                                                                                |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `useGlobalEvents.ts`          | SSE 订阅与跨标签页领导者选举：只有领导者标签页持有 `EventSource`，其余经 `BroadcastChannel` 接收；事件交给 `dispatchGlobalEvent`；组装 `GlobalEventDeps`（翻译、路由、受 `enableWebNotifications` 控制的 toast 与系统通知、防抖计时器表）；断线指数退避重连，重连后广播 `app_resync_required` 并校准当前会话；卸载时清理计时器，领导者交还自己的领导者标记（下次挂载或其他标签页无需等心跳超时即可接管） |
| `dispatchGlobalEvent.ts`      | 事件类型 → 处理器注册表（两张表认领同一类型时加载即抛错）；只需唤醒页面的事件（`memory_history_updated` / `subagents_updated` / `cron_updated` / `budget_updated` / `goal:branch_switched` / `workspace_file_changed` / `async_agent_stream_chunk` / `extension_status_changed` / `managed_policy_updated`）直接转成 window 事件；未知类型忽略 |
| `eventTypes.ts`               | 共享契约：`SSEPayload`、`GlobalEventDeps`、`GlobalEventHandler`、`PushToast`、`GlobalEventTranslator`、`DebounceTimers` |
| `scheduleDebounced.ts`        | 按 key 防抖：成串到达的事件合并为静默 `delayMs` 后的一次刷新 |
| `channelApprovalEvents.ts`    | `pairing_pending` / `channel_connected` / `channel_disconnected` / `groups_updated` / `message_dead_lettered` / `approval_required` / `approval_resolved` |
| `skillEvents.ts`              | `new_skill_draft` / `skill_growth_updated` / `skill_evolved`：提示直达 `/settings/evolutionPending`，并转成技能页订阅的 window 事件；`skill_pool_updated`（安装 / 卸载 / 同步 / 归档）静默 300ms 后合并为一次本地技能列表与启用配置重载，并转成 window 事件 |
| `systemEvents.ts`             | `idle_status` / `run_digest_updated` / `system_notification`（含后台任务完成时刷新目标与任务列表、`voice-bg-done`）/ `memory_operation` / `locator_healed` / `mcp_auth_required` / `oauth_reauth_required` / `kanban_task_updated` |
| `alertEvents.ts`              | `health_alert`（整机 / 云端记忆备份失败走专用 toast，其余失败为通用错误 toast 与系统通知）/ `budget_alert`（`work_units` 用尽弹对话框并刷新权益，其余按严重度 toast） |
| `goalEvents.ts`               | `goal_terminal` / `goal_dequeued`：提示结果，点击直达会话；出队后重载该会话的目标队列 |
| `agentEvents.ts`              | `subagent_stale` / `subagent_rebind_required` / `agent_config_updated`（`updated` / `rollback` / `force_push` 后 500ms 防抖，刷新花名册、选中智能体详情与绑定会话） |
| `memoryOperationToasts.ts`    | 记忆 CRUD toast；`implicit_feedback_personal` 事件刷新待审批队列（提示由聊天页 `usePendingMemoryToast` 负责）                                                                       |
| `locatorHealedToast.tsx`      | 浏览器 locator 自愈通知（标题、说明与「目标」标签经调用方传入的 `notifications` 翻译函数本地化）                                                                                                                                                             |
| `subsumptionUndoToast.ts`     | 空闲知识降维软删除后的撤销 toast（`idle_status` 的 `cognitive_subsumption` notification 携带可恢复 id，调用 `/memory/undo-consolidation`）                                          |
| `skillGrowthToasts.ts`        | 技能成长 toast：后台自动学会新技能（`skill_growth_updated` 的 `AUTO_APPLIED`）只弹一条，带「撤销」= 归档（`PATCH /skills/curator/{name}/lifecycle`，可在技能列表恢复；固定或被绑定时服务端返回 409，文案说明原因）；`skill_evolved` 带 `notify=false`（已由成长事件提示）时只刷新不弹窗，人工批准与可选进化（`skill_evolved` 默认通知）弹出带回滚的提示，回滚经 `rollbackSkillEvolution`（带鉴权头的统一请求入口） |
| `messageDeadLetteredToast.ts` | 消息死信告警                                                                                                                                                                        |
| `reauthToasts.ts`             | `mcp_auth_required` / `oauth_reauth_required` 重新授权 toast：MCP → `/settings/mcp`，OAuth 账号 → `/settings/credentials`，文案用 `formatOAuthIssuerLabel` 的账号展示名称呼账号且不展示后端 reason                  |
| `backupAlertToast.ts`         | 自动备份连续失败的 `health_alert`：整机备份（`component=instance_backup`）直达 `/settings/workbench#auto-backup`，云端记忆备份（`component=remote_memory_backup`）直达 `/settings/memory?sub=cloud-backup`；仅本地化文案（不展示服务端措辞与组件名），两类各用独立 toast id，互不覆盖 |
| `kanbanTaskToast.ts`          | 看板任务完成/阻塞/失败的 toast 与系统通知：toast 的「查看看板」操作与系统通知的点击都直达该状态列（`buildKanbanBoardDeepLink` 的 `board_id` + `status`，事件没有 `board_id` 时不给操作）；完成的结果与阻塞原因按服务端原文显示，认识的阻塞原因按界面语言显示（`lib/kanban/kanbanBlockedReason`），不认识的原样显示，超过 200 字符截断并加省略号；失败不带说明文字（服务端不发运行的异常原文，运行记录在看板里）；定时阻塞（`block_kind=scheduled`，任务自己恢复）不弹窗也不发系统通知 |
| `systemNotificationToast.ts`  | `system_notification` 的 toast：按服务端在 `meta_data.level` 声明的级别（`success` / `info` / `warning` / `error`）展示，缺省或不认识的级别按 `success`，失败与警告不会呈现成绿色的成功提示；快照创建通知（`meta_data.type=snapshot_created`）由聊天窗口自带图标展示，这里不重复弹出 |

Hook 层允许的 JSX 例外（toast 渲染）。消费者：`global-events-initializer.tsx`、workspace-browser。
