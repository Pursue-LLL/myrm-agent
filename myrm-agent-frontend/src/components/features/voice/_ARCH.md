# voice/

## 架构概述

语音输入/播报相关 UI。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `VoiceSessionOverlay.tsx` | 核心 | 全屏语音会话 UI：波形可视化、会话状态、 interim 转写与 barge-in 中断控制 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- `@/hooks/useVoiceSession` — 全双工语音会话编排
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
