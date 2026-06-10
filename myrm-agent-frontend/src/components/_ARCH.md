# components/

## 架构概述

React 组件根目录：`layout/` 应用壳层；`primitives/` shadcn/Radix 基元；`features/` 按业务域划分的 UI 模块；顶层 `agent/`、`auth/`、`billing/`、`security/` 等横切小组件。

## 子模块

| 目录 | 地位 | 职责 | 文档 |
| ---- | ---- | ---- | ---- |
| `layout/` | 核心 | 侧栏、导航、PageLayout 壳层 | [_ARCH.md](layout/_ARCH.md) |
| `primitives/` | 核心 | 可复用 UI 基元（button、dialog…） | [_ARCH.md](primitives/_ARCH.md) |
| `features/` | 核心 | 对话、设置、看板等业务 UI | [_ARCH.md](features/_ARCH.md) |
| `agent/` | 辅助 | Agent 头像、选择器、编辑表单（多 feature 共用） | [_ARCH.md](agent/_ARCH.md) |
| `error-boundary/` | 核心 | 全局错误边界与 Provider 配置错误弹窗 | [_ARCH.md](error-boundary/_ARCH.md) |
| `auth/` | 辅助 | SaaS OAuth 与本机 WebUI 登录表单 | [_ARCH.md](auth/_ARCH.md) |
| `security/` | 辅助 | Security Center 页面（`/security`） | [_ARCH.md](security/_ARCH.md) |
| `billing/` | 辅助 | Work Unit 门禁、预算弹窗、配额展示 | [_ARCH.md](billing/_ARCH.md) |
| `approval/` | 辅助 | 工具审批抽屉与多态审批卡片 | [_ARCH.md](approval/_ARCH.md) |

## 依赖

- `@/hooks` — 见 [hooks/_ARCH.md](../hooks/_ARCH.md)
- `@/store`、`@/services`
- `@/lib` — 见 [lib/_ARCH.md](../lib/_ARCH.md)
