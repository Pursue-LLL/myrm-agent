# components/approval/

## 架构概述

工具审批（HITL）的 React UI 壳层：全局 Drawer 与多态审批卡片。决策逻辑、resume payload、visual 上下文在 `lib/approval/`；队列状态在 `@/store`。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `ApprovalDrawer.tsx` | 核心 | 全局审批抽屉（subagent 批量 decisions） |
| `PolymorphicApprovalCard.tsx` | 核心 | 单条工具审批卡片（shell/MCP/视觉等形态） |
| `__tests__/` | 测试 | 组件级测试 |

## 依赖

- `@/lib/approval/*` — 见 [lib/approval/_ARCH.md](../../lib/approval/_ARCH.md)
- `@/hooks/useToolApprovalResolve.ts` 等
- `@/store` 审批队列

## 与 lib/approval 边界

- **本目录**：React 组件与交互
- **lib/approval**：纯函数、resume 构建、visual 解析
