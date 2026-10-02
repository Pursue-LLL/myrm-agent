# lib/utils/subagent/ 模块架构

## 架构概述

Subagent 数据域子包：subagent 树数据工具、任务拓扑图模型与阶段任务计数推导的纯函数集合，为 chat-window subagent 展示组件（树/甘特/洞察/工作地图）提供统一数据层。

## 文件清单

| 文件                        | 职责                                                                                                                              |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `subagentTree.ts`           | Subagent 树数据工具 — 构建树、子树聚合（成本/tokens/后代）、全局统计、排序、过滤、展平、格式化与预算/用量提取（成本经 `token_usage.total_cost_usd`，上限经 `budget.max_cost_usd`/`budget.budget_tokens`） |
| `taskTopologyModel.ts`     | 任务拓扑数据模型 — 纯函数把 subagent 树 / fission 拓扑转为 ReactFlow 可渲染图模型（节点/边/墓碑/焦点/进度/元数据、悬空边过滤、label 截断、状态 tone 映射；验证失败节点 tone 降级为 danger 并透传 verification 字段；fission 命名空间按 fission_id 隔离） |
| `stageTaskCount.ts`        | 阶段任务计数推导 — subagent 树节点推导 Scope/Fan-out/Verify/Synthesize 细粒度阶段进度（done/total 比率）与上游阻塞指示             |
| `index.ts`                  | 域聚合导出出口（显式符号清单护栏）                                                                                                 |
| `__tests__/`               | 三模块单元测试（随域内聚）                                                                                                        |

## 依赖

- `@/store/chat/useSubagentStore` — `SubagentNode` / `FissionTopology` 类型（type-only，零运行时耦合）

## 消费方

- `src/components/features/chat-window/subagent/` 展示组件群（树/甘特/洞察/工作地图/计数条/仪表盘/详情抽屉）
