# services/agent/evolution 模块架构


## 架构概述

技能进化调度引擎。负责承接来自底层的进化事件、协调后台异步调度任务并通知前端。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `engine.py` | 核心 | 技能进化辅助（Captured 技能提取 → EvolutionProposal → WebSocket 广播） | ✅ |
| `monitor_service.py` | 核心 | 业务层后台驻留服务。封装 Harness 的 `MetricMonitor`，定时触发错误扫描，并将生成的 `EvolutionProposal` 通过 ConfidenceApprovalFlow 处理。高分提议（具备通用性）将被静默自动合并 (Auto-Merge) 形成 Aha Moment，其余仍将作为草稿分发到 WebSocket。 | ✅ |
| `skill_immune_service.py` | 核心 | 技能免疫业务服务。监听 Harness 运行时技能失败证据（含 session/LoopGuard 元数据），执行业务分类、幂等去重、修复提案生成与审批落地 | ✅ |

## 依赖关系
- `myrm_agent_harness.agent.skills.evolution`
- `app.services.agent.confidence_approval_flow`
- `app.api.skills.ws_evolution`
