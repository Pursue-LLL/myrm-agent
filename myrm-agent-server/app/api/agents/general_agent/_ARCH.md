# api/agents/general_agent/

## 架构概述

GeneralAgent 流式对话、重连与离线 durable 任务 HTTP 层。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | General Agent package. | ✅ |
| `active_sessions.py` | 模块 | attach SSE；pair auth 时校验 `require_mobile_pair_chat_access`；`/active-sessions` 返回在执行的会话、停在工具审批卡上的 chat（`awaitingApprovalChatIds`，取自 collector 的 `has_pending_tool_approval()`：回合停在审批卡时网关会话已释放，卡片没有落库，重载的页面只能凭这份名单决定要不要 attach 把卡片取回）与空闲槽位 | ✅ |
| `phase_response.py` | 模块 | 阶段响应端点：`/clarify-response`（澄清）+ `/plan-confirm-response`（计划确认 HITL，支持 confirm/edit/skip）+ `/human-gate-response`（Dynamic Workflow 中途人机门控） | ✅ |
| `media_config.py` | 模块 | 媒体设置页凭证端点：`/test-media-config`（图像/视频/TTS 凭证与连通性探测）+ `/media-provider-status`（视频 Provider 密钥与健康状态）；配置读取失败降级为空配置，不返回 500 | ✅ |
| `streaming.py` | 模块 | agent-stream / steer / redirect（指令文本先过风险闸门，命中返回 `success:false`，不送达回合）/ **chat cancel（interrupt + registry）** / message cancel（desktop）— 两个 Stop 端点成功后都对该会话调用 `record_user_stop`（按消息 id 的端点先经网关反查会话），此后到期的后台完成只落通知行、不会自行唤醒，直到用户下一条消息；pair auth 时校验 scoped chat 绑定 | ✅ |
| `prewarm.py` | 模块 | `POST/DELETE /chats/{chat_id}/prewarm` — turn1 冷启动 proactive warm | ✅ |
