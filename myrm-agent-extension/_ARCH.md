# myrm-agent-extension 模块架构

## 架构概述

Chrome/Edge MV3 浏览器扩展。通过 WebSocket 连接本机 `myrm-agent-server`，代理 `chrome.debugger` 操作实现标签页管理与控制，使 Agent 可读取用户已授权标签页状态。同时提供 **Side Panel Chat UI**，让用户在浏览网页时可直接与 Agent 对话，无需切换窗口。

Server 侧见 `myrm-agent-server/app/api/extension/` 与 `app/services/extension/`；WebUI 管理见 Settings → `extensionBridge` Tab。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `manifest.json` | 核心 | MV3 清单：权限、Service Worker、popup、side_panel；`default_locale` + `_locales/` 中英双语 | — |
| `src/i18n.js` | 辅助 | `msg()` / `applyDocumentI18n()` — Chrome `_locales` SSOT | ✅ |
| `_locales/en/messages.json` | 辅助 | 英文 UI 文案 | — |
| `_locales/zh_CN/messages.json` | 辅助 | 简体中文 UI 文案 | — |
| `src/background.js` | 核心 | Service Worker：WebSocket/CDP/上下文菜单（`chrome.i18n`）；Wiki clip 委托 `src/wiki/*`；`lastClipErrorKind` 供 popup 深链；clip 结果 `chrome.notifications` | ✅ |
| `src/wiki/deep_links.js` | 辅助 | Settings Wiki 深链 builder | ✅ |
| `src/wiki/clip_client.js` | 核心 | Wiki clip REST 客户端；错误文案 `chrome.i18n` | ✅ |
| `src/wiki/` | 子模块 | Extension wiki clip 客户端与深链 — 见 [src/wiki/_ARCH.md](src/wiki/_ARCH.md) | ✅ |
| `src/popup.html` | 辅助 | Popup 结构；静态文案 `data-i18n` + 运行时 `applyDocumentI18n` | — |
| `src/popup.js` | 辅助 | Popup 控制器：连接状态；clip conflict/security/success 深链（`lastClipErrorKind` 结构化，非 regex）；`chrome.i18n` 双语 | ✅ |
| `src/sidepanel/sidepanel.html` | 核心 | Side Panel 入口页面：Chat UI 结构（SVG 图标、语义化 HTML） | — |
| `src/sidepanel/sidepanel.css` | 核心 | Side Panel 样式：暗色主题、消息气泡、工具进度、审批弹窗、流式指示器、输入区 | — |
| `src/sidepanel/sidepanel.js` | 核心 | Side Panel Chat（英文 UI；对话文案由 server/WebUI i18n 覆盖） | ✅ |
| `src/content/selection.js` | 辅助 | Content Script（manifest 注入）：监听 mouseup 捕获用户选中文本，转发至 Side Panel | ✅ |
| `src/content/clip_image_urls.js` | 核心 | srcset/lazy/picture 图片 URL 解析（`MyrmClipImageUrls` SSOT） | ✅ |
| `src/content/clip.js` | 核心 | Content Script（动态注入）：捕获 page/selection HTML + credentialed 图片 fetch | ✅ |
| `src/content/glow.js` | 辅助 | Content Script（动态注入）：Agent 工作时在网页视口边缘显示发光效果 | ✅ |
| `icons/icon{16,32,48,128}.png` | 辅助 | 扩展图标（16/32/48/128） | — |

## 连接契约

| 项 | 说明 |
|----|------|
| WebSocket | `ws://<server>/api/v1/ws/extension?token=<extension_auth_token>` |
| 握手 | 扩展发送 `hello`（version、browser、capabilities=`navigate_url|list_tabs|attach_debugger|detach_debugger`）；Server 校验 `settings.extension_auth_token` 并按 capability 执行动作门禁 |
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
| `/api/v1/extension/clip-agent` | GET/PUT | Wiki 剪藏目标 agent + WebUI origin（与 Settings → Extension Bridge 同步） |
| `/api/v1/wiki/clip` | POST | 浏览器剪藏 multipart 上传（可选 `?agent_id=`；`folder_path=""` 默认月分目录；`queue_compile=false` 零 LLM） |

## Wiki clip 产品默认

Extension `src/content/clip.js` 固定 `folder_path=""`、`queue_compile=false`：

- 空 `folder_path` → server/harness 写入 `raw/clips/{YYYY-MM}/web_{sha12(source_url)}.md`（URL 稳定路径）
- `queue_compile=false` → 剪藏不触发 LLM；用户在 WebUI Settings → Wiki 点击 Compile
- clip ingress：extension 上传图（srcset 最高分辨率 + credentialed fetch）+ server Track B 拉剩余远程 markdown 图片
- 同 `source_url` 再剪 → **conflict**（`RawConflictPolicy.FAIL`）→ popup/通知引导 Duplicate Review；非静默覆盖
- REST API 仍接受自定义 `folder_path` 与 `queue_compile=true`（高级/集成调用）

Settings → Extension Bridge 仅配置 **Wiki clip target agent**（`/extension/clip-agent` SSOT）。

## Extension i18n 范围

| 表面 | 语言 | 机制 |
|------|------|------|
| Popup + clip 错误 + 右键剪藏菜单 + clip 系统通知 | en / zh_CN | `_locales` + `chrome.i18n` |
| Side Panel Chat chrome | en | Agent 回复与 WebUI 设置语言由 server SSE 提供 |
| WebUI Settings → Extension Bridge | 六语 | `myrm-agent-frontend` next-intl |

**Degraded deep links:** When `web_ui_origin` is not yet seeded from WebUI, clip still writes to Wiki; popup shows a success hint (`clipSavedWithoutOrigin`) until origin syncs.

认证通过 `Authorization: Bearer <authToken>`（从 `chrome.storage.local` 读取）。跨域请求由 `host_permissions: ["<all_urls>"]` 授权。

## 模块依赖

- **上游**：`myrm-agent-server` Extension Bridge（`ExtensionBridgeService` + harness `ExtensionBridge` Protocol）+ Chat API（`general_agent/streaming.py`）
- **下游**：无（终端用户浏览器）

## 安装

开发者模式加载 unpacked 扩展目录；在 popup 或 WebUI Settings → Browser Extension 配置 Server URL 与 Token。Side Panel 通过右键菜单 "Ask Myrm Agent"、键盘快捷键 Cmd+Shift+M、或点击扩展图标后在 Side Panel 中打开。
