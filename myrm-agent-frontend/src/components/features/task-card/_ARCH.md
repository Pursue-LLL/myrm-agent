# task-card/

## 架构概述

任务卡片与后台任务摘要组件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ImageTaskCard.tsx` | 核心 | 图像类后台任务进度与结果摘要卡片 | ✅ |
| `VideoTaskCard.tsx` | 核心 | 视频类后台任务进度与结果摘要卡片 | ✅ |
| `TaskCardError.tsx` | 辅助 | 任务失败/error 态统一展示（含本地化文案、retry 中状态与失败反馈） | ✅ |
| `retryTask.ts` | 辅助 | 任务重试请求与结构化错误解析（`detail={code,message,recoverable}`） | ✅ |
| `useTaskRetry.ts` | 辅助 | 任务重试共享状态钩子（loading/error/reset） | ✅ |
| `TaskCardPlaceholder.tsx` | 辅助 | 任务加载中 skeleton 占位 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
