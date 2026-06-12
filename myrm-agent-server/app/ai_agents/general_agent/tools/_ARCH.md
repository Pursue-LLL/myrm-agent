# general_agent/tools 模块架构


---

## 架构概述

通用 Agent 业务层专属工具。提供回答用户、X 搜索能力，以及向 harness `_TOOL_LAYERS` 注册 server 层工具名的启动钩子。UI 渲染（`render_ui_tool`）在 harness `agent/meta_tools/interaction/`，由 `enabled_builtin_tools` 含 `render_ui` 时经 `resolve_builtin_tool_flags` → `enable_render_ui` → `tool_setup.py` 延迟加载。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `_tool_layer_bootstrap.py` | ✅ 核心 | Server 层 tool layer 注册引导：在 `main.py` 启动时把 server 层依赖第三方 SDK 的业务 tool（x_search）写入 harness `_TOOL_LAYERS`，保持"harness 不预登记业务 tool 名"的架构边界。 |
| `answer_user_tool.py` | ✅ 核心 | 回答用户工具（结构化回复生成）。 |
| `x_search_provider.py` | ✅ 核心 | X (Twitter) 搜索工具。 |
