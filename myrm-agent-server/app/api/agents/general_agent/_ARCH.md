
# app/api/agents/general_agent 模块架构

General Agent HTTP API 子路由。处理自主决策 Agent 的流式对话、澄清、建议等端点；`streaming.py` 会把 Harness LLM 错误标准化为带 `metadata.error_type` 的 SSE 事件，供前端错误弹窗识别。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `streaming.py` | 核心 | SSE 流式对话端点（typed archive restore action 预校验、Agent 执行、Fast Lane 极速通道拦截、事件流推送、结构化错误元数据、取消、运行时 Steer 引导） | ✅ |
| `sse_helpers.py` | 核心 | SSE 事件辅助层（错误格式化、审批超时调度、上下文压缩检测） | ✅ |
| `active_sessions.py` | 辅助 | 活跃会话管理端点、无缝重连(/attach)接口 | ⚠️ 待补 |
| `clarify.py` | 辅助 | 交互式对话澄清端点，支持接收前端结构化澄清回答（纯文本、选项数组或分题结构）并唤醒挂起的 deep_research 协程 | ✅ |
| `media_config.py` | 辅助 | 媒体配置（图片/视频生成 API Key 解析） | ⚠️ 待补 |
| `suggestions.py` | 辅助 | 搜索建议和推荐问题端点 | ⚠️ 待补 |
