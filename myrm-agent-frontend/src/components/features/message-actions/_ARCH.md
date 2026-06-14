# message-actions/

## 架构概述

单条消息操作菜单（复制、分支、反馈等）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `Copy.tsx` | 组件/模块 | — | — |
| `ExportMenu.tsx` | 组件/模块 | — | — |
| `MemoryFeedback.tsx` | 组件/模块 | — | — |
| `ReadAloud.tsx` | 组件/模块 | — | — |
| `RegenerateMenu.tsx` | 组件/模块 | — | — |
| `RevertFiles.tsx` | 组件/模块 | — | — |
| `SaveEvalCase.tsx` | 组件/模块 | — | — |
| `SaveToWikiButton.tsx` | 组件/模块 | — | — |
| `SiblingNav.tsx` | 组件/模块 | — | — |
| `SourcesButton.tsx` | 组件/模块 | 消息来源 Sheet 面板（web/mcp/conversation 三种类型差异化展示与操作） | ✅ |
| `Undo.tsx` | 组件/模块 | — | — |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
