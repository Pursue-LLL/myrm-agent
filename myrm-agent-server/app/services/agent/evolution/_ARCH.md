# services/agent/evolution 模块架构


## 架构概述

技能进化调度。负责承接来自底层的进化事件、协调后台异步调度任务并通知前端。新技能的自动沉淀不在本包：由 Harness 后台复盘经 `services/skills/growth/lifecycle.py` 编排（含高危新增复核）；本包只处理已有技能的修复/衍生/优化提案。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `evolution_runtime.py` | 核心 | 技能进化运行时装配。启动期构建全局 `EvolutionIntegration`（进化模型、筛选器、后台队列），把队列产出的 `EvolutionProposal` 经 `ConfidenceApprovalFlow` 落地：高分且具备通用性的提议静默自动合并 (Auto-Merge，发布 `SKILL_EVOLVED`)，其余进入审核队列。修复提案只由失败事件（`skill_immune_service.py`）、轨迹切片与用户操作触发。 | ✅ |
| `skill_immune_service.py` | 核心 | 技能免疫业务服务。监听 Harness 运行时技能失败证据（含 session/LoopGuard 元数据），执行业务分类、幂等去重、修复提案生成与审批落地 | ✅ |

## 触发链路

```
进化事件（工具失败证据 / 轨迹切片 / 用户操作）
  ├── skill_immune_service.py → 修复提案
  └── evolution_runtime.py → 后台队列 → EvolutionProposal
        └── ConfidenceApprovalFlow.process_evolution
              ├── 多信号风控（diff 幅度 / 历史成功率 / 新增 HIGH 级安全发现）
              └── 自动合并 → SKILL_EVOLVED；其余 → 审核队列
```

## 依赖关系
- `myrm_agent_harness.agent.skills.evolution`
- `app.services.agent.confidence_approval_flow`
- `app.services.skills.evolution_events`（`SKILL_EVOLVED` 发布）
