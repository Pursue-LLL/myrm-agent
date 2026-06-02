
# app/ai_agents/extensions 模块架构

Agent 运行时扩展层。通过 Extension 模式为 Agent 注入横切关注点（安全策略、子代理、任务自适应、记忆等），不修改核心 Agent 逻辑。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `security_policy_extension.py` | 核心 | 安全策略扩展（网络/文件系统/代码执行权限守卫 + PII 隐私策略含自定义规则透传） | ⚠️ 待补 |
| `subagent_extension.py` | 核心 | 子代理路由扩展（动态注册和调度子 Agent） | ⚠️ 待补 |
| `task_adaptive_extension.py` | 核心 | 任务自适应扩展（根据任务类型动态调整 Agent 行为） | ⚠️ 待补 |
| `zero_cost_memory.py` | 辅助 | 零成本记忆扩展（利用压缩驱逐的 EvictedToolCall.original_content 提取记忆） | ✅ |
| `pre_compact_memory.py` | 核心 | 压缩前语义记忆 recall 注入 + operation_ledger 事件 | ✅ |
| `archive_checkpoint_memory.py` | 核心 | 剪枝归档 lite 摘要落盘 EpisodicMemory + operation_ledger + agent_status SSE | ✅ |
