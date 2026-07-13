# app-shell/

## 架构概述

应用壳层：启动屏、全局认证/PWA 初始化、跨页面对话框。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BrandLogo.tsx` | 辅助 | 品牌 Logo（明暗主题 SVG） | ✅ |
| `ConfigConflictDialog.tsx` | 组件 | 跨设备配置冲突解决 UI（T3）；同设备冲突由 ConfigSyncManager 静默处理 | ✅ |
| `PremiumTooltip.tsx` | 辅助 | 付费功能锁定 Tooltip 包装器 | ✅ |
| `QuarantineDialog.tsx` | 组件 | 隔离/安全扫描 quarantine 文件确认对话框 | ✅ |
| `SystemStatusBanner.tsx` | 组件 | 数据库降级/恢复全局 Banner；健康检查走 `fetchBackendHealth`（后端不可达静默跳过）；文案走 `notifications.*` 五语言 i18n | ✅ |
| `VaultUnlockModal.tsx` | 组件 | E2EE Vault 解锁密码模态框 | ✅ |
| `VisualDesktop.tsx` | 组件 | VNC/noVNC 实时桌面嵌入视图 | ✅ |
| `VisualDesktopToggle.tsx` | 组件 | VNC 实时桌面面板 + 浏览器 HITL takeover UI（Agent 请求人工介入时自动弹出，显示原因并提供「完成」/「无法完成」操作按钮） | ✅ |
| `app-update-prompt.tsx` | 组件 | Tauri 桌面端更新提示浮层（静默下载，ready/error 时展示；dismissed 持久化到 localStorage） | ✅ |
| `whats-new-modal.tsx` | 组件 | 版本更新后 What's New 弹窗（从 GitHub Release API 拉取完整 Release Notes，Markdown 渲染） | ✅ |
| `appshot-initializer.tsx` | 组件 | Appshot 截图能力初始化（Tauri 权限与事件桥） | ✅ |
| `settings-sync-initializer.tsx` | 组件 | ConfigSyncManager 初始化；`initConfig` 优先，providers/commands/retrieval idle 延迟 | ✅ |
| `deferred-mount.tsx` | 辅助 | `requestIdleCallback` 延迟挂载非首屏 subtree | ✅ |
| `deferred-app-initializers.tsx` | 辅助 | FlowPad/PWA/WhatsNew 等 6 个 initializer 的 dynamic + idle 挂载 | ✅ |
| `voice-ptt-initializer.tsx` | 组件 | 全局语音 PTT 快捷键 IPC → DOM CustomEvent 桥接 | ✅ |
| `auth-callback.tsx` | 组件 | OAuth 回调页 loading/错误态与 token 交换 | ✅ |
| `auth-initializer.tsx` | 组件 | 启动时 auth store  hydration 与路由守卫 | ✅ |
| `boot-screen.tsx` | 组件 | 冷启动屏；local 模式下轮询后端健康，失败时展示 health-aware `common.configLoadError` hint | ✅ |
| `local-backend-unavailable-banner.tsx` | 组件 | `LocalBackendUnavailableBanner`：后端未就绪告警；`ConfigReadinessDegradedBanner`：readiness 降级非阻塞告警（`common.readinessDegraded`） | ✅ |
| `capability-icons.tsx` | 辅助 | 模型能力图标行（Vision/ToolCalling/Reasoning/Audio/Video 5 种布尔能力） | ✅ |
| `command-palette.tsx` | 组件 | Slash 命令面板 UI（Cursor 风格弹出面板，分组展示系统行为/技能/用户命令，含 argsHint 参数提示） | ✅ |
| `flow-pad-modal.tsx` | 组件 | Omni-FlowPad 全局 Dialog：截图预览+Quick Actions+语音/文本输入+Inline Mode 流式结果桥接+Paste 回写 | ✅ |
| `FlowPadModalParts.tsx` | 辅助 | FlowPad 截图预览/lightbox 与 Appshot 消息格式化 | ✅ |
| `config-load-error.tsx` | 组件 | Settings 配置加载失败 UI；复用 `lib/local-backend-dev` hint SSOT | ✅ |
| `confirm-dialog.tsx` | 辅助 | 全局确认对话框 imperative API 包装 | ✅ |
| `deep-link-listener.tsx` | 组件 | Tauri/URL deep link 路由分发 | ✅ |
| `global-events-initializer.tsx` | 组件 | 挂载 `useGlobalEvents` toast 订阅 | ✅ |
| `json-editor.tsx` | 辅助 | Monaco JSON 编辑器封装（settings 表单复用） | ✅ |
| `key-value-editor.tsx` | 辅助 | 动态 key-value 对编辑列表 | ✅ |
| `lazy-mermaid.tsx` | 辅助 | Mermaid 动态 import 懒加载包装 | ✅ |
| `lazy-monaco-editor.tsx` | 辅助 | Monaco 动态 import 懒加载包装 | ✅ |
| `login-prompt.tsx` | 组件 | 未登录态全局登录引导条 | ✅ |
| `model-picker-popover.tsx` | 组件 | 模型选择弹出面板：Provider 分组列表 + 搜索过滤 + 3 层 Slot（Primary/Fallback/Safety）+ Context Window Badge + 参考成本 Badge + 能力图标 | ✅ |

## 测试

| 路径 | 职责 |
|------|------|
| `__tests__/SystemStatusBanner.test.tsx` | Banner 展示/隐藏、recovered toast、dismiss、i18n key 绑定 |
| `__tests__/SystemStatusBanner.locales.test.ts` | 五语言 `notifications.database*` keys 完整性 |
| `__tests__/` | 其他 colocated 单测：BootScreen、LocalBackendUnavailableBanner、FlowPad、PWA 等壳层组件 |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
