# workspace/

## 架构概述

工作区文件树、浏览器与沙箱文件操作 UI。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `ActiveSessionsBar.tsx` | 组件 | 工作区活跃会话标签栏 |
| `PaneCard.tsx` | 组件 | 多窗格布局卡片容器 |
| `ReviewPanel.tsx` | 组件 | 变更审阅侧栏 |
| `WorkspaceLayout.tsx` | 核心 | `/work` 多窗格工作区布局入口 |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
