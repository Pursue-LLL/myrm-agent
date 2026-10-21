# deliverable/

## 架构概述

Workspace 交付物在 ArtifactPortal 中的打开与内容拉取 SSOT（`/files/browse/content` + `chat_id`）。

## 文件清单

| 文件                           | 地位 | 职责                                                                                         | I/O/P |
| ------------------------------ | ---- | -------------------------------------------------------------------------------------------- | ----- |
| `openWorkspaceFileInPortal.ts` | 核心 | `resolveWorkspaceDirForBrowse` / `fetchWorkspaceBrowseContent` / `openWorkspaceFileInPortal` | ✅    |
| `openWorkspaceDeliverable.ts`  | 门面 | `DeliverableReferenceLink` 用的 workspace/artifact 打开入口                                  | ✅    |

## 依赖

- `@/store/useArtifactPortalStore`、`@/store/useChatStore`
- `@/services/chat`（lazy `getChatDetail` 解析 workspace_dir）
- 父模块 [`services/_ARCH.md`](../_ARCH.md)
