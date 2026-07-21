# api/voice/

## 架构概述

实时语音 WebSocket 与 REST 会话控制。上级文档：[../_ARCH.md](../_ARCH.md)。

**Inline A2UI**：语音会话无聊天气泡渲染面。`gemini_live` 与 `realtime` 工具目录均 **不** 暴露 `render_ui`；`agent_bridge` 使用 `channel_name="voice_bridge"`（IM），GeneralAgent Turn1 亦不挂载 `render_ui_tool`。内联表单/图表面板请使用 Web Chat 或 Tauri 桌面客户端。

**Memory read-plane**：OpenAI Realtime 与 Gemini Live 通过 `voice_memory_context.py` 读取与 Chat 相同的 Settings ACL，经 `tool_catalog.py` 动态裁剪 `memory_search_tool` 的 corpus enum；`realtime-tool-exec` 与 `agent_bridge` 共用同一 flags 组装 `GeneralAgentParams`。已加载 profile 与 settings 的路径须调用 `voice_memory_context_from`，禁止重复 resolver I/O。

**测试**：`tests/api/voice/test_voice_memory_context.py`（SSOT 矩阵）、`tests/api/voice/test_voice_memory_acl_api_integration.py`（HTTP token/tool-exec）、`tests/e2e/test_voice_memory_acl_chrome_e2e.py`（Settings UI → `personalSettings` READ E2E）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `voice_memory_context.py` | 核心 | Voice memory ACL SSOT（settings + profile → flags） | ✅ |
| `tool_catalog.py` | 核心 | 动态 `memory_search_tool` 声明（Realtime + Gemini） | ✅ |
| `agent_bridge.py` | 模块 | Agent execution bridge for voice sessions. | ✅ |
| `gemini_live.py` | 模块 | Gemini Live API integration (token + WebSocket URL + tool declarations). | ✅ |
| `realtime.py` | 模块 | OpenAI Realtime API integration (ephemeral token + tools + tool-exec proxy). | ✅ |
| `ws_session.py` | 模块 | Full-duplex voice session WebSocket endpoint. | ✅ |
