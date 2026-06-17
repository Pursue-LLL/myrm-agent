# mobile/

## 架构概述

移动端远程控制面：Hub 活跃会话列表 → scoped pair token → 单会话 StatusBoard（SSE attach、HITL 审批、steer）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `MobileSessionHub.tsx` | `/mobile` Hub：拉取 active sessions，点击 mint scoped token 跳转 |
| `../../app/mobile/page.tsx` | Hub 路由页 |
| `../../app/mobile/status/[chatId]/page.tsx` | StatusBoard 路由页 |
| `../chat-window/MobileStatusBoard.tsx` | 单会话控制 UI（SSE attach、HITL、steer、语音、**Stop** → `cancelActiveChatAgent`） |

## 依赖

- `@/services/remoteAccess` — pairing token / sessions API
- `@/lib/mobileRemote` — pair header、token 存储与 refresh
- `@/services/chat::cancelActiveChatAgent` — Mobile Stop（`POST /agents/chats/{chatId}/cancel`）
- `@/lib/api::fetchWithTimeout` — pair header SSOT

## 用户入口

Settings → System → AccessCard：开启 tunnel → Hub QR / 分享链接。
