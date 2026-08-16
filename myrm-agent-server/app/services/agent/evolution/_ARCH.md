# services/agent/evolution 模块架构


## 架构概述

技能进化调度引擎。负责承接来自底层的进化事件、协调后台异步调度任务并通知前端。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `engine.py` | 核心 | 技能草案提炼触发入口（`trigger_skill_evolution`）。由 `stream_finalize` 在 profile `skill_manage` ON 且 stream 正常结束时 fire-and-forget 调用。支持普通对话（从 ChatService 加载历史）和 DW 模式（直接传入 collector 内容）。后台 task 调用 Harness 层 `SkillEvolutionEngine.capture_skill_from_trajectory`，通过 5 层安全管线后生成 `EvolutionProposal`，再经 `ConfidenceApprovalFlow` 处理并 WebSocket 广播。**并发去重**：以 chat_id 为键的进程内任务表 `_RUNNING_EVOLUTION_TASKS` 保证同一 chat 的后台进化单飞（asyncio task name 不约束唯一性），任务完成/取消后自动清理；**触发门槛**：普通对话需 `tool_steps_count >= 3` 才触发（对齐 OpenClaw「substantial work」启发，抑制简单对话的无意义捕获），DW 模式（提供 `conversation_text`）不设门槛。 | ✅ |
| `monitor_service.py` | 核心 | 业务层后台驻留服务。封装 Harness 的 `MetricMonitor`，定时触发错误扫描，并将生成的 `EvolutionProposal` 通过 ConfidenceApprovalFlow 处理。高分提议（具备通用性）将被静默自动合并 (Auto-Merge) 形成 Aha Moment，其余仍将作为草稿分发到 WebSocket。 | ✅ |
| `skill_immune_service.py` | 核心 | 技能免疫业务服务。监听 Harness 运行时技能失败证据（含 session/LoopGuard 元数据），执行业务分类、幂等去重、修复提案生成与审批落地 | ✅ |

## 触发链路

```
finalize_agent_stream_session (stream_finalize.py)
  └── gate: session.params.enable_skill_manage
  └── trigger_skill_evolution (engine.py)
        ├── gate: 同 chat 进化任务已在飞 → 跳过（去重）
        ├── gate: 普通对话 tool_steps_count >= 3（仅 conversation_text 为空时）
        └── asyncio.create_task → _run_evolution_task
              ├── Load conversation (ChatService or DW content)
              ├── SkillEvolutionEngine.capture_skill_from_trajectory
              ├── ConfidenceApprovalFlow.process_evolution
              └── broadcast_proposal (WebSocket)
```

## 依赖关系
- `myrm_agent_harness.agent.skills.evolution`
- `app.services.agent.confidence_approval_flow`
- `app.services.skills.ws_hub`
- `app.services.agent.stream_session.stream_finalize` (caller)
