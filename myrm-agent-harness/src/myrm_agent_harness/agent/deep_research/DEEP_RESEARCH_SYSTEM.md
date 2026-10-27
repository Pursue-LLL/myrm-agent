# Deep Research System Design

> 多阶段深度研究编排器。澄清（可选）→ 规划 → 本地探索（可选）→ 并行 research agents → 报告合成。

---

## 设计目标

1. **阶段化编排**：orchestrator 驱动主事件循环，阶段实现分离在 mixin
2. **结构化澄清**：复用 `meta_tools/clarification/` 的 ask_question 能力
3. **并行研究**：多 research agent 分派，结果聚合为最终报告
4. **编排信号**：orchestrator 通过 `agent/orchestration/signals/deep_research.py` 注入 3 个 JSON schema（非 Action Tool）

---

## 系统架构

```
DeepResearchOrchestrator (orchestrator.py)
    │ inherits the plan/research, dispatch and phases mixins
    ▼
┌──────────────┬──────────────────┬──────────────┐
│ Clarification│ Research dispatch │ Report gen   │
│ (_phases)    │ (_dispatch)       │ (_phases)    │
└──────────────┴──────────────────┴──────────────┘
         │                │
         ▼                ▼
   clarification/     sub_agents spawn
   (ask_question)     + meta_tools
```

---

## 核心文件

| 文件 | 职责 |
|------|------|
| `orchestrator.py` | 主事件循环与阶段编排入口 |
| `_orchestrator_phases.py` | 澄清 / 报告生成 mixin |
| `_orchestrator_dispatch.py` | research agent 并行分派 mixin（`_dispatch_research_agents`），每个 agent 在自己的守卫上运行 |
| `_orchestrator_plan_research.py` | 规划 + 研究循环 mixin（`_phase_plan` / `_phase_research`） |
| `config.py` | 配置与类型定义 |
| `prompts.py` | 全阶段 prompt 模板 |
| `../orchestration/signals/deep_research.py` | Orchestrator 用 3 个编排信号 schema |
| `helpers.py` | 无状态辅助函数 |

---

## 报告上下文装配

- 研究循环内，orchestrator 的 `ToolMessage` 至多携带 `ORCHESTRATOR_RESULT_CHAR_LIMIT` 个字符的 research 结果（超出部分截断）；消息总量超出预算时，较早的 `ToolMessage` 被压缩为首行摘要（≤180 字符，`compact_orch_messages`）。
- 完整结果保存在 `DeepResearchResult.agent_results`，REPORT 阶段由 `helpers.format_research_context` 按完成先后顺序（并行 agent 完成即追加）编号拼接（`## Research Task N: <task>`）。总长超过 `max_report_context_chars` 时从最后完成的结果向前保留，装不下的次新结果在剩余预算足够时被截断并追加截断标记（否则直接丢弃），更早的结果被丢弃。

---

## 与 meta_tools/clarification 边界

- **deep_research/** — 多阶段研究产品流程
- **meta_tools/clarification/** — 可复用 HITL 澄清工具（Deep Research 消费方之一）

---

## Callback 机制

Orchestrator 支持 5 个可选回调，由业务层（`streaming.py`）注入：

| Callback | 触发时机 | Server 层接入状态 | 签名 |
|----------|----------|------------------|------|
| `on_clarify` | CLARIFY 阶段需要用户输入 | ✅ `PhaseWaiter` + SSE `phase=clarify` + `/agents/clarify-response` | `(AskQuestionInput) -> ClarificationAnswer \| None` |
| `on_plan_ready` | 研究计划生成后 | ✅ `PhaseWaiter` + SSE `phase=plan_confirm` + `/agents/plan-confirm-response` | `(str) -> str \| None` |
| `on_explore` | PLAN 完成后，RESEARCH 前 | ✅ Wiki FTS5 搜索（零 LLM 成本） | `(str) -> str \| None` |
| `on_cycle_complete` | 每个研究循环结束 | ⏳ Harness hook 就绪，Server 层未接入 | `(int, list[dict]) -> PhaseGuidance \| None` |
| `on_report_ready` | 最终报告生成成功后 | ✅ Wiki Vault 归档 | `(DeepResearchResult) -> None` |

Server 层通过 `PhaseWaiter`（通用阶段暂停/恢复门控）实现 Clarification 和 Plan Confirmation 两个 HITL 闭环。前端通过 `ClarificationInput.tsx` 和 `PlanConfirmationCard.tsx` 分别渲染对应的交互 UI。

`on_explore` 在 PLAN 和 RESEARCH 之间执行，使用 Wiki FTS5 全文搜索（零 LLM 调用成本）检索本地知识库中与研究计划相关的已有内容。检索结果作为 `local_context` 注入 orchestrator 系统提示词，引导子代理跳过已知信息、聚焦新发现。回调失败静默降级，不影响后续研究。

`on_report_ready` 仅在 `result.report` 非空且无 error 时触发（在 `finally` 块中），
用于后处理如 wiki 入库、通知等。回调失败不影响研究结果。

---

## Research agent 的守卫隔离

research agent 与分派它们的 run 在同一个 context 里并行运行，而每个 run 开始时都会就地重置它找到的守卫。`_dispatch_research_agents` 因此把每个 agent 放进 `agent/_internals/_agent_helpers.ephemeral_run_scope(scope_key)`（`scope_key = research-<分派 id>-<序号>`）：

- 每个 agent 拥有自己的 LoopGuard、FrequencyGuard、ToolTurnBudgetGuard、ContextBudgetGuard、terminal-error 注册表与完成门禁回合状态，结束时分派方的守卫原样回来。没有隔离时，三个 agent 抓同一个 URL 会把调用数加在同一个循环检测窗口上，每个 agent 只抓了几次就被判定为循环（见 `tests/agent/deep_research/test_dispatch_real_agents.py`），且任何一个 agent 的启动都会清空其余 agent 与分派方的窗口。
- 与子 agent（`child_run_scope`）不同，research agent 保持分派方的 approval session，也不置 `is_subagent`：它们的工具审批仍按分派方的会话走，不会被当成委派出来的子任务。
- 没有任何东西会恢复一个 research agent，所以它登记在 loop guard 注册表里的条目在 `ephemeral_run_scope` 结束时（无论怎样结束）即被释放。

---

## 扩展指南

1. 新阶段 → 对应 phase mixin（`_orchestrator_phases.py`、`_orchestrator_dispatch.py` 或 `_orchestrator_plan_research.py`）+ prompts
2. 公开 API 仅通过 `deep_research/__init__.py` 导出
3. 更新 [deep_research/_ARCH.md](_ARCH.md)

---

## 参考资料

- [deep_research/_ARCH.md](_ARCH.md)
- [meta_tools/clarification/_ARCH.md](../meta_tools/clarification/_ARCH.md)
