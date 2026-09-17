# workspace/

## 架构概述

工作区文件树、浏览器与沙箱文件操作 UI。

## 文件清单

| 文件                    | 地位 | 职责                                                                                                          |
| ----------------------- | ---- | ------------------------------------------------------------------------------------------------------------- |
| `ActiveSessionsBar.tsx` | 组件 | 工作区活跃会话标签栏                                                                                          |
| `PaneCard.tsx`          | 组件 | 多窗格布局卡片容器                                                                                            |
| `ReviewPanel.tsx`       | 组件 | 变更审阅侧栏（文件头虚拟化 + 检索/状态过滤、单文件 >300 行 Diff 默认折叠、截断提示、一键复制、workspacePath 徽章） |
| `ReviewDiffRow.tsx`     | 组件 | 单文件差异行（rawDiff 懒计算、DiffViewer 高亮渲染、增删统计与超大文件提示） |
| `WorkspaceLayout.tsx`   | 核心 | `/work` 多窗格工作区布局入口                                                                                  |

## 核心设计与交互规范

1. **会话级工作区路径绑定（Project-Scoped Workspace）**：
   - `ReviewPanel` 在顶部会话区域呈现当前绑定的物理/沙箱工作区路径徽章，路径经 `validateWorkspacePath` / `normalizeDisplayPath` 规范化。
2. **大文件 Diff 渲染优化**：
    - 文件头列表超过 30 项时启用虚拟滚动（`@tanstack/react-virtual` 动态测量），小列表直接渲染，避免测量开销；行身份按消息隔离，同文件多行互不串扰；检索/过滤变更时滚动复位。
    - 单文件 Diff 行数超过阈值（300 行）时默认折叠，展开详情由 `lib/diff/DiffViewer` 高亮渲染。
    - 超大文件（>512KB）仅展示增删统计与提示，不回传原文、不做全量高亮。
    - 移动端通过底部抽屉打开审查面板（桌面端为右侧常驻栏）。
    - 每个 Diff 代码块头部集成一键复制 Diff 差异内容功能。

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`、`@/lib/utils/pathValidation`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
