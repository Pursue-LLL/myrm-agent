# settings/sections/integration 模块架构

## 架构概述

Integration 设置 Tab 下的独立 Section：浏览器扩展桥接、凭证、外部 Agent、渠道容器等。

## 文件清单

| 文件 | 职责 |
|------|------|
| `ExtensionBridgeSection.tsx` | 扩展连接状态、Setup Copy URL/路径、`token_required` 提示、授权域名与标签页 |
| `CommunicationSection.tsx` | 渠道 Tab 容器 |
| `channels/` | 各渠道配置（见 [channels/_ARCH.md](channels/_ARCH.md)） |
| `integrations/` | 第三方集成卡片 |

## ExtensionBridgeSection 要点

- WS URL：`getWsUrl('/ws/extension')`，兼容 local / sandbox / Tauri 部署
- Copy 模式：复用 `writeToClipboard`（与 `CpInboundUrlBanner` 一致）
- 扩展目录：`~/.myrm/myrm-agent/myrm-agent-extension`（install）与 `myrm-agent/myrm-agent-extension`（monorepo dev）
- 轮询：`GET /extension/status` 每 5s

## 依赖

- `@/services/extension` — REST 客户端
- `@/lib/api::getWsUrl` — WebSocket 基址
- [api/extension/_ARCH.md](../../../../../../myrm-agent-server/app/api/extension/_ARCH.md)
