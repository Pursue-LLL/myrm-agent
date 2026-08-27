# workspace/

## 架构概述

工作区文件树、浏览器与沙箱文件操作 UI。

## 文件清单

| 文件                    | 地位 | 职责                                                                                                          |
| ----------------------- | ---- | ------------------------------------------------------------------------------------------------------------- |
| `ActiveSessionsBar.tsx` | 组件 | 工作区活跃会话标签栏                                                                                          |
| `PaneCard.tsx`          | 组件 | 多窗格布局卡片容器                                                                                            |
| `ReviewPanel.tsx`       | 组件 | 变更审阅侧栏（支持单文件 >300 行 Diff 默认折叠、代码差异片段一键复制、绑定工作区路径 workspacePath 徽章展示） |
| `WorkspaceLayout.tsx`   | 核心 | `/work` 多窗格工作区布局入口                                                                                  |

## 核心设计与交互规范

1. **会话级工作区路径绑定（Project-Scoped Workspace）**：
   - `ReviewPanel` 在顶部会话区域呈现当前绑定的物理/沙箱工作区路径徽章，路径经 `validateWorkspacePath` / `normalizeDisplayPath` 规范化。
2. **大文件 Diff 渲染优化**：
   - 单文件 Diff 行数超过阈值（300 行）时默认折叠中间内容，支持局部展开/收起，防止极端长 Diff 导致 DOM 卡顿。
   - 每个 Diff 代码块头部集成一键复制 Diff 差异内容功能。

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`、`@/lib/utils/pathValidation`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
