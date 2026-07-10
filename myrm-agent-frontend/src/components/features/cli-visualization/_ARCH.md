# cli-visualization/

## 架构概述

Tauri 桌面端 CLI/ACP 工作区可视化：Diff 预览、文件树、文件预览与右键菜单。Web/SaaS 模式由 `workspace-browser/` 承担同类职责。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CLIDiffViewer.tsx` | 核心 | DiffViewer 薄包装（Tauri 阴影样式） | ✅ |
| `CLIWorkspaceTree.tsx` | 核心 | 工作区文件树（侧栏 ACP 模式） | ✅ |
| `CLIFilePreview.tsx` | 核心 | 选中文件内容预览面板 | — |
| `CLIFileIcon.tsx` | 辅助 | 扩展名 → 图标映射 | — |
| `CLIContextMenu.tsx` | 辅助 | 文件树右键菜单 | — |
| `hooks/useFilePreview.ts` | Hook | 预览状态（路径/类型/加载） | — |
| `hooks/useFileWatcher.ts` | Hook | 工作区变更监听 | — |

## 约束

- **禁止** `index.ts` 桶导出；消费者直引组件/hook 文件
- Diff 解析共用 `@/hooks/useDiffParser`、`@/lib/diff/parseUnifiedDiff`

## 依赖

- `@/lib/diff/DiffViewer` — 共享 Diff 渲染
- `@/store/useCLIAgentStore` — 工作目录
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
