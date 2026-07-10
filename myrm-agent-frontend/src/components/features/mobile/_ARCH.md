# mobile/

## 架构概述

移动端远程控制面：Hub 活跃会话列表 → scoped pair token → 单会话 StatusBoard（SSE attach、HITL 审批、steer）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `MobileSessionHub.tsx` | `/mobile` Hub：拉取 active sessions，点击 mint scoped token 跳转 |
| `../../app/mobile/page.tsx` | Hub 路由页 |
| `../../app/mobile/status/[chatId]/page.tsx` | StatusBoard 路由页 |
| `../chat-window/MobileStatusBoard.tsx` | 单会话控制 UI（SSE attach、HITL、steer、语音、**Stop** → `cancelActiveChatAgent` + toast 反馈、**Live Preview** — Browser/Desktop 截图实时预览 + Lightbox 全屏放大） |

## 依赖

- `@/services/remoteAccess` — pairing token / sessions API
- `@/lib/mobileRemote` — pair header、token 存储与 refresh
- `@/lib/e2ee/useE2EEStatus` — E2EE 握手状态 Hook
- `@/components/features/e2ee/E2EESecurityPanel` — E2EE 安全状态 badge
- `@/services/chat::cancelActiveChatAgent` — Mobile Stop（`POST /agents/chats/{chatId}/cancel`）
- `@/services/i18nToastService::showI18nToast` — Stop 成功/失败 toast（desktop Multi-Pane + mobile 远程，`stopTaskSuccess` / `stopTaskFailed`）
- `@/lib/api::fetchWithTimeout` — pair header SSOT

## 用户入口

Settings → System → AccessCard：开启 tunnel → Hub QR / 分享链接。
