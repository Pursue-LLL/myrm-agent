# app-shell/

## 架构概述

应用壳层：启动屏、全局认证/PWA 初始化、跨页面对话框。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BrandLogo.tsx` | 组件/模块 | — | — |
| `ConfigConflictDialog.tsx` | 组件/模块 | 跨设备配置冲突解决 UI（T3）；同设备冲突由 ConfigSyncManager 静默处理 | — |
| `PremiumTooltip.tsx` | 组件/模块 | — | — |
| `QuarantineDialog.tsx` | 组件/模块 | — | — |
| `SystemStatusBanner.tsx` | 组件/模块 | 数据库降级/恢复全局 Banner；健康检查走 `fetchBackendHealth`（后端不可达静默跳过） | `fetchBackendHealth`, `apiRequest`（reset，`silent`） |
| `VaultUnlockModal.tsx` | 组件/模块 | — | — |
| `VisualDesktop.tsx` | 组件/模块 | — | — |
| `VisualDesktopToggle.tsx` | 组件/模块 | VNC 实时桌面面板 + 浏览器 HITL takeover UI（Agent 请求人工介入时自动弹出，显示原因并提供「完成」/「无法完成」操作按钮） | `useBrowserTakeoverStore`, `useChatStore`, `useFeatureEntitlements` |
| `app-update-prompt.tsx` | 组件/模块 | Tauri 桌面端更新提示浮层（静默下载，ready/error 时展示；dismissed 持久化到 localStorage） | `useAppUpdate` |
| `whats-new-modal.tsx` | 组件/模块 | 版本更新后 What's New 弹窗（从 GitHub Release API 拉取完整 Release Notes，Markdown 渲染） | `useWhatsNew` |
| `appshot-initializer.tsx` | 组件/模块 | — | — |
| `settings-sync-initializer.tsx` | 组件/模块 | 应用顶层 ConfigSyncManager 初始化、启动归一化、冲突对话框挂载 | `ConfigSyncManager`, `ConfigConflictDialog` |
| `voice-ptt-initializer.tsx` | 组件/模块 | — | — |
| `auth-callback.tsx` | 组件/模块 | — | — |
| `auth-initializer.tsx` | 组件/模块 | — | — |
| `boot-screen.tsx` | 组件/模块 | 冷启动屏；local 模式下轮询后端健康，失败时展示 health-aware `common.configLoadError` hint | `waitForBackendReady`, `resolveLocalBackendSetupHint`, `isLocalMode` |
| `local-backend-unavailable-banner.tsx` | 组件/模块 | AppLayout 内全局提示；同 session 跳过 Boot 且后端未就绪时展示 health-aware `common.configLoadError` hint，可 dismiss，后端恢复后自动隐藏 | `checkBackendReadyOnce`, `resolveLocalBackendSetupHint`, `isLocalMode` |
| `capability-icons.tsx` | 组件/模块 | 模型能力图标行（Vision/ToolCalling/Reasoning/Audio/Video 5 种布尔能力） | `ModelCapabilities` |
| `command-palette.tsx` | 组件/模块 | Slash 命令面板 UI（Cursor 风格弹出面板，分组展示系统行为/技能/用户命令，含 argsHint 参数提示） | `useCommandStore` |
| `flow-pad-modal.tsx` | 组件/模块 | Omni-FlowPad 全局 Dialog：截图预览+Quick Actions+语音/文本输入+Inline Mode 流式结果桥接+Paste 回写 | `useFlowPadStore`, `useChatStore`, `isTauriRuntime` |
| `FlowPadModalParts.tsx` | 组件/模块 | FlowPad 截图预览/lightbox 与 Appshot 消息格式化 | — |
| `config-load-error.tsx` | 组件/模块 | Settings 配置加载失败 UI；复用 `lib/local-backend-dev` hint SSOT | `formatLocalBackendSetupHint`, `fetchBackendHealth` |
| `confirm-dialog.tsx` | 组件/模块 | — | — |
| `deep-link-listener.tsx` | 组件/模块 | — | — |
| `global-events-initializer.tsx` | 组件/模块 | — | — |
| `json-editor.tsx` | 组件/模块 | — | — |
| `key-value-editor.tsx` | 组件/模块 | — | — |
| `lazy-mermaid.tsx` | 组件/模块 | — | — |
| `lazy-monaco-editor.tsx` | 组件/模块 | — | — |
| `login-prompt.tsx` | 组件/模块 | — | — |
| `model-picker-popover.tsx` | 组件/模块 | 模型选择弹出面板：Provider 分组列表 + 搜索过滤 + 3 层 Slot（Primary/Fallback/Safety）+ Context Window Badge + 参考成本 Badge + 能力图标 | `useProviderStore`, `fetchModelCapabilitiesBatch`, `CapabilityIcons`, `formatTokens`, `formatPrice` |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
