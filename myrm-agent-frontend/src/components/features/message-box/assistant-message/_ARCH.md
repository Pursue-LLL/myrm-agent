# assistant-message/

## 架构概述

助手消息气泡的行为层：载荷读取、思考块折叠、重新生成与取消。

## 文件清单

| 文件                                           | 地位 | 职责                                                                                                                                                                                                                                                                                                                                                                                                   | I/O/P |
| ---------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `messagePayloads.ts`                           | 辅助 | 助手消息载荷的纯函数读取器：`closeUnbalancedReasoningTags`（补全流式中途尚未闭合的 think / thinking / thought / antthinking / reasoning / REASONING_SCRATCHPAD 块）、`parseAsyncTaskResponse`（含 `task_id` 的回复渲染为任务卡）、`parseTtsAudioResponse`（`status=success` 且带 `audio_url` 的回复渲染为播放卡）、`readSessionRecording` / `readToolImages` / `readMcpApps` / `readCronJobResult` / `readKanbanTasksCreated` / `resolveProgressSteps`；持久化或流式消息可能带畸形值，读取器逐项校验，不抛错，回落为空结果 | ✅    |
| `useReasoningAutoCollapse.ts`                  | 辅助 | 思考块展开状态：最新一条、流式中且尚无正文时初始展开；正文与思考停止变化 1 秒后折叠一次，折叠之后用户再展开不再被收起；`inline` 档位（思考始终展开）与没有思考的消息不折叠                                                                                                                                                                                                                                                                      | ✅    |
| `useAssistantMessageActions.ts`                | 辅助 | `handleRegenerate`：没有 chatId 返回 false；服务端放行后移除本条回答、带上 sibling 分组与指令，回答带 KB 证据时上报 `recordQualityOutcomeNegative`，刷新计划，去掉时间标签后重发，返回回合是否送出（请求被拒或未送出为 false，菜单据此保留自定义指令），`finally` 清除 sibling 提示；`handleCancel`：取消服务端请求、关闭 SSE，并清除 `waiting_for_turn` 残留步骤                                                                                     | ✅    |
| `__tests__/messagePayloads.test.ts`            | 测试 | 各读取器的表驱动单测：未闭合标签补全、任务 / TTS 回复的识别与拒绝、录屏 / 图片 / MCP 应用 / 定时任务 / 看板任务的畸形值回落、进度步骤的取值优先级                                                                                                                                                                                                                                                                  | ✅    |
| `__tests__/useReasoningAutoCollapse.test.tsx`  | 测试 | 初始展开条件、正文停止变化 1 秒后折叠一次且重新展开不被收起、正文持续变化时重新计时、`inline` 档位与无思考消息不折叠                                                                                                                                                                                                                                                                                              | ✅    |
| `__tests__/useAssistantMessageActions.test.tsx` | 测试 | 重新生成的放行 / 被拒 / 异常路径、KB 质量锚点、sibling 提示清除；取消请求、关闭流与清除等待步骤，服务端拒绝取消时不动流与转录                                                                                                                                                                                                                                                                                   | ✅    |

## 依赖

- `@/store/*`、`@/services/*`、`@/lib/utils/messageUtils`
- 同级 `message-box/` 的 `CronJobSystemCard` / `KanbanTaskCreatedCard`（结果类型）
- 父模块 [`message-box/_ARCH.md`](../_ARCH.md)
