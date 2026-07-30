# lib/wiki/

## 架构概述

Wiki 证据与 claim 相关的跨 surface 纯函数（Chat citation drawer + Settings 概念详情）。无 React 组件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `claimStatusDisplay.ts` | 核心 | claim 状态 CSS class、i18n label 映射、drawer 降噪规则（仅 contested/unsupported 展示 badge） | ✅ |
| `__tests__/claimStatusDisplay.test.ts` | 测试 | claimStatusDisplay 单测 | ✅ |

## 依赖

- 不依赖 `@/components`（components → lib 单向）

## 消费方

- `components/features/message-box/SourceChunkDrawer.tsx`
- `components/features/settings/sections/knowledge/wiki/WikiConceptDetailPanel.tsx`
