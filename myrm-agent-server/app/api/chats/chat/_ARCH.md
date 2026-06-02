
# app/api/chats/chat 模块架构

单个 Chat 的操作子路由。按功能域拆分为独立路由模块，统一挂载到 `/chats/{chat_id}/` 前缀下。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `core.py` | 核心 | 聊天 CRUD；`GET /{chat_id}` 在 `workspace_dir` 为空时 JIT 绑定 harness 沙箱路径（与 agent converter 一致）并持久化，供前端活动记忆预览 | ✅ |
| `catchup.py` | 核心 | 会话追赶简报查询与状态更新 | ⚠️ 待补 |
| `messages.py` | 核心 | 消息管理（查询、分页、搜索、导出）。`GET /{chat_id}/export` 返回消息、`usageSummary`（Chat 表用量统计）和 `toolSummary`（AgentTurn/AgentEvent 聚合） | ✅ |
| `turn.py` | 核心 | 对话轮次管理（删除轮次、截断历史） | ⚠️ 待补 |
| `compaction.py` | 辅助 | 历史压缩（上下文窗口管理） | ⚠️ 待补 |
| `fork.py` | 辅助 | 对话分支（从某轮次分叉新对话） | ⚠️ 待补 |
| `handoff.py` | 辅助 | 跨平台会话交接（Web→Channel 迁移） | ✅ |
| `title.py` | 辅助 | 标题管理（自动生成、重命名） | ⚠️ 待补 |
