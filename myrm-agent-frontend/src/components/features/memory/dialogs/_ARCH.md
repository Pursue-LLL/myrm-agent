# memory/dialogs/

## 架构概述

记忆域对话框集合：创建、编辑、清空、归档恢复、导入审阅与共享规则配置。统一使用 `@/components/primitives` 的 Dialog 基元，文案走 `memory` i18n 命名空间。

## 文件清单

| 文件                              | 地位 | 职责                                                     | I/O/P |
| --------------------------------- | ---- | -------------------------------------------------------- | ----- |
| `MemoryCreateDialog.tsx`          | 核心 | 新建记忆：类型、内容、作用域录入                         | ✅    |
| `MemoryEditDialog.tsx`            | 核心 | 编辑既有记忆内容与元数据                                 | ✅    |
| `MemoryClearAllDialog.tsx`        | 核心 | 清空全部记忆的二次确认                                   | ✅    |
| `MemoryArchiveRestoreDialog.tsx`  | 核心 | 归档/恢复记忆的批量处置                                  | ✅    |
| `MemoryImportReviewDialog.tsx`    | 核心 | 导入记忆审阅：逐条接受/拒绝                              | ✅    |
| `ShareRulesDialog.tsx`            | 辅助 | 共享规则配置（跨会话/跨工作区规则共享）                  | ✅    |
| `ConnectWizardDialog.tsx`         | 辅助 | 记忆来源连接向导                                         | ✅    |

## 依赖

- `@/store/*`、`@/services/memory`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
