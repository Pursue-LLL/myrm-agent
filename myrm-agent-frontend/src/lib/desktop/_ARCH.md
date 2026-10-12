# desktop/

## 架构概述

本地/Tauri 桌面自动化权限引导的纯函数 SSOT：从 probe `settings_deeplinks` 选取 URL，并通过 Tauri shell 或 Web fallback 打开系统设置。

## 文件清单

| 文件                                   | 地位 | 职责                                                                                                                                          | I/O/P |
| -------------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `permissionDeepLink.ts`                | 核心 | `pickSettingsDeepLink*`；`openPermissionDeepLink`；`openPermissionDeepLinkWithGuideFallback(url, platform?)`；`getPermissionGuideFallbackUrl` | ✅    |
| `desktopPermissionsStatus.ts`          | 核心 | `DesktopPermissionsStatus` + `desktopPermissionsPath` — FE contract for `GET /webui/desktop/permissions`                                      | ✅    |
| `desktopLockedUseDoctor.ts`            | 核心 | DesktopLockedUse doctor 解析：badge/detail/tone + `locked_use_enabled` 协调态                                      | ✅    |
| `desktopSettingsAnchors.ts`            | 核心 | 系统设置内离席/帷幕卡片 scroll 锚点 SSOT                                                                           | ✅    |
| `__tests__/permissionDeepLink.test.ts` | 测试 | pick meta / system URL / Tauri open / platform guide fallback（含 darwin≠win32 回归）                                                         | —     |
| `__tests__/desktopLockedUseDoctor.test.ts` | 测试 | DesktopLockedUse doctor 解析与 i18n detail key 映射                                                                                           | —     |

## 依赖

- `@tauri-apps/plugin-shell` — Tauri 桌面打开 `x-apple.systempreferences:` / `ms-settings:`
- 消费者：`DoctorDashboard`、`CuPermissionInline`、`DesktopPermissionsCard`、`DesktopLiveView`（权限 DTO 经 `desktopPermissionsStatus.ts`）
