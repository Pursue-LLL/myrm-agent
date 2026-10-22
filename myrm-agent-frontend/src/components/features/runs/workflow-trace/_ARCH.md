# workflow-trace 模块架构

## 架构概述

多步骤工作流全景执行轨迹可视化、节点级快照审计与断点重放驾驶舱（对标生产级 Workflow 结构化载体与复盘要求）。
用于展示复杂 Agent 任务的五阶全生命周期链路（需求接入 ➔ 拆解规划 ➔ 调度流转 ➔ 分步执行与校验 ➔ 终态闭环），支持节点级全息审计快照展开（Prompt 摘要、工具序列、中间产物、四维评分雷达），并支持基于前序节点快照缓存的就地参数修改与断点自愈重放。

## 核心文件

| 文件 | 地位 | 职责 |
|------|------|------|
| `workflowTraceTypes.ts` | 核心 | 契约层：五阶段枚举、状态、四维校验雷达、节点快照与断点重放请求/响应契约 |
| `workflowTraceService.ts` | 核心 | 服务层：调用 `/api/v1/workflow/{id}/trace` 与 `/replay-from-node`，提供离线保底 fallback |
| `WorkflowNodeAuditDrawer.tsx` | 核心组件 | 抽屉视图：节点全息快照审计、四维评分展示、参数就地覆盖与断点自愈重放触发 |
| `WorkflowSwimlaneViewer.tsx` | 核心组件 | 泳道图谱：五阶动态链路、状态指示徽章、耗时/Token 指标与节点点击交互 |
| `index.ts` | 门面 | 统一导出所有组件与类型 |

## 依赖关系

- 父模块：`components/features/runs/_ARCH.md`
- 图标库：`lucide-react`（零原生 emoji）
- 国际化：`next-intl`（`workflowTrace` 命名空间）
