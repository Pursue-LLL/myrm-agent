# general_agent/tools 模块架构


---

## 架构概述

通用 Agent 业务层专属工具。`x_search_provider.py` 提供 xAI API 客户端；eager tool 工厂在 `app/services/integrations/tools/x_live_search.py`，由 `tool_setup._setup_x_live_search_tool` 在 skill 绑定后进 Turn1 `tools`（不依赖 `enable_web_search`）。UI 渲染（`render_ui_tool`）在 harness `agent/meta_tools/interaction/`，由 `enabled_builtin_tools` 含 `render_ui` 时 Turn1 eager 加载。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `_tool_layer_bootstrap.py` | ✅ 核心 | Server 层 `@tool` → harness `_TOOL_LAYERS` 登记（`x_search`、媒体、channel_notify） |
| `answer_user_tool.py` | ✅ 核心 | 回答用户工具（结构化回复生成）。 |
| `x_search_provider.py` | ✅ 核心 | xAI Live Search API 客户端与 `XSearchProvider`；供 `integrations/tools/x_live_search.py` 调用。`tool_setup._setup_x_live_search_tool` 仅 skill gate，不依赖 `enable_web_search` |
