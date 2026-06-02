# services/approvals — 统一拦截审批流模块

## 架构概述

本模块实现跨端的统一拦截与审批决策业务层（Approval Registry）。
基于 Harness 层抛出的 `ApprovalContract` 中断原语，将审批请求落库至 `approvals` 表（ORM：`ApprovalRecord`），并广播 SSE 事件至 Web 前端，同时支持拦截并转化成 `OutboundMessage` 发送至原生 IM 渠道（如 Slack/Feishu）。
前端或 IM 调用相关 API 后，通过本模块记录决策并向底层 LangGraph/Harness 下发 `Command(resume=...)`。
支持通过 `expires_at` 和 Cron 定时任务进行超时审批 (TTL) 的自动降级与自动清理。

本模块彻底取代了之前分散在各处的零碎审批拦截流（如硬编码的 `MemoryTaintedError` 拦截和 `SkillDraft` 模型）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `registry.py` | 核心 | 拦截审批流注册、多端推送 (SSE + Channels) 与批量/超时唤醒中枢 | ✅ |

## 模块依赖

- `app.database.models.approval` -> 访问 `ApprovalRecord` 存储拦截任务。
- `app.api.events.event_bus` -> 下发 SSE 实时通信唤醒 Web/Desktop 卡片。
- `app.channels` -> 下发 `OutboundMessage` Native Blocks 推送。
- `myrm_agent_harness.agent.types` -> 使用 `Command` 恢复挂起的 Agent State。
