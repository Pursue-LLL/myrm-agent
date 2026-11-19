# task-card/

## 架构概述

任务卡片与后台任务摘要组件：图像 / 视频生成任务的进度、结果与失败、取消、过期状态。

## 文件清单

| 文件                      | 地位 | 职责                                                                                                                                                                                                   | I/O/P |
| ------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `ImageTaskCard.tsx`       | 核心 | 图像类后台任务进度与结果摘要卡片（支持进行中取消与重试；成功时按结果里的 `media://` 引用显示图片，只有存在于媒体库的图片才提供「编辑此图」；结果缺少图片或模型时明确提示「结果无法显示」，不渲染空白） | ✅    |
| `VideoTaskCard.tsx`       | 核心 | 视频类后台任务进度与结果摘要卡片（支持进行中取消与重试；成功时播放 `media://` 引用的视频）                                                                                                             | ✅    |
| `TaskCardExpired.tsx`     | 辅助 | 任务记录已不存在（30 天后被清理）的状态：说明生成的文件仍在媒体库并链接到 `/library`，取代永不结束的骨架屏                                                                                             | ✅    |
| `TaskCardNotice.tsx`      | 辅助 | 已取消、已过期、结果无法显示三种无结果状态共用的中性卡片外壳                                                                                                                                           | ✅    |
| `TaskCardError.tsx`       | 辅助 | 任务失败态展示（本地化文案、`interrupted` 提示、retry 状态与反馈）                                                                                                                                     | ✅    |
| `retryTask.ts`            | 辅助 | 任务重试请求与结构化错误解析（`detail={code,message,recoverable}`）                                                                                                                                    | ✅    |
| `useTaskRetry.ts`         | 辅助 | 任务重试共享状态钩子（loading/error/reset）                                                                                                                                                            | ✅    |
| `TaskCardPlaceholder.tsx` | 辅助 | 任务加载/生成中占位（展示进度、状态信息，支持原地取消与状态反馈）                                                                                                                                      | ✅    |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- `@/hooks/tasks/useTasksSubscription` — 任务订阅（`undefined` 加载中 / `null` 记录已不存在）
- `@/components/features/image-gen/*` — 图像结果展示与「编辑此图」动作
- `@/lib/api-url`（`getStorageUrl`）、`@/lib/mediaReference` — `media://` 引用解析
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
