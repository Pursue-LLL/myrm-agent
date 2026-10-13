# services/approvals — 统一拦截审批流模块

## 架构概述

本模块实现跨端的统一拦截与审批决策业务层（Approval Registry）。
基于 Harness 审批中间件抛出的 `interrupt()` 中断，将审批请求落库至 `approvals` 表（ORM：`ApprovalRecord`），并广播 SSE 事件至 Web 前端，同时支持拦截并转化成 `OutboundMessage` 发送至原生 IM 渠道（如 Slack/Feishu）。
IM/渠道 ActionButton 回调由 `channels/routing/commands/router_commands_approval.py::_handle_action_button_approval` 处理：解析 `approval:{action}:{id}` → 权限校验 → `resolve_approval` 落库 → 编辑原 IM 消息 → `SessionGate.submit(resume_msg)` 恢复 Agent。`resolve_approval` 仅处理 `status == "PENDING"` 的记录，已解决的审批返回 `None`（幂等保护，防止重复点击导致状态翻转；IM 点击落在已处理的审批上时，原卡片被改写为“已处理”提示，不再显示可点击按钮）。Web Drawer 对 `subagent_approval` 由前端 `resumeApprovalStream` 先 resume，再由本模块 `resolve_approval` 落库；growth/无 thread_id 项仅落库不 resume。
支持通过 `expires_at` 和 Cron 定时任务进行超时审批 (TTL) 的自动降级与自动清理。

**Outbound Draft Review（Channel HITL）**：`action_type == "outbound_draft"` 的审批项用于 Channel 消息草稿审核。当 Topic 配置 `replyMode: "draft_review"` 时，Agent 的 Channel 回复被整条拦截为 ApprovalRecord 而非直接发送：`payload.outbound` 是回复的完整快照（附件、按钮、线程等，不含正文），`payload.draft_content` 是可编辑正文且为正文的唯一来源；审批无法创建时回复一并不发送（fail-closed，审核承诺“未经批准不外发”）。审批通过后按快照原样发出（附件随行），拒绝或超时丢弃时释放快照中的临时附件。超时行为由 `draft_timeout_action` 控制（`auto_send` 或 `auto_reject`）。此类审批无 `thread_id`（不涉及 LangGraph 恢复）。所有定案入口（WebUI、IM 按钮、批量、TTL 清理）统一收口于 `ApprovalRegistry`：状态提交后调用 `outbound_draft.finalize_outbound_draft`——通过则发送（发不出去时以错误 toast / IM 通知 / 通知中心告知 owner，因为“批准”等于向对方承诺了回复），拒绝或超时则释放临时附件；无论哪种结果，都会关闭路由器扣留回复时留在发送方会话里的“待审核”占位消息（`payload.placeholder_id`）。调用方（WebUI router、IM 按钮 handler）不再自行发送或丢弃，只负责各自的响应与卡片更新。

Growth drafts（`skill_draft` / `skill_patch` / `semantic_memory`）统一存储于 `ApprovalRecord`，但 **无 `thread_id` 的后台 growth 项不进 `GET /approvals` 全局 recovery 列表**（走 `/skills/drafts` + Agent 洞察 tab）；**有 `thread_id` 的 inline HITL** 仍走本模块与全局 Drawer。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `registry.py` | 核心 | 拦截审批流注册、多端推送 (SSE + Channels)、`list_pending` 过滤后台 growth draft、`list_pending_growth`（背景 growth 去重/上限 SSOT）、`find_pending_outbound_drafts`（按审批 ID 前缀查找待审核的被扣留回复，只返回 outbound_draft、最多 2 条，供 `/draft` 命令）、`resolve_approval` 与 `cleanup_expired_approvals` 在 outbound_draft 状态提交后（会话释放之后）调用 `finalize_outbound_draft`（定案的唯一收口；TTL 清理对多条草稿并发收尾）；create/resolve 后 `_sync_copilot_pending` 刷新 RunDigest 待审批计数 | ✅ |
| `outbound_draft.py` | 核心 | 被扣留回复（`outbound_draft`）定案后的唯一收尾：`finalize_outbound_draft()`（发送或释放 + 关闭发送方占位消息 + 发送失败告知 owner；永不抛出，因为决定已落库）、`send_outbound_draft_payload()` / `discard_outbound_draft_payload()`（由整条回复快照重建与释放临时附件）、`draft_code()` / `DRAFT_CODE_MIN_CHARS`（被扣留回复在聊天里的短码：审核请求打印审批 ID 前 8 位，`/draft` 接受 6 位及以上） | ✅ |

## `list_pending` / `list_pending_growth` 契约

- **`list_pending` 包含**：工具 HITL、`thread_id` 非空的 inline `skill_draft` 等需全局 Drawer recovery 的项。
- **`list_pending` 排除**：`action_type ∈ growth/constants.py::GROWTH_ACTION_TYPES` 且 `thread_id` 为空（Agent Draft Inbox / `/skills/drafts`）。
- **`list_pending_growth`**：仅返回 PENDING 后台 growth drafts（与 `list_pending` 互补），供 `draft_notification.persist_skill_draft_record` 做去重抑制与 pending 上限检查；避免 `list_pending` 的过滤导致重复提案无限堆积。
- **SSE**：后台 growth 创建时（`PENDING` 或非 `PENDING`）一律不广播 `APPROVAL_REQUIRED` / `SKILL_GROWTH_UPDATED`（由 `draft_notification` 统一发 `NEW_SKILL_DRAFT` / `SKILL_GROWTH_UPDATED`，避免双发）。

## 模块依赖

- `app.database.models.approval` -> 访问 `ApprovalRecord` 存储拦截任务。
- `app.services.event.app_event_bus` -> `ServerEventBus` 下发 SSE 实时通信唤醒 Web/Desktop 卡片。
- `app.channels` -> 下发 `OutboundMessage` Native Blocks 推送。
- `myrm_agent_harness.agent.types` -> 使用 `Command` 恢复挂起的 Agent State。
