# hooks/globalEvents/

全局 SSE 编排与跨 feature toast。

| 文件                          | 职责                                                                                                                                                                                |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `useGlobalEvents.ts`          | SSE 订阅、审批/预算/后台任务/`managed_policy_updated`/`run_digest_updated`/`skill_pool_updated` 等全局事件编排；`voice_background_task_done` 时 dispatch `voice-bg-done` 供语音播报 |
| `memoryOperationToasts.ts`    | 记忆 CRUD toast；`implicit_feedback_personal` 事件刷新待审批队列（提示由聊天页 `usePendingMemoryToast` 负责）                                                                       |
| `locatorHealedToast.tsx`      | 浏览器 locator 自愈通知                                                                                                                                                             |
| `subsumptionUndoToast.ts`     | 空闲知识降维软删除后的撤销 toast（`idle_status` 的 `cognitive_subsumption` notification 携带可恢复 id，调用 `/memory/undo-consolidation`）                                          |
| `skillGrowthToasts.ts`        | 技能成长 toast：后台自动学会新技能（`skill_growth_updated` 的 `AUTO_APPLIED`）只弹一条，带「撤销」= 归档（`PATCH /skills/curator/{name}/lifecycle`，可在技能列表恢复；固定或被绑定时服务端返回 409，文案说明原因）；`skill_evolved` 带 `notify=false`（已由成长事件提示）时只刷新不弹窗，人工批准与可选进化（`skill_evolved` 默认通知）弹出带回滚的提示，回滚经 `rollbackSkillEvolution`（带鉴权头的统一请求入口） |
| `messageDeadLetteredToast.ts` | 消息死信告警                                                                                                                                                                        |
| `reauthToasts.ts`             | `mcp_auth_required` / `oauth_reauth_required` 重新授权 toast：MCP → `/settings/mcp`，OAuth 账号 → `/settings/credentials`，文案用 `formatOAuthIssuerLabel` 的账号展示名称呼账号且不展示后端 reason                  |
| `backupAlertToast.ts`         | 自动备份连续失败的 `health_alert`：整机备份（`component=instance_backup`）直达 `/settings/workbench#auto-backup`，云端记忆备份（`component=remote_memory_backup`）直达 `/settings/memory?sub=cloud-backup`；仅本地化文案（不展示服务端措辞与组件名），两类各用独立 toast id，互不覆盖 |
| `kanbanTaskToast.ts`          | 看板任务完成/阻塞/失败的 toast 与系统通知：toast 的「查看看板」操作与系统通知的点击都直达该状态列（`buildKanbanBoardDeepLink` 的 `board_id` + `status`，事件没有 `board_id` 时不给操作）；完成的结果与阻塞原因按服务端原文显示，认识的阻塞原因按界面语言显示（`lib/kanban/kanbanBlockedReason`），不认识的原样显示，超过 200 字符截断并加省略号；失败不带说明文字（服务端不发运行的异常原文，运行记录在看板里）；定时阻塞（`block_kind=scheduled`，任务自己恢复）不弹窗也不发系统通知 |

Hook 层允许的 JSX 例外（toast 渲染）。消费者：`global-events-initializer.tsx`、workspace-browser。
