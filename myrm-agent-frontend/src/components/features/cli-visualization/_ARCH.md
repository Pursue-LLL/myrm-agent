# cli-visualization/

## 架构概述

CLI 输出可视化与终端样式渲染。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CLIContextMenu.tsx` | 组件/模块 | — | — |
| `CLIDiffViewer.tsx` | 组件/模块 | — | — |
| `CLIFileIcon.tsx` | 组件/模块 | — | — |
| `CLIFilePreview.tsx` | 组件/模块 | — | — |
| `CLIWorkspaceTree.tsx` | 组件/模块 | — | — |
| `hooks/useFilePreview.ts` | Hook | CLI 文件预览状态 | — |
| `hooks/useFileWatcher.ts` | Hook | 工作区文件变更监听 | — |

## 依赖

- `@/lib/diff/DiffViewer`（共享 Diff 可视化组件，CLIDiffViewer 为薄包装层）
- `@/hooks/useDiffParser`、`@/lib/diff/parseUnifiedDiff`（diff 解析）
- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
