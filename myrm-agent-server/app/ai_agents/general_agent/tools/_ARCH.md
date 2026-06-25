# general_agent/tools 模块架构


---

## 架构概述

通用 Agent 业务层专属工具。`x_search_provider.py` 提供 xAI API 客户端；`x_live_search` deferred tool 工厂在 `app/services/integrations/tools/`。UI 渲染（`render_ui_tool`）在 harness `agent/meta_tools/interaction/`，由 `enabled_builtin_tools` 含 `render_ui` 时经 `tool_setup.py` 延迟加载。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `_tool_layer_bootstrap.py` | ✅ 核心 | Server 层 tool layer 注册：`x_search_tool` → EXTENDED（skill-gated deferred 加载，见 `tool_setup.py` + `x-live-search` prebuilt skill） |
| `answer_user_tool.py` | ✅ 核心 | 回答用户工具（结构化回复生成）。 |
| `x_search_provider.py` | ✅ 核心 | xAI Live Search API 客户端与 `XSearchProvider`；供 `integrations/tools/x_live_search.py` 调用 |
