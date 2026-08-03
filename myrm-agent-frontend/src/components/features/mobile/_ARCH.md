# mobile/

## 架构概述

移动端远程控制面：Hub 活跃会话列表 + 远程新建任务 → scoped pair token → 单会话 StatusBoard（SSE attach、HITL 审批、steer、autoStart 自动启动新任务）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `MobileSessionHub.tsx` | `/mobile` Hub：拉取 active sessions、远程新建任务（agent/project 选择 + 消息输入 → spawn API → autoStart 跳转），点击 mint scoped token 跳转 |
| `../../app/mobile/page.tsx` | Hub 路由页 |
| `../../app/mobile/status/[chatId]/page.tsx` | StatusBoard 路由页 |
| `../../app/mobile/takeover/[chatId]/page.tsx` | takeover 专用路由页（签名链接入口） |
| `../chat-window/MobileStatusBoard.tsx` | 单会话控制 UI（SSE attach、HITL、steer、语音、**Stop** → `cancelActiveChatAgent` + toast 反馈、**Live Preview** — Browser/Desktop 截图实时预览 + Lightbox 全屏放大、**Artifact Deliverables** — 交付物列表预览/下载、**autoStart** — sessionStorage 消费初始消息自动 sendMessage、run 中 **查看完整对话** → 主 Chat 划词旁路；localhost dev **`window.__MYRM_E2E_MOBILE_CC__.setLoading`** Chrome E2E 桥） |
| `MobileTakeoverBoard.tsx` | takeover 专用轻量面板（读取 `mid/reason/page/pair` 签名参数，轮询 `/api/v1/remote-access/mobile/takeover/{chatId}/snapshot` 实时预览，Done/Skip resume + 会话跳转） |

## 依赖

- `@/services/remoteAccess` — pairing token / sessions / spawn-options / spawn API
- `@/lib/mobileRemote` — pair header、token 存储与 refresh
- `@/lib/e2ee/useE2EEStatus` — E2EE 握手状态 Hook
- `@/components/features/e2ee/E2EESecurityPanel` — E2EE 安全状态 badge
- `@/services/chat::cancelActiveChatAgent` — Mobile Stop（`POST /agents/chats/{chatId}/cancel`）
- `@/services/i18nToastService::showI18nToast` — Stop 成功/失败 toast（desktop Multi-Pane + mobile 远程，`stopTaskSuccess` / `stopTaskFailed`）
- `@/lib/api::fetchWithTimeout` — pair header SSOT

## 用户入口

Settings → System → AccessCard：开启 tunnel → Hub QR / 分享链接。
