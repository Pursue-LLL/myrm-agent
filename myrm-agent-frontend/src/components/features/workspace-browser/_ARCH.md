# workspace-browser/

## 架构概述

工作区内嵌浏览器预览与检查器联动。

## 文件清单

| 文件                       | 地位 | 职责                                                                                                                     |
| -------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------ |
| `WorkspaceDialogs.tsx`     | 组件 | 工作区文件操作确认对话框                                                                                                 |
| `WorkspaceFileBrowser.tsx` | 核心 | 沙箱文件树浏览器；目录右键「AI 整理」或「设为项目根目录」→ 联动聊天与 Project Scoped 边界 |
| `WorkspaceFileOps.tsx`     | 组件 | 上传/删除/重命名/移动；ContextMenu 含 `onOrganize` 与 `onSetProjectRoot` 入口 |
| `WorkspaceFilePreview.tsx` | 组件 | 选中文件内联预览；文本走行号编辑器与内嵌 Inline Diff 审查；富媒体委托 `RichMediaFilePreview` |
| `InlineWorkspaceDiff.tsx`  | 组件 | 工作区代码即时 Diff 对比抽屉/面板 |
| `RichMediaFilePreview.tsx` | 组件 | 富媒体（图片/音视频/PDF/Office/SVG）预览分发；`getPreviewKind` 扩展名路由 + `kind` prop 覆盖；图片禁用 artifact 编辑按钮 |
| `useWorkspaceFiles.ts`     | Hook | 三部署 agent vault 文件树；register watch + SSE auto refresh（经 useGlobalEvents）                                       |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
