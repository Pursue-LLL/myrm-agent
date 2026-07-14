# services/approvals — 统一拦截审批流模块

## 架构概述

本模块实现跨端的统一拦截与审批决策业务层（Approval Registry）。
基于 Harness 层抛出的 `ApprovalContract` 中断原语，将审批请求落库至 `approvals` 表（ORM：`ApprovalRecord`），并广播 SSE 事件至 Web 前端，同时支持拦截并转化成 `OutboundMessage` 发送至原生 IM 渠道（如 Slack/Feishu）。
IM/渠道 ActionButton 回调由 `channels/routing/router_commands.py::_handle_action_button_approval` 处理：解析 `approval:{action}:{id}` → 权限校验 → `resolve_approval` 落库 → 编辑原 IM 消息 → `SessionGate.submit(resume_msg)` 恢复 Agent。`resolve_approval` 仅处理 `status == "PENDING"` 的记录，已解决的审批返回 `None`（幂等保护，防止重复点击导致状态翻转）。Web Drawer 对 `subagent_approval` 由前端 `resumeApprovalStream` 先 resume，再由本模块 `resolve_approval` 落库；growth/无 thread_id 项仅落库不 resume。
支持通过 `expires_at` 和 Cron 定时任务进行超时审批 (TTL) 的自动降级与自动清理。

**Outbound Draft Review（Channel HITL）**：`action_type == "outbound_draft"` 的审批项用于 Channel 消息草稿审核。当 Topic 配置 `replyMode: "draft_review"` 时，Agent 的 Channel 回复被拦截为 ApprovalRecord 而非直接发送。审批通过后消息被发送，拒绝则丢弃。超时行为由 `draft_timeout_action` 控制（`auto_send` 或 `auto_reject`）。此类审批无 `thread_id`（不涉及 LangGraph 恢复），resolution 直接触发消息发送/丢弃。

Growth drafts（`skill_draft` / `skill_patch` / `semantic_memory`）统一存储于 `ApprovalRecord`，但 **无 `thread_id` 的后台 growth 项不进 `GET /approvals` 全局 recovery 列表**（走 `/skills/drafts` + Agent 洞察 tab）；**有 `thread_id` 的 inline HITL** 仍走本模块与全局 Drawer。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `registry.py` | 核心 | 拦截审批流注册、多端推送 (SSE + Channels)、`list_pending` 过滤后台 growth draft、`send_outbound_draft_payload()` 共享的草稿发送逻辑 | ✅ |

## `list_pending` 契约

- **包含**：工具 HITL、`thread_id` 非空的 inline `skill_draft` 等需全局 Drawer recovery 的项。
- **排除**：`action_type ∈ growth_constants.GROWTH_ACTION_TYPES` 且 `thread_id` 为空（Agent Draft Inbox / `/skills/drafts`）。
- **SSE**：后台 growth 创建时不广播 `APPROVAL_REQUIRED`（由 `draft_notification` 发 `NEW_SKILL_DRAFT`）。

## 模块依赖

- `app.database.models.approval` -> 访问 `ApprovalRecord` 存储拦截任务。
- `app.services.event.app_event_bus` -> `ServerEventBus` 下发 SSE 实时通信唤醒 Web/Desktop 卡片。
- `app.channels` -> 下发 `OutboundMessage` Native Blocks 推送。
- `myrm_agent_harness.agent.types` -> 使用 `Command` 恢复挂起的 Agent State。
