# core/channel_bridge/agent_executor/

## 架构概述

渠道入站消息 → GeneralAgent 执行桥。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Business-layer AgentExecutor for channel inbound messages. | ✅ |
| `executor.py` | 核心 | Executes Agent tasks for inbound channel messages with session-aware auto-reset notification, dual-layer budget interception (global + per-channel), channel cost recording and sender attribution. Registers `on_artifacts_ready` callback to bridge harness file artifacts into IM outbound media delivery. | ✅ |
| `helpers.py` | 模块 | Business-layer assembly for IM/channel turns headed to the SkillAgent runtime. StreamAccumulator tracks cost_usd for channel budget attribution. | ✅ |
| `session.py` | 模块 | Build a structured session key (base, without epoch). Exports `build_channel_budget_key(msg)` for channel budget guard key construction (single source of truth for peer resolution). | ✅ |
