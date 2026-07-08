# interactive-ui/

## 架构概述

Agent 在对话内渲染的声明式 UI（`UI_UPDATE` SSE → `uiArtifacts` → 组件树）。用户操作通过 i18n 用户消息回传 Agent；`<ui_action_data>` 仅 Agent 可见，聊天气泡由 `stripUserMessageDisplayText` 过滤。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `InteractiveUIDisplay.tsx` | 组件 | 多 surface 容器；artifact.title 为唯一用户可见标题 | — |
| `InteractiveUIRenderer.tsx` | 组件 | 递归渲染组件树（`.interactive-ui-container`） | — |
| `UIComponentRegistry.tsx` | 组件 | 组件 type → React 映射 | — |
| `UIComponentErrorBoundary.tsx` | 组件 | 单组件 fail-closed 边界 | — |
| `utils.ts` | 辅助 | `formatUIActionAsMessage`（Agent 载荷 + 用户可读正文） | ✅ |
| `components/UITable.tsx` | 组件 | 表格展示；`selectable` + `bindings.selected` 支持行勾选 | ✅ |
| `__tests__/` | 测试 | 组件与 `formatUIActionAsMessage` 回归 | — |

## 依赖

- `@/store/chat/types` — `UIArtifact`、`UIActionEvent`
- `@/lib/utils/messageUtils` — 展示层剥离 `ui_action_data`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
