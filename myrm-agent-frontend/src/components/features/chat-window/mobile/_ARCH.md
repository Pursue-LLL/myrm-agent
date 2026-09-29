# mobile/

## 架构概述

移动端 Command Center 交互层：专为移动触控与窄屏场景优化的命令中心视图、审批控制、长按确认、操作 Sheet、以及指挥条输入面（多行草稿 + 语音先校对后下发 + 提示词历史漫游）。

## 边界

指挥条只负责**接收与确认用户意图**（短指令原地直达）；长文写作职责归属主 Chat 的完整 composer，由常驻「查看完整对话」入口承接。刻意不在此处堆叠全屏编辑器、模板体系或工具栏，避免与 `MessageInput` 形成第二套输入实现而漂移。

## 文件清单

| 文件                                     | 地位      | 职责                                                                                                                                                                                                            | I/O/P |
| ---------------------------------------- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `MobileStatusBoard.tsx`                  | 核心      | 移动端 Command Center 壳层（审批/预览/进度 + Co-Pilot chip/Advisor；常驻「查看完整对话」→ 主 Chat 复用 QuoteToolbar 划词）                                                                                      | ✅    |
| `MobileQuickCommandComposer.tsx`         | 核心      | 指挥条输入面：受限多行 TextareaAutosize（回车沿用原生换行，提交只走常驻发送按钮）、chatId 隔离草稿持久化、语音转写先入草稿再确认下发、领域热词偏置、历史漫游单键向旧回溯并交还草稿、`/ask` `/side` 旁路问答路由 | ✅    |
| `MobileQuickControlAccessoryToolbar.tsx` | 组件      | 移动端软键盘上方高频控制辅助栏：历史漫游、剪贴板无损粘贴、一键呼出顾问面板、一键清空                                                                                                                            | ✅    |
| `useMobilePromptHistory.ts`              | 核心 Hook | 移动端会话隔离提示词历史漫游状态机：LRU 历史栈 + 单向向旧回溯游标（草稿由 `MobileQuickCommandComposer` 自身状态与持久化承担）                                                                                   | ✅    |
| `HoldToApproveButton.tsx`                | 组件      | 移动端高危审批长按确认按钮（700ms 动态环形进度条与触觉振动反馈防误触）                                                                                                                                          | ✅    |
| `MobileActionSheet.tsx`                  | 组件      | 移动端底部动作 Sheet（`useMobileSheetEntries` 驱动）                                                                                                                                                            | ✅    |
| `MobilePushDiscoveryBanner.tsx`          | 组件      | 移动端 Web Push 发现与一键授权引导横幅（PWA 离线任务与审批通知）                                                                                                                                                | ✅    |
| `MobileStatusApprovalsSection.tsx`       | 组件      | 移动端待审批队列区块                                                                                                                                                                                            | ✅    |
| `MobileStatusLivePreview.tsx`            | 组件      | 浏览器/桌面 Live Preview 与 Lightbox 查看器                                                                                                                                                                     | ✅    |
| `MobileStatusMessageBody.tsx`            | 组件      | 进度/验证/思考/结果/Artifact 交付物列表与 Plan 步骤                                                                                                                                                             | ✅    |
| `useMobileSheetEntries.tsx`              | 辅助 Hook | 移动端动作 Sheet 条目定义与路由分发                                                                                                                                                                             | ✅    |

## 依赖

- `@/store/*`（会话与 Agent 状态）
- `@/services/*`（实时通信与接口交互）
- `@/hooks/shared/useDraftPersistence`（与桌面 composer 共用的草稿持久化）
- `../speechKeyterms`（桌面与移动端共用的 STT 热词提取）
- `lucide-react`（统一语义图标）
- 父模块 [`../_ARCH.md`](../_ARCH.md)
