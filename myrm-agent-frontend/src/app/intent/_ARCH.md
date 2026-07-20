# app/intent/

## 架构概述

Web deep-link 落地路由。承接 `/intent/*`，交由 `IntentDispatcher` 分发到聊天、设置或 FlowPad。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `[...segments]/page.tsx` | 核心 | 解析并分发 `/intent/*`；页面层单次解析并传给 dispatcher；对 `ask` intent 或分发失败回到 `/`；通过 `useRef` 保证单次分发 | ✅ |

## 测试

| 路径 | 职责 |
|------|------|
| `[...segments]/page.test.tsx` | 页面级回归：`ask` 单次分发 + 非法 intent 回首页 + 非 ask 成功不回跳 + 非 ask 失败兜底回首页 |

## 依赖

- `@/lib/intent-dispatcher` — UIP 解析与执行
- `@/store/useFlowPadStore` — `ask` intent 打开 FlowPad
- 父模块 [`../_ARCH.md`](../_ARCH.md)
