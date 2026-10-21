# memory/hooks/

## 架构概述

记忆域自定义 hooks：封装跨组件复用的记忆动作与状态派生逻辑。

## 文件清单

| 文件                                | 地位 | 职责                                        | I/O/P |
| ----------------------------------- | ---- | ------------------------------------------- | ----- |
| `useMemoryArchiveRestoreActions.ts` | 核心 | 归档/恢复记忆的动作封装（含批量与错误处置） | ✅    |
| `useMemoryDemoSeed.ts`              | 辅助 | 演示数据种子注入（引导与空态体验）          | ✅    |
| `useMemoryCommandCenterActions.ts`  | 核心 | 命令中心写操作：治理决策、Doctor 修复、导入回滚、整合回滚、归档导出与迁移向导跳转 | ✅    |

## 依赖

- `@/store/*`、`@/services/memory`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
