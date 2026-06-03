# components/

## 架构概述

React 组件根目录：`layout/` 应用壳层；`primitives/` shadcn/Radix 基元；`features/` 按业务域划分的 UI 模块；顶层 `auth/`、`billing/` 等横切小组件。

## 子模块

| 目录 | 地位 | 职责 | 文档 |
| ---- | ---- | ---- | ---- |
| `layout/` | 核心 | 侧栏、导航、PageLayout 壳层 | — |
| `primitives/` | 核心 | 可复用 UI 基元（button、dialog…） | [_ARCH.md](primitives/_ARCH.md) |
| `features/` | 核心 | 对话、设置、看板等业务 UI | [_ARCH.md](features/_ARCH.md) |
| `error-boundary/` | 核心 | 全局错误边界与 Provider 配置错误弹窗 | — |
| `auth/` | 辅助 | SaaS OAuth 与本机 WebUI 登录表单 | [_ARCH.md](auth/_ARCH.md) |
| `approval/` | 辅助 | 工具审批抽屉 | — |

## 依赖

- `@/hooks`、`@/store`、`@/services`、`@/lib/utils`
