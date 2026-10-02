# mobile/

## 架构概述

移动端远程控制面：Hub 双区会话列表（进行中 + 最近完成）+ 远程新建任务 → scoped pair token → 单会话 StatusBoard（SSE attach、HITL 审批、steer、autoStart 自动启动新任务）。

## 文件清单

| 文件                                          | 职责                                                                                                                                                                                                                                                                                                                                                                                                       |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MobileSessionHub.tsx`                        | `/mobile` Hub：5s 轮询 sessions（进行中区：agentName + elapsed 徽章；最近完成区：title + 相对时间，`Intl.RelativeTimeFormat` 本地化）+ 并行额度徽章（used/max，额度满时 spawn 置灰 + `slotsFull` 提示）；远程新建任务（agent/project 选择 + 消息输入 → spawn API → autoStart 跳转），点击（进行中或已完成卡片）mint scoped token 跳转；进行中卡片 Stop 一步终止（复用 `cancelActiveChatAgent`，stopping 态防抖 + 成功/失败 toast + 列表即时刷新）；新建任务输入框以 `isImeComposing` 守卫 Enter，避免输入法候选上屏时误创建远端会话 |
| `../../app/mobile/page.tsx`                   | Hub 路由页                                                                                                                                                                                                                                                                                                                                                                                                 |
| `../../app/mobile/status/[chatId]/page.tsx`   | StatusBoard 路由页                                                                                                                                                                                                                                                                                                                                                                                         |
| `../../app/mobile/takeover/[chatId]/page.tsx` | takeover 专用路由页（签名链接入口）                                                                                                                                                                                                                                                                                                                                                                        |
| `../chat-window/mobile/MobileStatusBoard.tsx` | 单会话控制 UI（SSE attach、HITL、steer、语音、**Stop** → `cancelActiveChatAgent` + toast 反馈、**Live Preview** — Browser/Desktop 截图实时预览 + Lightbox 全屏放大、**Artifact Deliverables** — 交付物列表预览/下载、**autoStart** — sessionStorage 消费初始消息自动 sendMessage、run 中 **查看完整对话** → 主 Chat 划词旁路；localhost dev **`window.__MYRM_E2E_MOBILE_CC__.setLoading`** Chrome E2E 桥） |
| `MobileTakeoverBoard.tsx`                     | takeover 专用轻量面板（读取 `mid/reason/page/pair` 签名参数，轮询 `/api/v1/remote-access/mobile/takeover/{chatId}/snapshot` 实时预览，Done/Skip resume + 会话跳转）                                                                                                                                                                                                                                        |
| `__tests__/MobileSessionHub.test.tsx`         | Hub 回归：新建任务输入的输入法守卫（候选上屏与 keyCode 229 不得创建远端会话、Shift+Enter 换行）；双区渲染（agentName/title/额度徽章）；额度满时 spawn 阻断 + `slotsFull` 提示；进行中卡片 Stop（调 `cancelActiveChatAgent` + toast + 列表刷新，失败 toast warning）                                                                                                                                                                                                                              |

## 依赖

- `@/services/remoteAccess` — pairing token / sessions / spawn-options / spawn API
- `@/lib/utils/imeUtils` — 输入法组合守卫（新建任务 Enter 提交保护）
- `@/lib/utils/relativeTime` — 最近完成卡片相对时间（`formatRelativeTime`，六语言本地化）
- `@/components/agent/builtin-agent-i18n::getBuiltinAgentName` — 内置 Agent 显示名本地化（双区卡片）
- `@/lib/mobileRemote` — pair header、token 存储与 refresh
- `@/lib/e2ee/useE2EEStatus` — E2EE 握手状态 Hook
- `@/components/features/e2ee/E2EESecurityPanel` — E2EE 安全状态 badge
- `@/services/chat::cancelActiveChatAgent` — Stop（`POST /agents/chats/{chatId}/cancel`）：Hub 进行中卡片 + Mobile StatusBoard 两处消费
- `@/services/i18nToastService::showI18nToast` — Stop 成功/失败 toast（desktop Multi-Pane + Hub 卡片 + mobile 远程，`stopTaskSuccess` / `stopTaskFailed`）
- `@/lib/api::fetchWithTimeout` — pair header SSOT

## 用户入口

Settings → System → AccessCard：开启 tunnel → Hub QR / 分享链接。
