# app/intent/

## 架构概述

Web deep-link 落地路由。承接 `/intent/*`，交由 `IntentDispatcher` 分发到聊天、设置或 FlowPad。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `[...segments]/page.tsx` | 核心 | 解析并分发 `/intent/*`；对 `ask` intent 分发后回到 `/`；通过 `useRef` 保证单次分发 | ✅ |

## 依赖

- `@/lib/intent-dispatcher` — UIP 解析与执行
- `@/store/useFlowPadStore` — `ask` intent 打开 FlowPad
- 父模块 [`../_ARCH.md`](../_ARCH.md)
