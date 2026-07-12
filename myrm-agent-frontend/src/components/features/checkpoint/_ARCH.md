# checkpoint/

## 架构概述

会话检查点与文件快照管理 UI。包含两套功能：
1. **Agent 任务检查点** (CheckpointList/Card) — 用于恢复中断的 Agent 任务
2. **文件快照** (FileSnapshotPanel/List/Card/DiffViewer) — 用于查看和恢复 Agent 操作产生的文件变更

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CheckpointCard.tsx` | 组件 | 单个 Agent 任务检查点卡片（时间/状态/恢复入口） | ✅ |
| `CheckpointList.tsx` | 组件 | Agent 任务检查点列表（恢复/删除/清理） | ✅ |
| `FileDiffViewer.tsx` | 核心 | 文件级 diff 视图，支持 checkbox 选择性恢复、行数统计显示 | ✅ |
| `FileSnapshotCard.tsx` | 组件 | 单个文件快照卡片（触发类型/文件数/时间戳） | ✅ |
| `FileSnapshotList.tsx` | 组件 | 文件快照列表（恢复/删除/清理/查看 diff） | ✅ |
| `FileSnapshotPanel.tsx` | 入口 | 浮动按钮 + 侧滑面板，集成到 ChatWindow | ✅ |

## 关键设计

- `FileSnapshotPanel` 从 `useChatStore.workspaceDir` 获取当前会话工作目录
- `FileDiffViewer` 支持 checkbox 多选文件，调用 `restoreFileSnapshot(id, files)` 进行部分恢复
- Diff 视图显示行数统计 `+X/-Y`（来自后端 `git diff --numstat`）
- 恢复操作有二次确认 dialog 防止误操作

## 依赖

- `@/store/useChatStore`（workspaceDir）
- `@/services/checkpoint`（API 调用层）
- `@/hooks/useToast`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
