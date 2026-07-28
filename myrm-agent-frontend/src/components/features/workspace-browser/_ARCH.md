# workspace-browser/

## 架构概述

工作区内嵌浏览器预览与检查器联动。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `WorkspaceDialogs.tsx` | 组件 | 工作区文件操作确认对话框 |
| `WorkspaceFileBrowser.tsx` | 核心 | 沙箱文件树浏览器；目录右键「AI 整理」→ 预填 organize prompt 到聊天输入框 |
| `WorkspaceFileOps.tsx` | 组件 | 上传/删除/重命名/移动；ContextMenu 含可选 `onOrganize` 目录整理入口 |
| `WorkspaceFilePreview.tsx` | 组件 | 选中文件内联预览 |
| `useWorkspaceFiles.ts` | Hook | 三部署 agent vault 文件树；register watch + SSE auto refresh（经 useGlobalEvents） |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
