# myrm-agent-extension 模块架构

## 架构概述

Chrome/Edge MV3 浏览器扩展。通过 WebSocket 连接本机 `myrm-agent-server`，代理 `chrome.debugger` CDP 操作，使 Agent 浏览器自动化可使用用户真实登录会话。Server 侧见 `myrm-agent-server/app/api/extension/` 与 `app/services/extension/`；WebUI 管理见 Settings → `extensionBridge` Tab。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `manifest.json` | 核心 | MV3 清单：权限（debugger/tabs/storage/alarms）、Service Worker、popup | — |
| `src/background.js` | 核心 | Service Worker：WebSocket 连接、心跳保活、CDP 请求分发、标签页生命周期、智能 Tab 选择（同 domain 多 tab 优先 active + tabId 直传） | ✅ |
| `src/popup.html` | 辅助 | Popup 页面结构（服务器 URL、Token、域名列表） | — |
| `src/popup.js` | 辅助 | Popup 控制器：读写 `chrome.storage.local`、连接/断开、状态展示 | ✅ |
| `icons/icon{16,32,48,128}.png` | 辅助 | 扩展图标（16/32/48/128） | — |

## 连接契约

| 项 | 说明 |
|----|------|
| WebSocket | `ws://<server>/api/ws/extension?token=<extension_auth_token>` |
| 握手 | 扩展发送 `hello`（version、browser）；Server 校验 `settings.extension_auth_token` |
| 域名授权 | `authorizedDomains` 存于 `chrome.storage.local`；Server REST `/api/v1/extension/domains` 与 WebUI 同步 |
| 保活 | `chrome.alarms` 周期唤醒；断线指数退避重连 |

## 模块依赖

- **上游**：`myrm-agent-server` Extension Bridge（`ExtensionBridgeService` + harness `ExtensionBridge` Protocol）
- **下游**：无（终端用户浏览器）

## 安装

开发者模式加载 unpacked 扩展目录；在 popup 或 WebUI Settings → Browser Extension 配置 Server URL 与 Token。
