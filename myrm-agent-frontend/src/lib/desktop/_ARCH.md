# desktop/

## 架构概述

本地/Tauri 桌面自动化权限引导的纯函数 SSOT：从 probe `settings_deeplinks` 选取 URL，并通过 Tauri shell 或 Web fallback 打开系统设置。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `permissionDeepLink.ts` | 核心 | `pickSettingsDeepLink*`；`openPermissionDeepLink`（deeplink fallback）；`openPermissionDeepLinkWithGuideFallback`（指南 fallback）；`isSystemSettingsDeepLink` | ✅ |
| `__tests__/permissionDeepLink.test.ts` | 测试 | pick meta / system URL / Tauri open / guide fallback | — |

## 依赖

- `@tauri-apps/plugin-shell` — Tauri 桌面打开 `x-apple.systempreferences:` / `ms-settings:`
- 消费者：`DoctorDashboard`、`CuPermissionInline`、`DesktopPermissionsCard`、`DesktopLiveView`
