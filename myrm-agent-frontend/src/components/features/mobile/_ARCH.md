# mobile/

## 架构概述

移动端远程控制面：Hub 双区会话列表（进行中 + 最近完成）+ 远程新建任务 → scoped pair token → 单会话 StatusBoard（SSE attach、HITL 审批、steer、autoStart 自动启动新任务）。

## 文件清单

| 文件                                          | 职责                                                                                                                                                                                                                                                                                                                                                                                                       |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MobileSessionHub.tsx`                        | `/mobile` Hub：5s 轮询 sessions（进行中区：agentName + elapsed 徽章；最近完成区：title + 相对时间，`Intl.RelativeTimeFormat` 本地化）+ 并行额度徽章（used/max，额度满时 spawn 置灰 + `slotsFull` 提示）；远程新建任务（agent/project 选择 + 消息输入 → spawn API → autoStart 跳转），点击（进行中或已完成卡片）mint scoped token 跳转；进行中卡片 Stop 一步终止（复用 `cancelActiveChatAgent`，stopping 态防抖 + 成功/失败 toast + 列表即时刷新）；新建任务输入框以 `isImeComposing` 守卫 Enter，避免输入法候选上屏时误创建远端会话 |
| `../../../app/mobile/page.tsx`                | Hub 路由页                                                                                                                                                                                                                                                                                                                                                                                                 |
| `../../../app/mobile/status/[chatId]/page.tsx`   | StatusBoard 路由页                                                                                                                                                                                                                                                                                                                                                                                         |
| `../../../app/mobile/takeover/[chatId]/page.tsx` | takeover 专用路由页（签名链接入口）                                                                                                                                                                                                                                                                                                                                                                        |
| `../chat-window/mobile/MobileStatusBoard.tsx` | 单会话控制 UI（SSE attach、HITL、steer、语音、**Stop** → `cancelActiveChatAgent` + toast 反馈、**Live Preview** — Browser/Desktop 截图实时预览 + Lightbox 全屏放大、**Artifact Deliverables** — 交付物列表预览/下载、**autoStart** — sessionStorage 消费初始消息自动 sendMessage、run 中 **查看完整对话** → 主 Chat 划词旁路；localhost dev **`window.__MYRM_E2E_MOBILE_CC__.setLoading`** Chrome E2E 桥） |
| `MobileTakeoverBoard.tsx`                     | takeover 专用轻量面板（读取 `mid/reason/page/pair` 签名参数，轮询 `/api/v1/remote-access/mobile/takeover/{chatId}/snapshot` 实时预览，Done/Skip resume + 会话跳转）                                                                                                                                                                                                                                        |
| `MobileQuickCaptureDrawer.tsx`                | 移动端单手极速倾倒抽屉：支持受控与全局自定义事件（`myrm:open-quick-capture`）双模态唤起，集成 Web Crypto AES-GCM-256 E2EE 护盾徽章、离线 IndexedDB 本地暂存箱持久化、离线/在线自适应感知、语音实时转写上屏、标签点选、一键手动/自动同步队列与“派发任务”直接回填 |
| `MobileQuickCaptureFab.tsx`                   | 单手易触达常驻悬浮按钮（FAB）：固定于移动端 Hub 页面右下角（`bottom-6 right-5`），胶囊药丸造型与 Lucide Sparkles 图标，作为极速倾倒抽屉常驻入口 |
| `StagedVaultQueueView.tsx`                    | 独立展示型子组件：负责渲染离线加密暂存箱队列列表、同步状态徽标（staged/synced 等）、空态占位及每条暂存笔记的“派发任务”（`onConvertToTask`）轻按钮                                                                                                                                                                                    |
| `useVoiceRecognition.ts`                      | Web Speech API 独立 Hook：管理语音听写录音启停、连续识别、语言配置、实时文本分块上屏与浏览器兼容性兜底                                                                                                                                                                        |
| `useMobileViewportAdapter.ts`                 | 移动端动态视口与键盘避让 Hook：基于 Visual Viewport API 监听 resize/scroll，动态计算并注入 `--mobile-viewport-height` 与 `--mobile-keyboard-height` CSS 变量，提供 `isKeyboardOpen` 与 `isStandalone` 模式检测 |
| `MobileShellStatusBar.tsx`                    | 移动端沉浸式原生壳状态感知栏：吸顶安全区对齐（`pt-[env(safe-area-inset-top)]`），具备在线就绪、正在连接、断连离线三态实时感知指示，提供轻量重试按钮与 Thin-Client 连接安全信息浮层 |
| `MobilePwaInstallGuide.tsx`                   | PWA 独立壳安装指引：智能检测 Standalone 模式，在普通移动端浏览器访问时根据 iOS Safari / Android Chrome 提供一键添加到主屏幕指引，支持 7 天免打扰记忆 |
| `MobileHostControlRoster.tsx`                 | 移动端控制台横向看板：展示 Agent 活跃/空闲状态矩阵点选卡片，以及 Cron 自动化任务调度概要（下次触发倒计时）折叠面板 |
| `MobileTaskSpawnForm.tsx`                     | 抽离式轻量任务创建表单：从 MobileSessionHub 剥离以控制行数严格受控于 400 行红线内，提供 IME 组合守卫、Agent 与可选 Project 下拉选择以及额度满状态提示 |
| `__tests__/MobileShellStatusBar.test.tsx`     | 状态条单测：覆盖在线常态就绪、薄客户端详情切换、正在连接加载态、离线错误条及重试回调触发 |
| `__tests__/MobilePwaInstallGuide.test.tsx`    | 安装指引单测：覆盖独立 PWA 模式自动隐藏、iOS Safari 添加到主屏幕步骤弹窗、Android Chrome 安装引导及 7 天免打扰缓存 |
| `__tests__/MobileHostControlRoster.test.tsx`  | 控制看板单测：覆盖智能体卡片渲染、运行中/就绪状态指示、卡片点选回调以及 Cron 调度计划折叠面板展开/收起 |
| `__tests__/MobileTaskSpawnForm.test.tsx`      | 任务表单单测：覆盖展开/折叠切换、表单字段渲染、回车键触发提交、Shift+Enter 换行以及额度满按钮禁用 |
| `__tests__/useMobileViewportAdapter.test.ts`  | 视口适配器单测：覆盖默认高度计算、CSS 变量注入、Standalone 模式感知以及动态软键盘弹出时的视口偏移重算 |
| `__tests__/MobileSessionHub.test.tsx`         | Hub 回归：集成状态条、控制台看板、安装引导与抽屉，覆盖新建任务输入法守卫、双区渲染、额度满阻断、Stop 终止及 FAB 唤起 |
| `__tests__/MobileQuickCaptureDrawer.test.tsx` | 抽屉单测：覆盖受控渲染、全局事件唤起、标签选择切换、空内容校验、E2EE 离线存储提交、暂存队列切换展示与手动同步触发 |
| `__tests__/StagedVaultQueueView.test.tsx`     | 队列组件单测：覆盖空态提示、标题回退、状态徽标渲染与“派发任务”回调点击触发 |
| `__tests__/useVoiceRecognition.test.ts`       | 语音 Hook 单测：覆盖 Web Speech 存在与不存在兜底、启停切换、分块派发与状态重置 |

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
