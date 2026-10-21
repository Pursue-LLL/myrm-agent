# observability/timeline/

## 架构概述

任务执行时序透视镜与技能调用追踪服务层实现。
维护单例 `TaskTimelineInspectorService`，统一管理各任务的 `TaskExecutionTimelineCollector` 实例，提供实时状态树与瀑布流结构快照序列化，并支持即时插嘴打断（Barge-in Interrupt）指令分发。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `TaskTimelineInspectorService` | — |
| `service.py` | 核心 | 任务步骤追踪、毫秒级耗时指标记录、插嘴打断与快照序列化 | ✅ |
| `_ARCH.md` | 架构 | 模块架构设计说明与组件索引 | — |

## 依赖关系

### 内部依赖
- `myrm_agent_harness.observability.timeline_visualizer` — 框架层时序采集与数据模型

### 被依赖方
- `app/api/tasks/timeline_router.py` — GET `/api/v1/tasks/{task_id}/timeline` & POST `/api/v1/tasks/{task_id}/interrupt`
