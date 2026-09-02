# services/commands/

## 架构概述

Slash 命令业务执行与自然语言调度解析服务层。供 `builtinActions.ts` 与输入框交互复用。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `loopSlashCommand.ts` | 核心 | `/loop` 自然语言时间解析、Profile 与会话绑定、创建 Cron 任务并执行即时首跑 | ✅ |
| `__tests__/loopSlashCommand.test.ts` | 辅助 | `loopSlashCommand` 自然语言解析、Toast 反馈与执行流单元测试 | ✅ |

## 依赖

- `@/services/cron` — Cron 任务创建与即时触发 API
- `@/store/useChatStore` — 当前会话 `chatId`、流式状态与 `selectedPersona`
- `@/services/i18nToastService` — 多语言 Toast 通知
