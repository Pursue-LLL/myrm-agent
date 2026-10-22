# task-inspector/

## 架构概述

任务执行实时透视镜与技能调用时序可视化看板前端模块。
提供右侧抽屉式状态树与时序瀑布流、毫秒级耗时指标打点、技能输入/输出折叠预览面板，以及即时插嘴打断（Barge-In Steering）操作栏。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `taskInspectorTypes.ts` | 类型 | 任务节点、状态树、瀑布流、IO 指标与状态库契约类型（零 `any`） |
| `useTaskInspectorStore.ts` | 状态 | Zustand 状态管理，负责时序数据轮询/拉取、视图切换、节点选中与插嘴打断 |
| `TaskExecutionTimelineDrawer.tsx` | 组件 | 原生 `<dialog>` 抽屉，展示步骤状态树/瀑布流、毫秒级耗时、IO 徽章与插嘴打断交互 |
| `index.ts` | 门面 | 统一导出组件、状态库与契约类型 |
| `_ARCH.md` | 架构 | 模块架构设计说明与组件索引 |

## 依赖关系

- 父模块：[`../_ARCH.md`](../_ARCH.md)
- 后端 API：`GET /api/v1/tasks/{task_id}/timeline` & `POST /api/v1/tasks/{task_id}/interrupt`
- 国际化：`locales/{lang}.json` 的 `taskInspector` 命名空间
