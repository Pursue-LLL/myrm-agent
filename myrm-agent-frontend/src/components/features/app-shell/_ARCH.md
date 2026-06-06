# app-shell/

## 架构概述

应用壳层：启动屏、全局认证/PWA 初始化、跨页面对话框。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BrandLogo.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ConfigConflictDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `PremiumTooltip.tsx` | 组件/模块 | 见源码 | 见源码 |
| `QuarantineDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SystemStatusBanner.tsx` | 组件/模块 | 见源码 | 见源码 |
| `VaultUnlockModal.tsx` | 组件/模块 | 见源码 | 见源码 |
| `VisualDesktop.tsx` | 组件/模块 | 见源码 | 见源码 |
| `VisualDesktopToggle.tsx` | 组件/模块 | 见源码 | 见源码 |
| `app-update-prompt.tsx` | 组件/模块 | 见源码 | 见源码 |
| `appshot-initializer.tsx` | 组件/模块 | 见源码 | 见源码 |
| `auth-callback.tsx` | 组件/模块 | 见源码 | 见源码 |
| `auth-initializer.tsx` | 组件/模块 | 见源码 | 见源码 |
| `boot-screen.tsx` | 组件/模块 | 见源码 | 见源码 |
| `capability-icons.tsx` | 组件/模块 | 见源码 | 见源码 |
| `command-palette.tsx` | 组件/模块 | 见源码 | 见源码 |
| `flow-pad-modal.tsx` | 组件/模块 | Omni-FlowPad 全局 Dialog：截图预览+指令输入+当前 Agent 显示 | 见源码 |
| `config-load-error.tsx` | 组件/模块 | 见源码 | 见源码 |
| `confirm-dialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `deep-link-listener.tsx` | 组件/模块 | 见源码 | 见源码 |
| `global-events-initializer.tsx` | 组件/模块 | 见源码 | 见源码 |
| `json-editor.tsx` | 组件/模块 | 见源码 | 见源码 |
| `key-value-editor.tsx` | 组件/模块 | 见源码 | 见源码 |
| `lazy-mermaid.tsx` | 组件/模块 | 见源码 | 见源码 |
| `lazy-monaco-editor.tsx` | 组件/模块 | 见源码 | 见源码 |
| `login-prompt.tsx` | 组件/模块 | 见源码 | 见源码 |
| `model-picker-popover.tsx` | 组件/模块 | 见源码 | 见源码 |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
