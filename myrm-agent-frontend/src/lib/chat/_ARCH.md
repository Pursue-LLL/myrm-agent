# lib/chat/

## 架构概述

聊天域共享的前端纯逻辑：会话引导、跨视图拖拽载荷契约、智能路由归因文案映射、「最新回合回答」判定与后台完成通知行的读取。

## 文件清单

| 文件                    | 地位 | 职责                                                                                                                                                                                                       | I/O/P |
| ----------------------- | ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `ensureActiveChatId.ts` | 核心 | 返回既有 chat id，缺失时创建会话与 pane（供 Settings 面板程序化发消息）                                                                                                                                    | ✅    |
| `priorChatDrag.ts`      | 核心 | 侧栏会话拖拽到输入框的载荷契约（MIME 常量与编解码）                                                                                                                                                        | ✅    |
| `routingReason.ts`      | 核心 | harness 路由判定原因 → `chat.tokenUsage` 文案 key 的映射（未识别返回 null，UI 不展示内部串）                                                                                                               | ✅    |
| `progressStepsUi.ts`    | 辅助 | Task Steps 展开事件（skill undo hint → `EXPAND_PROGRESS_STEPS_EVENT`）                                                                                                                                     | ✅    |
| `lastTurnAnswer.ts`     | 核心 | `findLastTurnAnswerId`：最新用户回合的回答（跳过系统通知行 `isSystemNotice`，也跳过没起回合的后台完成通知，与服务端 `get_last_user_message` 同规则）；重新生成只作用于最新回合，仅该回答显示该按钮         | ✅    |
| `wakeupNotice.ts`       | 核心 | 服务端为已结算后台任务追加的用户行（`metadata.wakeup_notice`）的唯一读法：`parseWakeupNoticeKind` 解出种类（followup / degraded / suppressed，其余为 undefined），`isInertWakeupNotice` 判定没起回合的种类 | ✅    |

## 依赖

- `@/store/useChatStore`、`@/store/useWorkspaceStore`
- `@/store/chat/types/messages` — `MentionReference`（前序会话引用 SSOT）
- 父模块 [`../_ARCH.md`](../_ARCH.md)
