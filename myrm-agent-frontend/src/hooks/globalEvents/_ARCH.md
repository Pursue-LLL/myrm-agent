# hooks/globalEvents/

全局 SSE 编排与跨 feature toast。

| 文件                          | 职责                                                                                                                                                                                |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `useGlobalEvents.ts`          | SSE 订阅、审批/预算/后台任务/`managed_policy_updated`/`run_digest_updated`/`skill_pool_updated` 等全局事件编排；`voice_background_task_done` 时 dispatch `voice-bg-done` 供语音播报 |
| `memoryOperationToasts.ts`    | 记忆 CRUD toast；`implicit_feedback_personal` 事件刷新待审批队列（提示由聊天页 `usePendingMemoryToast` 负责）                                                                       |
| `locatorHealedToast.tsx`      | 浏览器 locator 自愈通知                                                                                                                                                             |
| `subsumptionUndoToast.ts`     | 空闲知识降维软删除后的撤销 toast（`idle_status` 的 `cognitive_subsumption` notification 携带可恢复 id，调用 `/memory/undo-consolidation`）                                          |
| `messageDeadLetteredToast.ts` | 消息死信告警                                                                                                                                                                        |
| `reauthToasts.ts`             | `mcp_auth_required` / `oauth_reauth_required` 重新授权 toast：MCP → `/settings/mcp`，OAuth 账号 → `/settings/credentials`，文案用 `formatOAuthIssuerLabel` 的账号展示名称呼账号且不展示后端 reason                  |
| `backupAlertToast.ts`         | 自动备份连续失败的 `health_alert`（`component=instance_backup`）：仅本地化文案（不展示服务端措辞与组件名），操作直达备份设置卡片 `/settings/workbench#auto-backup` |

Hook 层允许的 JSX 例外（toast 渲染）。消费者：`global-events-initializer.tsx`、workspace-browser。
