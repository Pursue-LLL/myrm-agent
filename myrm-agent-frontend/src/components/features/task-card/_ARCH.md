# task-card/

## 架构概述

任务卡片与后台任务摘要组件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ImageTaskCard.tsx` | 核心 | 图像类后台任务进度与结果摘要卡片 | ✅ |
| `TaskCardError.tsx` | 辅助 | 任务失败/error 态统一展示 | ✅ |
| `TaskCardPlaceholder.tsx` | 辅助 | 任务加载中 skeleton 占位 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
