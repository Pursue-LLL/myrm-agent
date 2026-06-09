# myrm-agent-extension 模块架构

## 架构概述

Chrome MV3 扩展，作为 **Browser Extension Bridge** 客户端。通过 WebSocket 连接 `myrm-agent-server` 的 `/api/v1/ws/extension`，在授权域名上代理 CDP（`chrome.debugger`）操作，使 Agent 能复用用户真实登录会话。

详细服务端 API 见 [myrm-agent-server/app/api/extension/_ARCH.md](myrm-agent-server/app/api/extension/_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `manifest.json` | MV3 清单（权限、service worker、popup） |
| `src/background.js` | Service worker：WebSocket、CDP 代理、重连与 keepalive |
| `src/popup.html` / `src/popup.js` | 扩展弹窗：服务器 URL、令牌、授权域名配置 |
| `icons/icon{16,32,48,128}.png` | 工具栏与商店图标 |

## 模块依赖

- **上游**：`myrm-agent-server` `app/services/extension/` + `app/api/extension/router.py`
- **运行时**：Chrome / Chromium（开发者模式加载 unpacked，或未来 Chrome Web Store 分发）

## 本地加载

```bash
# Chrome → Extensions → Developer mode → Load unpacked
# Install path: ~/.myrm/myrm-agent/myrm-agent-extension
# Monorepo dev: myrm-agent/myrm-agent-extension
```

在 popup 中粘贴 WebUI Settings 复制的 WebSocket URL；若 `token_required` 为 true，填写与 server `EXTENSION_AUTH_TOKEN` 相同的 token。

## 约束

- 扩展不含业务逻辑；协议变更须与 server `extension` 模块同步
- `host_permissions: <all_urls>` 为 CDP 所需；授权域名白名单由 server + storage 共同约束
- 发布前可替换 `icons/` 为品牌设计资产
