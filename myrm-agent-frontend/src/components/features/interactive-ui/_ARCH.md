# interactive-ui/

## 架构概述

Agent 交互式 UI 组件（表单、卡片等 SSE UI_UPDATE 渲染）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `InteractiveUIDisplay.tsx` | 组件/模块 | — | — |
| `InteractiveUIRenderer.tsx` | 组件/模块 | — | — |
| `UIComponentErrorBoundary.tsx` | 组件/模块 | — | — |
| `UIComponentRegistry.tsx` | 组件/模块 | — | — |
| `components/` | 目录 | 子模块 | — |
| `utils.ts` | 组件/模块 | — | — |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
