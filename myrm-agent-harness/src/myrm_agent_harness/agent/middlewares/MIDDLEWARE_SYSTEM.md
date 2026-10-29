# Middleware System Design

> Agent 框架内建中间件栈。在 LangChain `AgentMiddleware` 链上实现安全、上下文、工具拦截、审批与并发控制；与用户可配 `hooks/` 互补（hooks=业务/用户生命周期，middlewares=框架内建逻辑）。

---

## 设计目标

1. **单一工具拦截点**：`tool_interceptor_middleware` 编排所有 guard，避免分散 patch
2. **可组合**：各 middleware 独立文件，通过 `_factory/builder.py` 或 Server 注入组装
3. **安全 fail-closed**：`safety_dispatcher` 未知工具默认串行；security 层验证 tool result
4. **Cache 安全**：context/progress/replan 类 middleware 通过 `request.override` 注入 HumanMessage，不污染 system 前缀

---

## 中间件栈（概念顺序）

```
请求进入 Agent 图
    │
    ▼
┌─────────────────────────────────────────┐
│ model_call_cancel                       │  ← Stop 打断在途模型请求（最外层）
│ context_pipeline_middleware (context_pipeline/) │  ← 上下文压缩/摘要链
│ memory_context_middleware (memory_context/)  │  ← 用户记忆注入（编排）
│   └─ memory_context_format.py         │  ← stable/learned 格式化纯函数
│ progress_middleware / goal_focus_middleware │  ← todo 焦点 / active goal 提醒
│ moa_advisor_middleware (opt-in)             │  ← agent 环轻量顾问 fan-out
│ replan_middleware                         │  ← 动态重规划
│ GuardrailMiddleware (guardrails/)       │  ← 技能边界等
│ security_*_middleware                   │  ← 安全边界/护栏
│ subagent_limit / concurrency_limiter    │  ← 委派 fan-out 限制
│ tool_history_hygiene.py                 │  ← ToolMessage dedup + within/cross-turn tool_call_id re-id
│ dangling_tool_call_middleware           │  ← 悬空 tool_call 修复 + invalid 重放隔离
│ skill_attenuation_middleware (tooling/)  │  ← skill attenuation + runtime intent gating
│ filesystem_search_middleware            │  ← glob/grep 注入
│ tool_interceptor_middleware (tooling/)  │  ← ★ 工具执行主拦截点
│   └─ tool_executor (timeout/retry)      │
│   └─ approval/                          │  ← HITL 审批
│ completion_guard                        │  ← 完成门控 + 外部证据门控 + 混合消息 guard
│ completion_directive_middleware         │  ← 被拦草稿的复核指令，仅随下一次模型请求送达
│ rate_limit                              │  ← Provider 429 主动节流
│ concurrency/ (safety_dispatcher + router)│  ← 工具并发安全路由
│ debug_logger_middleware (dev)           │
└─────────────────────────────────────────┘
    │
    ▼
  ToolNode / LLM
```

实际顺序以 `_factory/builder.py` 与 Server `factory.py` 装配为准；上图为逻辑分层。

模型响应后的守卫（`after_model`）由 LangChain 按装配列表**倒序**执行：响应先过 CompletionGuard，再过 ClarificationGuard，然后是 `ApprovalEvaluationMiddleware`（评估），最后才到 `ToolApprovalMiddleware`（向用户发问）。评估单独成一个图节点，因为 LangGraph 在用户回答审批卡片后会把发问的那个节点从第一行重跑：评估有副作用（审核模型调用、拒绝计数、限流），放在发问节点里就会跑两遍，审核模型第二次改判时甚至会让用户刚拒绝的调用被放行。评估结果存在私有的检查点状态键 `approval_evaluation`（按 AI 消息 id 对应），发问节点只读、结束时清空。被 ClarificationGuard 拦下的调用由它用 error ToolMessage 回答，审批跳过已有回答的调用，所以不会再弹给用户审批。被拒绝的调用（策略拒绝、用户拒绝、审批超时、定时任务无人可批）同样留在 AI 消息里、由 error ToolMessage 回答，模型读到的是对自己调用的拒绝结果与原因（用户填写的理由原样带上；超时写明无人回答）；调用与结果成对留在会话里，悬空调用修复没有孤儿可丢。界面上这一步只显示拒绝的原因，给模型的备注在流式层被截掉。CompletionGuard 拦下草稿时返回 `jump_to="model"`，复核指令由 `completion_guard/directive_middleware.py` 只在下一次模型请求末尾追加（仅当它所跟随的那条消息仍是请求的最后一条：有文字的被拦草稿，或不带文字的结束工具草稿被 `RemoveMessage` 移出会话后它前面的那条消息），不写入会话与检查点；同时记录 `completion_guard` 事件，并发出 `answer_recheck` 重启状态让前端丢弃正在流出的旧草稿。

---

## 子系统

| 子目录/文件 | 职责 |
|-------------|------|
| `tooling/` | 工具执行子系统：`tool_interceptor_middleware.py`（唯一编排入口；GraphInterrupt on stuck）、`tool_executor.py`（超时、重试、指数退避）、`tool_history_hygiene.py`（within-AIMessage re-id → ToolMessage keep-last dedup → cross-turn re-id；导出 `sanitize_tool_history()`）、`dangling_tool_call_middleware.py`（修复 strict provider 400；invalid_tool_calls 出站隔离——升级为合法声明并回填结构化诊断，畸形原文不回喂 provider）、`skill_attenuation_middleware.py`（skill attenuation + runtime intent-aware narrowing via `tool_choice.allowed_tools`）、`_tool_guards.py`/`_circuit_breaker.py`/`_tool_helpers.py`（拦截辅助；熔断检查独立成 `_circuit_breaker.py`）、`_mutation_verifier.py`（文件变更 per-turn 验证 → SSE）、`_skill_failure_tracking.py`（技能失败事件 + 单技能执行计数）、`_tool_execution_lifecycle.py`（执行生命周期 hook）、`_runtime_tool_governance.py`（回合级工具面收敛 UI intent gate + readonly intent gate）、`_skill_tool_choice.py`（attenuation tool_choice 构建） |
| `_session_context.py` | Middleware 链共享 ContextVar |
| `_run_workspace.py` | 运行工作区解析：`run_workspace` 从 LangGraph `Runtime` 上下文取 `workspace_path`，todo 焦点注入与 CompletionGuard 共用。哪些运行保有 todo 清单由构建方决定（`_agent_build.build_middlewares` 按本 Agent 的注册表是否持有 `todo_write`）：与父共用工作区、但没有 `todo_write` 的子 Agent，既看不到父的 todo，也不受「未完成 todo」约束。清单按 chat 分开存放（`.myrm/progress/<chat>/todos.json`），两处读到的都是运行中 chat 自己的那份；未完成 todo 只在本 run 用过 `file_write_tool` / `file_edit_tool` 之后才阻断收尾，否则只是一条不拦截的 WARNING（仅在守卫因验证失败拦下收尾时，随复核清单送达模型） |
| `approval/` | HITL 审批：`evaluation/`（评估节点，工具调用只评估一次）、`middleware.py`（发问节点：batch interrupt 与决策落地）、`refusal/`（拒绝如何到达模型）、scheduler |
| `guardrails/` | Provider 链 + `GuardrailMiddleware` |
| `completion/` | 完成验证门子系统：`completion_guard/guard.py`（代码任务完成验证门 + 外部证据缺失门控（web/browser/MCP：PTC bash `skills.mcp_*` 或 Direct FC `mcp__{server}__{tool}`；自有项目/材料与纯文本改写请求豁免，触发判定见 `completion_guard/freshness.py`，词表覆盖英文、简体与繁体中文）+ 未落盘交付物门控与自动暂存保全（只对能落盘的运行生效：挂载 `file_write_tool` 且策略未禁止 `file_write`；不能落盘的运行不被要求写文件、也不被强制暂存；虚假“已保存”声称对所有运行照常拦截）；各项要求只对能满足它的运行提出（`completion_guard/capabilities.py` 的 `CompletionCapabilities`，由 `_agent_build.build_middlewares` 按注册表与策略逐次判定）：没有任何可产出证据工具的运行只被提醒一次“如实说明无法核实”，之后放行+ **执行断言接地门**（三类承重断言——验证结论/外发动作/代码修改——与本轮执行轨迹对齐，命中即要求取证或诚实改写）；Mixed Message Guard（保留变异调用 `is_mutating_tool` registry fail-closed + 交互/UI 承载工具，仅剥离确定无副作用无交互的只读工具；证据缺失或断言无法接地时保留只读 tool_calls 防未核实内容直达用户））、`completion_guard/capabilities.py`（运行能力探针：能否保有 todo 清单/落盘/取证）、`completion_guard/hold_back.py`（被拦草稿的去向与指令挂靠位置：有文字的草稿保留、不带文字的结束工具草稿移出会话）、`completion_guard/mixed_message.py`（Mixed Message Guard 的剥离判定）、`completion_guard/checklist/`（子包：`assessment.py` 验证清单与拦截原因，`record_rules.py` 判定它的规则）与 `completion_guard/verification.py`（验证清单、判定它的规则——最后一次代码写入之后有没有通过的验证、各验证类别的最新结果、最后一次写入之后仍然成立的失败（写入之前的探索性失败与已被同一调用重试成功的失败不拦）——与验证命令分类）、`completion_guard/external_evidence.py`（外部证据判定）、`completion_guard/directive.py`（`BlockReasons` 与按拦截原因渲染的模型侧复核指令、无原因时的验证清单回退）、`completion_guard/directive_middleware.py`（复核指令随下一次模型请求送达，不入会话）、`completion_guard/events.py`（`completion_guard` 决策事件 + `answer_recheck` 重启状态）、`completion_guard/freshness.py`（外部证据门的触发规则：词表 + 自有工作/文本改写豁免 + 「今天/现在」类短问句分支（求建议与超过 200 字的粘贴材料不算），带人工标注回归集）、`completion_guard/rerun.py`（修改代码后、且没有别的问题时，在沙箱里独立复跑最近一次验证命令；复跑通过只能解除“代码改在最后一次通过的验证之后”这一件事）、`completion_guard/state.py`（按轮次消息 id 分桶的拦截预算与强制收尾闩锁 + 整轮调用账本（按调用顺序、按记录对象身份合并；所有拦截判定读它，而不是 LoopGuard 只留最近 20 条的窗口）+ 每轮证据档/暂存披露登记，`attach_disclosure_to_event` 供 `message_end` 事件消费）、`execution_claim/verifier.py`（断言接地判定：真实测试运行器约束、零用例否决、外发动作证据集、引用/条件/否定/讲解排除与需求侧意图收口）、`completion_guard/safety.py`（effectful 工具判定 SSOT，供 Mixed Message Guard 与 server Cron 后验消费）、`deliverable/auto_staging.py`（未落盘交付物沙箱草案自动安全暂存与 LRU 保护）、`deliverable/confidence_tier.py`（交付置信档解析 + 披露策略：证据档总是展示，PLAN 档仅在回答含完成式断言时展示）、`deliverable/write_verifier.py`（写盘声称检测与实质未落盘交付物代码块启发式嗅探） |
| `context_pipeline/` | `context_pipeline_middleware.py`（桥接 `context_management/pipeline/`）、`context_pipeline_helpers.py`（压缩意图/cache feedback/schema fingerprint） |
| `memory_context/` | `memory_context_middleware.py`（记忆上下文注入编排，首轮 LLM 前 idempotent 注入）、`memory_context_format.py`（注入格式化纯函数：stable SystemMessage / learned UNTRUSTED HumanMessage） |
| `concurrency/` | `concurrency_limiter.py`（按 agent_type Semaphore）、`concurrency_router.py`（智能并发路由：host-serial MCP lane + canonical path + `build_tool_execution_stages`）、`safety_dispatcher.py`（safe→concurrent / unsafe→serial） |
| `security/` | `security_boundary_middleware.py`（SECURITY_BOUNDARY_SYSTEM_RULES 每次运行注入一次，state 以追加方式合并，落在最新用户消息之后）、`security_guardrail_middleware.py`（八层防御：circuit-breaker cognition / intent router / prompt guard / PII / leak / canary / history redact）、`user_input_guard.py`（意图 / 注入 / PII 三层筛查用户亲写消息，文本或图文块均可；runtime 追加的 `is_system_synthetic` 消息不筛。最新一条完整筛查：审计、日志、安全告诫前缀与 PII 改写只在该输入的首次模型调用写入，之后每轮工具调用字节不变；更早的用户消息随历史在每轮再次送入模型，故静默执行同一策略（PII 改写；注入 / 危险意图为 `fail_closed` 时拦截），不写审计、日志与告诫，且无任何策略生效时整段跳过）、`pii_actions.py`（按级别执行 warn / redact / pseudonymize / block，入站、出站、工具结果与模型调用出口共用）、`outbound_privacy_guard.py`（模型调用出口闸门：注册到 `toolkits.llms` 的 `outbound_guard`，对每一次 ChatLiteLLM 调用的非 system 消息按隐私策略处理（直连 litellm / 厂商 SDK 的调用与 embedding、语音、图像、视频等非对话调用不经过它）——运行策略优先，其次进程级策略；与主循环同一动作语义，主循环已处理过的文本字节不变，不伤 prompt cache；主循环自带 `privacy_enforced_by_loop` 标记避免重复处理；出错即中止调用，不放行）、`text_blocks.py`（文本与图文块内容的统一文本变换） |
| `subagent_limit_middleware.py` | 单轮 delegate 上限 |
| `plan_confirm_middleware.py` | 计划阶段人机协同确认与重大 Re-plan 拦截门禁 |
| `filesystem_search_middleware.py` | 工作区搜索工具注入 |
| `progress_middleware.py` | 活跃 todo 紧凑焦点注入与幂等清洗（末位 HumanMessage）；仅持有 `todo_write` 的 Agent 注入 |
| `advisor_risk_trigger_router.py` | 自适应事件门禁路由：多维感知 Replan 连续失败与 LoopGuard 异常模式，兼具致命错误旁路与冷却免疫/会话配额门禁 |
| `moa_advisor_middleware.py` | Agent 环 MoA 顾问叠加（支持 `risk_triggered` 模式自适应路由接入；`moa_overlay_active` 透传 `trigger_reason` + 渐进 SSE `moa_ref_done` + 6s 硬超时静默降级 + 瞬态 Cache-Safe 尾注入与 KV-Cache 保全 + `privacy_filter` display/full 分流） |
| `replan_middleware.py` | 动态重规划循环（导出 `get_replan_error_summary` 与 `get_max_consecutive_replan_errors` 只读遥测） |

| `model_call_cancel.py` | 最外层模型调用包装：Stop 时在一个轮询周期内中断在途模型请求（含其内侧中间件的限流等待与重试），抛 `OperationCancelledError`，执行器按 Stop 收尾 |
| `rate_limit.py` | Provider 级主动 sleep |
| `debug_logger_middleware.py` | 完整消息 debug 日志 |

---

## 与 hooks 边界

| | `middlewares/` | `hooks/` |
|--|------------------|----------|
| 配置方 | 框架/Server 装配 | 用户 profile YAML |
| 时机 | LangGraph middleware 链 | 生命周期事件（pre/post tool 等） |
| 典型用途 | 安全、压缩、审批 | 自定义脚本、业务回调 |

---

## 与 security 边界

- **检测/验证实现**在 `agent/security/`（如 `tool_result_validator`）
- **middleware 层**只做编排与注入；`middlewares/__init__.py` 再导出部分 security 符号供便捷 import

---

## 扩展指南

1. 新 guard → 独立模块，由 `tool_interceptor_middleware` 注册顺序
2. 新 middleware → 独立文件 + `_ARCH.md` 行 + 本文档栈说明
3. 禁止在 middleware 内写业务 REST/OAuth 逻辑 → Server `AgentExtension`

---

## 参考资料

- [middlewares/_ARCH.md](_ARCH.md) — 完整文件清单
- [context_management/CONTEXT_MANAGEMENT_SYSTEM.md](../context_management/CONTEXT_MANAGEMENT_SYSTEM.md)
- [security/SECURITY_SYSTEM.md](../security/SECURITY_SYSTEM.md)
