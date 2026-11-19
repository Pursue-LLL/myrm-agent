# lib/chat/

## 架构概述

聊天域共享的前端纯逻辑：会话引导、跨视图拖拽载荷契约、智能路由归因文案映射、「最新回合回答」判定、后台完成通知行的读取、生成媒体的登记读写，以及代用户填写输入框后的光标落点。

## 文件清单

| 文件                    | 地位 | 职责                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | I/O/P |
| ----------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `ensureActiveChatId.ts` | 核心 | 返回既有 chat id，缺失时创建会话与 pane（供 Settings 面板程序化发消息）                                                                                                                                                                                                                                                                                                                                                                                                        | ✅    |
| `priorChatDrag.ts`      | 核心 | 侧栏会话拖拽到输入框的载荷契约（MIME 常量与编解码）                                                                                                                                                                                                                                                                                                                                                                                                                            | ✅    |
| `routingReason.ts`      | 核心 | harness 路由判定原因 → `chat.tokenUsage` 文案 key 的映射（未识别返回 null，UI 不展示内部串）                                                                                                                                                                                                                                                                                                                                                                                   | ✅    |
| `progressStepsUi.ts`    | 辅助 | Task Steps 展开事件（skill undo hint → `EXPAND_PROGRESS_STEPS_EVENT`）                                                                                                                                                                                                                                                                                                                                                                                                         | ✅    |
| `lastTurnAnswer.ts`     | 核心 | `findLastTurnAnswerId`：最新用户回合的回答（跳过系统通知行 `isSystemNotice`，也跳过没起回合的后台完成通知，与服务端 `get_last_user_message` 同规则）；重新生成只作用于最新回合，仅该回答显示该按钮                                                                                                                                                                                                                                                                             | ✅    |
| `wakeupNotice.ts`       | 核心 | 服务端为已结算后台任务追加的用户行（`metadata.wakeup_notice`）的唯一读法：`parseWakeupNoticeKind` 解出种类（followup / degraded / suppressed，其余为 undefined），`isInertWakeupNotice` 判定没起回合的种类                                                                                                                                                                                                                                                                     | ✅    |
| `mediaGenerated.ts`     | 核心 | 生成媒体卡片的唯一数据来源：`mediaGeneratedEntriesOf` 把一次媒体工具（`image_tool` / `video_tool` / `tts_generate`）的结构化结果登记为条目（异步生成登记任务 `{kind, task_id}`，同步编辑与语音登记已落库的 `media://` 引用；`status` / `list` / 错误不登记），`readMediaGeneratedEntries` 读回消息 metadata 或断线重连快照里的条目（丢弃形状不合法的项），`mergeMediaGeneratedEntries` 去重并入；与服务端 `collect_media_generated` 同受 `shared/config/media_generation_contract.json` 约束 | ✅    |
| `focusMessageInput.ts`  | 辅助 | 把光标移到输入框末尾；所有代用户填写输入框的动作（恢复并继续、编辑此图）共用，因为它们离输入框很远，所以按文档查找输入框而不是传入                                                                                                                                                                                                                                                                                                                                             | ✅    |

## 依赖

- `@/store/useChatStore`、`@/store/useWorkspaceStore`
- `@/store/chat/types/messages` — `MentionReference`（前序会话引用 SSOT）
- `@/lib/mediaReference` — `parseMediaReference`（`media://<id>` 引用判定）
- 共享契约 [`media_generation_contract.json`](../../../../shared/config/media_generation_contract.json)（`mediaGenerationContract.test.ts` 读取）
- 父模块 [`../_ARCH.md`](../_ARCH.md)
