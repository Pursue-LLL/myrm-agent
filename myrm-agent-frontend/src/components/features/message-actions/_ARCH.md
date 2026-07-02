# message-actions/

## 架构概述

消息操作菜单（复制、分支、反馈等）与文件变更撤销。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `Copy.tsx` | 组件/模块 | — | — |
| `ExtractToSkillButton.tsx` | 组件/模块 | 一键提炼 assistant 消息为可复用技能（通过 /learn 命令触发技能进化管线） | — |
| `ExportMenu.tsx` | 组件/模块 | — | — |
| `MemoryFeedback.tsx` | 组件/模块 | — | — |
| `ReadAloud.tsx` | 组件/模块 | — | — |
| `RegenerateMenu.tsx` | 组件/模块 | — | — |
| `RevertFiles.tsx` | 组件/模块 | 消息级文件变更撤销（每条 AI 回复旁） | — |
| `SessionRevertButton.tsx` | 组件/模块 | 会话级一键撤销所有 AI 文件变更（调用 POST /files/revert/session） | — |
| `SaveEvalCase.tsx` | 组件/模块 | — | — |
| `SaveToMemoryButton.tsx` | 组件/模块 | 一键保存 assistant 消息到长期记忆（调用 createMemory API） | — |
| `SaveToWikiButton.tsx` | 组件/模块 | — | — |
| `SiblingNav.tsx` | 组件/模块 | — | — |
| `SourcesButton.tsx` | 组件/模块 | 消息来源 Sheet 面板（web/mcp/conversation 三种类型差异化展示与操作） | ✅ |
| `Undo.tsx` | 组件/模块 | — | — |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
