# core/channel_bridge/agent_executor/

## 架构概述

渠道入站消息 → GeneralAgent 执行桥。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Business-layer AgentExecutor for channel inbound messages. | ✅ |
| `executor.py` | 模块 | Executes Agent tasks for inbound channel messages. | ✅ |
| `helpers.py` | 模块 | Business-layer assembly for IM/channel turns headed to the SkillAgent runtime | ✅ |
| `session.py` | 模块 | Build a structured session key (base, without epoch). | ✅ |
