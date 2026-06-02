
# app/core/channel_bridge/agent_executor 模块架构

渠道消息的 Agent 执行引擎。将 IM 渠道的入站消息路由到对应 Agent 执行，管理渠道会话上下文和执行生命周期。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `executor.py` | 核心 | 渠道 Agent 执行器：执行前 `should_block_execution()` 门禁（block 策略下回复 Harness `daily_budget_blocked`）；解析 `ResolvedAgentProfile`，装配 `GeneralAgentParams`（含与 Web 一致的 `auto_restore_domains`、`memory_decay_profile`），Per-agent session_policy 覆盖全局 SessionPolicy，驱动流式执行，支持 Swarm Fission 动态并发裂变与 Yield-Resume 语义；捕获 `tool_image_output` 事件将 computer_use 截屏附加到 `OutboundMessage.media` | ✅ |
| `helpers.py` | 辅助 | Channel 入账 query 装配（ReplyContext 引用注入 + 群组上下文 sanitize + 投递元数据横幅 + 多模态图片 query 构建），`_format_reply_context()` 将结构化 ReplyContext 格式化为 LLM 可理解的消歧前缀（含 sender_name/media hint/500 char 截断/sanitize 防注入），从 `metadata["image_data_list"]` 构建 OpenAI Vision 兼容的多模态 content list；内存 identity 解析 | ✅ I/O/P 见文件头 |
| `session.py` | 辅助 | 渠道会话管理（SessionKey 解析、会话状态） | ⚠️ 待补 |
