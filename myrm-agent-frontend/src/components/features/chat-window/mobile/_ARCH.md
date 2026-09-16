# mobile/

## 架构概述

移动端 Command Center 交互层：专为移动触控与窄屏场景优化的命令中心视图、审批控制、长按确认、操作 Sheet、以及紧凑型快捷辅助输入栏与提示词历史管理。

## 文件清单

| 文件                                     | 地位      | 职责                                                                                                                                         | I/O/P |
| ---------------------------------------- | --------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `MobileStatusBoard.tsx`                  | 核心      | 移动端 Command Center 壳层（审批/预览/进度/快捷输入/辅助栏 + Co-Pilot chip/Advisor；run 中「查看完整对话」→ 主 Chat 复用 QuoteToolbar 划词） | ✅    |
| `MobileQuickControlAccessoryToolbar.tsx` | 组件      | 移动端软键盘上方高频控制辅助栏：历史漫游、剪贴板无损粘贴、一键呼出顾问面板、一键清空                                                         | ✅    |
| `useMobilePromptHistory.ts`              | 核心 Hook | 移动端会话隔离提示词历史漫游状态机：LRU 历史栈、用户草稿暂存保护、循环步进导航                                                               | ✅    |
| `HoldToApproveButton.tsx`                | 组件      | 移动端高危审批长按确认按钮（700ms 动态环形进度条与触觉振动反馈防误触）                                                                       | ✅    |
| `MobileActionSheet.tsx`                  | 组件      | 移动端底部动作 Sheet（`useMobileSheetEntries` 驱动）                                                                                         | ✅    |
| `MobilePushDiscoveryBanner.tsx`          | 组件      | 移动端 Web Push 发现与一键授权引导横幅（PWA 离线任务与审批通知）                                                                             | ✅    |
| `MobileStatusApprovalsSection.tsx`       | 组件      | 移动端待审批队列区块                                                                                                                         | ✅    |
| `MobileStatusLivePreview.tsx`            | 组件      | 浏览器/桌面 Live Preview 与 Lightbox 查看器                                                                                                  | ✅    |
| `MobileStatusMessageBody.tsx`            | 组件      | 进度/验证/思考/结果/Artifact 交付物列表与 Plan 步骤                                                                                          | ✅    |
| `useMobileSheetEntries.tsx`              | 辅助 Hook | 移动端动作 Sheet 条目定义与路由分发                                                                                                          | ✅    |

## 依赖

- `@/store/*`（会话与 Agent 状态）
- `@/services/*`（实时通信与接口交互）
- `lucide-react`（统一语义图标）
- 父模块 [`../_ARCH.md`](../_ARCH.md)
