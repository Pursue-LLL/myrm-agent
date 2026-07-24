# progress-steps/

## 架构概述

Agent 执行进度步骤 UI：折叠/展开 Task Steps 树、多态 step 渲染。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ProgressSteps.tsx` | 核心 | 进度步骤树与折叠面板 | ✅ |
| `utils.ts` | 辅助 | 步骤标题、items 类型推断、错误 linkify | ✅ |
| `treeUtils.ts` | 辅助 | progressSteps 树构建 | ✅ |
| `toolIcons.tsx` | 辅助 | 步骤图标与 agent 主题色 | ✅ |
| `ArchiveRestoreStepAction.tsx` | 组件 | 归档恢复步骤操作 | ✅ |
| `ArchiveRestoreResultChip.tsx` | 组件 | 归档恢复结果 chip | ✅ |
| `useScrollbarStyles.ts` | 辅助 | 展开面板滚动条样式 | ✅ |
| `renderers/` | 目录 | 步骤叶子渲染（终端、代码、evicted drawer 等） | [_ARCH.md](renderers/_ARCH.md) |
| `__tests__/` | 测试 | ProgressSteps / utils / ArchiveRestore 单测 | — |

## 依赖

- `@/store/useChatStore` — `updateMessages`（immer updater，禁止误用 `setMessages`）
- `@/store/chat/messageStream/handlers/statusStreamProgressSteps.ts` — STATUS progress step reducer

## 约束

- 可变 store 更新必须使用 `updateMessages`，与 stream handlers 一致。
