# general_agent/tools 模块架构


---

## 架构概述

通用 Agent 业务层 LLM 工具。

记忆读平面已迁入 harness `memory_search_tool(corpus=...)`；wiki 与会话 provider 在 `tool_setup._create_memory_tools` 绑定。工具描述 locale 由 `app/core/agent/tool_description_locale.py` 解析后经 `description_locale` 传入 harness。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `_tool_layer_bootstrap.py` | 核心 | Server 业务专有 LLM 工具通过 `ToolRegistry.register_external_layer_specs` 注册到 Harness `_TOOL_LAYERS` EXTERNAL 层；`channel_notify_tool` 同时注册 `register_leaf_blocked_tools`（子 Agent 不可继承） | ✅ |
