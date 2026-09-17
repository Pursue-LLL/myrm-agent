# memory/replay/

## 架构概述

会话回放：复现历史会话的记忆召回与模型视角。回放器驱动时间线，纯函数模块负责时间线映射与视口解析，实时流模块对接后端回放通道。

## 文件清单

| 文件                          | 地位 | 职责                                                             | I/O/P |
| ----------------------------- | ---- | ---------------------------------------------------------------- | ----- |
| `SessionReplayPlayer.tsx`     | 门面 | 回放播放器：时间线控制、安全徽标与视图编排                       | ✅    |
| `ReplayControls.tsx`          | 核心 | 播放/暂停/步进/倍速控制条                                        | ✅    |
| `ReplayInspector.tsx`         | 核心 | 回放检视面板（当前步的状态与召回快照）                           | ✅    |
| `ReplayTimeline`（`replayTimeline.ts`） | 逻辑 | 时间线纯函数：把回放事件流映射为可寻址步骤              | ✅    |
| `ReplayMessageBubble.tsx`     | 展示 | 回放消息气泡                                                     | ✅    |
| `ReplayMindView.tsx`          | 展示 | 回放心智视图（模型内部状态可视化）                               | ✅    |
| `ModelViewportView.tsx`       | 展示 | 结构化模型视口检视卡片                                           | ✅    |
| `viewportParser.ts`           | 逻辑 | 视口纯函数解析器（分角色拆解/截断提示/空值守卫）                 | ✅    |
| `ConversationRecallPanel.tsx` | 展示 | 会话召回面板（回放中命中的记忆条目）                             | ✅    |
| `ExternalHarnessSyncCard.tsx` | 辅助 | 外部 harness 同步卡（跨 harness 回放对齐）                       | ✅    |
| `memoryLiveStream.ts`         | 逻辑 | 记忆实时流客户端的纯函数部分                                     | ✅    |

## 依赖

- `@/store/*`、`@/services/memory`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
