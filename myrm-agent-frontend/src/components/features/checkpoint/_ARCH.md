# checkpoint/

## 架构概述

会话检查点与文件快照管理 UI。包含两套功能：

1. **Agent 任务检查点** (CheckpointList/Card) — 展示中断的 Agent 任务，提供「重新发起」入口（将任务描述回填聊天输入框，让用户重跑任务）
2. **文件快照** (FileSnapshotPanel/List/Card/DiffViewer) — 用于查看和恢复 Agent 操作产生的文件变更

## 文件清单

| 文件                          | 地位 | 职责                                                       | I/O/P |
| ----------------------------- | ---- | ---------------------------------------------------------- | ----- |
| `CheckpointCard.tsx`          | 组件 | 单个 Agent 任务检查点卡片（时间/状态/重新发起入口）        | ✅    |
| `CheckpointList.tsx`          | 组件 | Agent 任务检查点列表（重新发起/删除/清理）                 | ✅    |
| `FileDiffViewer.tsx`          | 核心 | 文件级 diff 视图，支持 checkbox 选择性恢复、行数统计显示   | ✅    |
| `FileSnapshotCard.tsx`        | 组件 | 单个文件快照卡片（触发类型/文件数/时间戳）                 | ✅    |
| `FileSnapshotList.tsx`        | 组件 | 文件快照列表（创建版本/恢复/删除/清理/查看 diff）          | ✅    |
| `FileSnapshotPanel.tsx`       | 入口 | 浮动按钮 + 侧滑面板，集成到 ChatWindow                     | ✅    |
| `TaskAirbagCapsule.tsx`       | 组件 | 无人值守长任务的改动撤销入口胶囊（改动数量/审查入口；`refreshKey` 变化时重新读取，丢弃过期响应） | ✅    |
| `TimeTravelRollbackModal.tsx` | 核心 | 改动审查与一键撤销对话框（变动文件统计/外部影响说明/撤销或保留；成功后 `onResolved`）  | ✅    |
| `externalEffectLabels.ts`     | 工具 | 外部影响类别 → 多语言文案（文件快照卡片与撤销对话框共用）  | ✅    |

## 关键设计

- `FileSnapshotPanel` 从 `useChatStore.workspaceDir` 获取当前会话工作目录
- `FileSnapshotList` 提供「创建版本」手动快照入口（`POST /file-snapshot/create`，可选描述），成功后复用 SSE 刷新
- `FileDiffViewer` 支持 checkbox 多选文件，调用 `restoreFileSnapshot(id, files)` 进行部分恢复
- Diff 视图显示行数统计 `+X/-Y`（来自后端 `git diff --numstat`）
- 恢复操作有二次确认 dialog 防止误操作
- 撤销对话框恒定声明「撤销只还原工作区文件，数据库/容器/网络请求/git push 等外部操作不会被撤销」；运行中检测到的外部影响类别（服务端记入安全气囊）另列一行，文案复用 `fileSnapshot.effects.*`
- `GoalStatusHeader` 以 `status:turnsUsed` 作为胶囊 `refreshKey`，目标开始（首次布防）、每轮结束与状态变化时刷新；用户选择「保留改动」后服务端不再返回状态，胶囊随之消失
- 文案在 `taskAirbag` 命名空间（zh/en/ja/ko/de/zh-TW），不暴露内部 ID 或快照术语

## 依赖

- `@/store/useChatStore`（workspaceDir）
- `@/services/checkpoint`（API 调用层）
- `@/hooks/shared/useToast`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
