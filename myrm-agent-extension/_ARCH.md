# myrm-agent-extension 模块架构

## 架构概述

Chrome/Edge MV3 浏览器扩展。通过 WebSocket 连接本机 `myrm-agent-server`，代理 `chrome.debugger` 操作实现标签页管理与控制，使 Agent 可读取用户已授权标签页状态。同时提供 **Side Panel Chat UI**，让用户在浏览网页时可直接与 Agent 对话，无需切换窗口。

Server 侧见 `myrm-agent-server/app/api/extension/` 与 `app/services/extension/`；WebUI 管理见 Settings → `extensionBridge` Tab。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `manifest.json` | 核心 | MV3 清单：权限（debugger/tabs/storage/alarms/sidePanel/contextMenus/scripting）、Service Worker、popup、side_panel、content_scripts、keyboard commands | — |
| `src/background.js` | 核心 | Service Worker：WebSocket 连接（四态 badge：ON/…/空/!）、心跳保活、debugger attach/detach 管理、标签页生命周期、智能 Tab 选择（同 domain 多 tab 优先 active + tabId 直传）、断线原因追踪、后台窗口隔离（`ensureBackgroundWindow` 非聚焦窗口管理、持久化/复用/自动清理）、**右键菜单注册与处理**、**Glow 消息转发**、**键盘快捷键处理** | ✅ |
| `src/popup.html` | 辅助 | Popup 页面结构（服务器 URL、Token、域名列表） | — |
| `src/popup.js` | 辅助 | Popup 控制器：读写 `chrome.storage.local`、连接/断开、状态展示 | ✅ |
| `src/sidepanel/sidepanel.html` | 核心 | Side Panel 入口页面：Chat UI 结构（SVG 图标、语义化 HTML） | — |
| `src/sidepanel/sidepanel.css` | 核心 | Side Panel 样式：暗色主题、消息气泡、工具进度、审批弹窗、流式指示器、输入区 | — |
| `src/sidepanel/sidepanel.js` | 核心 | Side Panel 控制器：通过 HTTP+SSE 与 server chat API 通信、SSE 流消费（对齐 `AgentEventType`）、消息渲染、工具进度可视化、取消流、上下文自动附加（当前标签页信息）、选中文本引用、工具审批 UI、Glow 控制、新建聊天 | ✅ |
| `src/content/selection.js` | 辅助 | Content Script（manifest 注入）：监听 mouseup 捕获用户选中文本，转发至 Side Panel | ✅ |
| `src/content/glow.js` | 辅助 | Content Script（动态注入）：Agent 工作时在网页视口边缘显示发光效果 | ✅ |
| `icons/icon{16,32,48,128}.png` | 辅助 | 扩展图标（16/32/48/128） | — |

## 连接契约

| 项 | 说明 |
|----|------|
| WebSocket | `ws://<server>/api/ws/extension?token=<extension_auth_token>` |
| 握手 | 扩展发送 `hello`（version、browser）；Server 校验 `settings.extension_auth_token` |
| 域名授权 | `authorizedDomains` 存于 `chrome.storage.local`；Server REST `/api/v1/extension/domains` 与 WebUI 同步 |
| 保活 | `chrome.alarms` 周期唤醒；断线指数退避重连 |

## Side Panel API 契约

Side Panel 通过 HTTP+SSE 直接与 server 通信（复用现有 chat API），**不** 经过 background.js 的 WebSocket：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/agents/agent-stream` | POST | 发送消息并接收 SSE 流式响应 |
| `/api/v1/chats/{chatId}/messages` | GET | 获取历史消息 |
| `/api/v1/agents/agent/{messageId}/cancel` | POST | 取消当前执行 |
| `/api/v1/agents/chat/{chatId}/attach` | GET | 重新附加到活跃流 |
| `/api/v1/approvals/{approvalId}/resolve` | POST | 响应工具审批（`{decision: "approve"|"deny"}`） |
| `/api/v1/health` | GET | 连接状态检测 |

认证通过 `Authorization: Bearer <authToken>`（从 `chrome.storage.local` 读取）。跨域请求由 `host_permissions: ["<all_urls>"]` 授权。

## 模块依赖

- **上游**：`myrm-agent-server` Extension Bridge（`ExtensionBridgeService` + harness `ExtensionBridge` Protocol）+ Chat API（`general_agent/streaming.py`）
- **下游**：无（终端用户浏览器）

## 安装

开发者模式加载 unpacked 扩展目录；在 popup 或 WebUI Settings → Browser Extension 配置 Server URL 与 Token。Side Panel 通过右键菜单 "Ask Myrm Agent"、键盘快捷键 Cmd+Shift+M、或点击扩展图标后在 Side Panel 中打开。
