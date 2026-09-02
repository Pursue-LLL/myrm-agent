# general_agent/tools 模块架构


---

## 架构概述

通用 Agent 业务层 LLM 工具。UI 渲染（`render_ui_tool`）在 harness `agent/meta_tools/interaction/`，由 `enabled_builtin_tools` 含 `render_ui` 时 Turn1 eager 加载。

记忆读平面已迁入 harness `memory_search_tool(corpus=...)`；wiki 与会话 provider 在 `tool_setup._create_memory_tools` 绑定。工具描述 locale 由 `app/core/agent/tool_description_locale.py` 解析后经 `description_locale` 传入 harness。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `_tool_layer_bootstrap.py` | ✅ 核心 | Server vendor `@tool` → harness `_TOOL_LAYERS` as EXTERNAL；`channel_notify_tool` 同时注册 `register_leaf_blocked_tools`（子 Agent 不可继承） |
