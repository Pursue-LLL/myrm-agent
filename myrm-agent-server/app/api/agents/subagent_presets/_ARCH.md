# api/agents/subagent_presets

## 架构概述

Agent 编辑器的内置子代理目录 HTTP 子包。只读取 server 业务层 `app.ai_agents.subagent_presets` 的 YAML 元数据，产出 `GET /agents/subagent-presets`；不返回 system prompt、不写数据库、不进入 harness。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `__init__.py` | 门面 | 只导出 `router`，供 `app/api/router.py` 挂载 |
| `router.py` | 路由 | `GET /agents/subagent-presets`：返回用户可选专家的 id/display_name/description/required_builtin_tools；内部 cron 专用预设不暴露 |
