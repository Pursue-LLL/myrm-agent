# memory/insights/

## 架构概述

记忆洞察展示层：健康仪表盘、知识图谱与共享上下文预览。只读视图，数据由 store/服务层提供。

## 文件清单

| 文件                          | 地位 | 职责                                                         | I/O/P |
| ----------------------------- | ---- | ------------------------------------------------------------ | ----- |
| `MemoryHealthDashboard.tsx`   | 核心 | 记忆健康仪表盘：容量、召回质量与医生诊断指标可视化           | ✅    |
| `MemoryKnowledgeGraph.tsx`    | 核心 | 记忆知识图谱（节点/边关系探索）                              | ✅    |
| `RankedHubSidebar.tsx`        | 辅助 | 图谱枢纽侧栏：按连接度排序的中心节点列表                     | ✅    |
| `GraphEmptyState.tsx`         | 辅助 | 图谱空态与引导                                               | ✅    |
| `MemoryContextPanel.tsx`      | 辅助 | Shared Context 编辑预览面板                                  | ✅    |
| `BehavioralMetricsPanel.tsx`  | 辅助 | 零大模型开销行为特征看板                                     | ✅    |

## 依赖

- `@/store/*`、`@/services/memory`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
