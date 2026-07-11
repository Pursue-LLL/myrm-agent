# components/error-boundary/

## 架构概述

应用级错误边界与 Provider 配置错误弹窗，防止未捕获渲染错误导致白屏。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `GlobalErrorBoundary.tsx` | 核心 | React Error Boundary 包裹应用树 |
| `ProviderConfigErrorDialog.tsx` | 辅助 | 模型/Provider 配置缺失时的引导弹窗 |
| `index.ts` | 入口 | 桶导出；**`app/layout.tsx` 等 Server Component 须直接 `from './GlobalErrorBoundary'`**（Turbopack 经桶重导出 client 组件会触发 lazy Module 错误） |
| `__tests__/` | 测试 | 边界行为测试 |

## 依赖

- `@/components/primitives/*`
- 父模块 [`components/_ARCH.md`](../_ARCH.md)
