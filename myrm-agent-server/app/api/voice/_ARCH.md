# api/voice/

## 架构概述

实时语音 WebSocket 与 REST 会话控制。上级文档：[../_ARCH.md](../_ARCH.md)。

**Inline A2UI**：语音会话无聊天气泡渲染面。`gemini_live` 与 `realtime` 工具目录均 **不** 暴露 `render_ui`；`agent_bridge` 使用 `channel_name="voice_bridge"`（IM），GeneralAgent Turn1 亦不挂载 `render_ui_tool`。内联表单/图表面板请使用 Web Chat 或 Tauri 桌面客户端。

**Memory read-plane**：OpenAI Realtime 与 Gemini Live 通过 `voice_memory_context.py` 读取与 Chat 相同的 Settings ACL，经 `tool_catalog.py` 动态裁剪 `memory_search_tool` 的 corpus enum；`realtime-tool-exec` 与 `agent_bridge` 共用同一 flags 组装 `GeneralAgentParams`。已加载 profile 与 settings 的路径须调用 `voice_memory_context_from`，禁止重复 resolver I/O。

**Agent Security net_fetch**：`agent_bridge.py` 与 `realtime.py`（tool-exec 代理）均通过 `resolve_enable_web_fetch(profile.security_overrides)` 设置 `enable_web_fetch`，与 Web/Channel/Cron 入口一致。

**Background work**：`run_background_task` / `cancel_background_task` / `get_background_tasks_status` / `steer_background_task` 四个后台任务工具在 OpenAI Realtime 和 Gemini Live 中均注册为 always-available。工具执行统一经 `realtime-tool-exec` 端点短路处理，经 `ChannelBackgroundTaskHandler` 操作 Kanban；`run_background_task` 要求 `chat_id` 非空，否则返回 error；完成通知见 `webui_voice_work_notifier.py`。

**测试**：`tests/api/voice/test_voice_memory_context.py`（SSOT 矩阵）、`tests/api/voice/test_voice_memory_acl_api_integration.py`（HTTP token/tool-exec）、`tests/e2e/test_voice_memory_acl_chrome_e2e.py`（Settings UI → `personalSettings` READ E2E）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `voice_memory_context.py` | 核心 | Voice memory ACL SSOT（settings + profile → flags） | ✅ |
| `tool_catalog.py` | 核心 | 动态 `memory_search_tool` 声明（Realtime + Gemini） | ✅ |
| `agent_bridge.py` | 模块 | Voice STT→Agent bridge；merge profile `system_prompt` + **`profile_output_suffixes`**；`enable_web_fetch` 由 profile `net_fetch` 门控 | ✅ |
| `gemini_live.py` | 模块 | Gemini Live token/WS；session `instructions` 含 profile `system_prompt` + **`profile_output_suffixes`** | ✅ |
| `realtime.py` | 模块 | OpenAI Realtime token/tools；session `instructions` 含 profile `system_prompt` + **`profile_output_suffixes`**；tool-exec 路由入口 `is_safe_session_id` 白名单拒绝非法 `chat_id`（400，防路径穿越，统一覆盖 background lifecycle 委托与 Agent 代理） | ✅ |
| `realtime_background.py` | 模块 | Background task lifecycle handlers（run/cancel/status/steer）短路 Kanban；由 `realtime.py` tool-exec 路由调用 | ✅ |
| `ws_session.py` | 模块 | Full-duplex voice session WebSocket endpoint；type:config 用 `is_safe_session_id` 校验 `chat_id`，非法拒绝连接 | ✅ |
