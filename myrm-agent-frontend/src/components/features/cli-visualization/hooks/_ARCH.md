# cli-visualization/hooks/

## 架构概述

CLI 工作区侧边栏专用 hooks：文件预览状态与文件系统变更监听。仅 Tauri + ACP 模式由 `ChatSidebarContent` 消费。

## 文件清单

| 文件 | 职责 |
|------|------|
| `useFilePreview.ts` | 选中文件预览状态（路径、内容类型、加载/错误） |
| `useFileWatcher.ts` | 工作区目录变更轮询/监听，触发树刷新 |

## 依赖

- `@/store/useCLIAgentStore` — 工作目录根路径
- 父模块 [`../_ARCH.md`](../_ARCH.md)

## 约束

- Diff 解析共用 `@/hooks/useDiffParser`，不在此目录重复实现
