# recall-simulator 模块架构

## 架构概述

记忆与经验基因交互式召回模拟沙盒与可视化二次治理工作台（对标 EvoX 召回测试与治理中心）。
用于透明化验证任意输入 Prompt 的多路命中逻辑（BM25 词法、向量余弦、因果经验基因匹配与 RRF 融合分），并提供单条记忆/基因在召回现场的交互式二次治理（置信度滑块、负向防坑标记、锁定/禁用与去重合并）。

## 核心文件

| 文件 | 地位 | 职责 |
|------|------|------|
| `recallSimulatorTypes.ts` | 核心 | 契约层：请求/响应、候选条目、多路分数字段与治理更新类型定义 |
| `recallSimulatorService.ts` | 核心 | 服务层：调用 `/api/memory/simulate-recall` 与 `/govern`，提供高保真离线 fallback |
| `MemorySecondaryGovernanceToolbar.tsx` | 核心组件 | 单条记忆治理工具条：置信度滑块 0.0~1.0、负向防坑切换、锁定/禁用、合并去重 |
| `MemoryRecallSimulator.tsx` | 核心组件 | 沙盒工作台抽屉：动态 Prompt 输入、耗时/命中数 KPI、Top-K 记忆片段卡片流与三维打分 |
| `index.ts` | 门面 | 统一导出所有组件与类型 |

## 依赖关系

- 父模块：`components/features/memory/command-center/_ARCH.md`
- 图标库：`lucide-react`（零原生 emoji）
- 国际化：`next-intl`（`memoryRecall` 命名空间）
