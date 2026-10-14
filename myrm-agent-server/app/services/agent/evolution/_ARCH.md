# services/agent/evolution 模块架构


## 架构概述

技能进化调度引擎。负责承接来自底层的进化事件、协调后台异步调度任务并通知前端。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `engine.py` | 核心 | 技能草案提炼触发入口（`trigger_skill_evolution`）。由 `stream_finalize` 在 profile `skill_manage` ON 且 stream 正常结束时 fire-and-forget 调用。支持普通对话（从 ChatService 加载历史）和 DW 模式（直接传入 collector 内容）。引入 `SkillBudgetGovernor` 容量守卫做前检：只按技能**数量**设上限（默认 50，不按 token——技能正文按需加载，Compactor 另行核算本轮已加载正文），库满时暂停自动沉淀新技能（修复类进化不受限），并经全局 SSE 发布 `SKILL_CAPACITY_REACHED` 提示用户清理；同一 agent 作用域每次“填满”只提示一次，容量释放后再次填满才会重新提示；容量只用 `COUNT(*)` 读取，不加载技能正文；存储不可读时 fail-open。后台 task 调用 Harness 层 `SkillEvolutionEngine.capture_skill_from_trajectory`，通过 5 层安全管线后生成 `EvolutionProposal`，再交 `ConfidenceApprovalFlow` 处理（自动合并发布 `SKILL_EVOLVED`，其余进入审核队列）。**并发去重**：以 chat_id 为键的进程内任务表 `_RUNNING_EVOLUTION_TASKS` 保证同一 chat 的后台进化单飞；**触发门槛**：普通对话需 `tool_steps_count >= 3` 才触发。 | ✅ |
| `evolution_runtime.py` | 核心 | 技能进化运行时装配。启动期构建全局 `EvolutionIntegration`（进化模型、筛选器、后台队列），把队列产出的 `EvolutionProposal` 经 `ConfidenceApprovalFlow` 落地：高分且具备通用性的提议静默自动合并 (Auto-Merge，发布 `SKILL_EVOLVED`)，其余进入审核队列。修复提案只由失败事件（`skill_immune_service.py`）、轨迹切片与用户操作触发。 | ✅ |
| `skill_immune_service.py` | 核心 | 技能免疫业务服务。监听 Harness 运行时技能失败证据（含 session/LoopGuard 元数据），执行业务分类、幂等去重、修复提案生成与审批落地 | ✅ |

## 触发链路

```
finalize_agent_stream_session (stream_finalize.py)
  └── gate: session.params.enable_skill_manage
  └── trigger_skill_evolution (engine.py)
        ├── gate: 同 chat 进化任务已在飞 → 跳过（去重）
        ├── gate: 普通对话 tool_steps_count >= 3（仅 conversation_text 为空时）
        ├── gate: check_skill_budget_before_evolution（容量守卫：技能数达上限即暂停，并发布 SKILL_CAPACITY_REACHED，每次填满只提示一次）
        └── asyncio.create_task → _run_evolution_task
              ├── Load conversation (ChatService or DW content)
              ├── SkillEvolutionEngine.capture_skill_from_trajectory
              └── ConfidenceApprovalFlow.process_evolution（自动合并 → SKILL_EVOLVED；其余 → 审核队列）
```

## 依赖关系
- `myrm_agent_harness.agent.skills.evolution`
- `app.services.agent.confidence_approval_flow`
- `app.services.skills.evolution_events`（`SKILL_CAPACITY_REACHED` 发布）
- `app.services.agent.stream_session.stream_finalize` (caller)
