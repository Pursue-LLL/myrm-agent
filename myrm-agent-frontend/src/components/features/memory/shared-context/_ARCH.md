# memory/shared-context/

## 架构概述

共享上下文：把记忆作用域绑定到目标（工作区/会话），并提供健康度披露。面板与 hook 成对，绑定与健康横幅为可复用展示件。

## 文件清单

| 文件                                  | 地位 | 职责                                             | I/O/P |
| ------------------------------------- | ---- | ------------------------------------------------ | ----- |
| `SharedContextPanel.tsx`              | 门面 | 共享上下文主面板：目标绑定与健康状态编排         | ✅    |
| `SharedContextTargetBinding.tsx`      | 核心 | 共享上下文目标绑定 UI（选择并绑定作用域目标）     | ✅    |
| `SharedContextMemoryHealthBanner.tsx` | 辅助 | 共享记忆健康横幅（异常/降级提示）                | ✅    |
| `useSharedContextPanel.ts`            | 逻辑 | 面板状态与副作用封装                             | ✅    |

## 依赖

- `@/store/*`、`@/services/memory`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
