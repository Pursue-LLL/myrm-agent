# lib/desktop-bridge/ 模块架构

## 架构概述

Desktop Bridge 标准化原生契约层：提供统一权威的 `IDesktopBridge` 抽象契约与双引擎实现（Tauri 原生 IPC 通信与 Web / Cloud 托管沙箱安全优雅降级）。抹平不同运行环境下的窗口几何度量、系统托盘、本地文件定位、系统级通知与电源休眠锁差异。

## 文件清单

| 文件 | 职责 |
| --- | --- |
| `types.ts` | 核心协议契约 SSOT：`IDesktopBridge`、`IWindowBridge`、`ITrayBridge`、`IShellBridge`、`IPowerBridge`、`IAppshotBridge`、`INotificationBridge`、`DesktopPlatform`、`DesktopBridgeCapabilities` |
| `bridge.ts` | 运行时环境探测（`detectDesktopPlatform`）、交通灯/标题栏几何度量（`getDesktopWindowControlsState`）与单例工厂（`createDesktopBridge`） |
| `tauri-bridge.ts` | `TauriDesktopBridge`：基于 `@/lib/tauri` 与 Tauri 原生插件的强类型 IPC 通信实现 |
| `web-fallback-bridge.ts` | `WebFallbackDesktopBridge`：纯 Web / Cloud 托管沙箱环境下的安全 No-Op 与 Web 标准 API 接入 |
| `context.tsx` | `DesktopBridgeProvider` 与 `useDesktopBridge()` React 上下文与 Hook |
| `index.ts` | 模块统一对外出口 |
| `__tests__/desktop-bridge.test.ts` | 跨环境行为与接口遵从性单元测试 |

## 依赖
- `@/lib/tauri` — `invokeTauriCommand`, `isTauriEnvironment`
- `@tauri-apps/plugin-dialog` — 原生文件选择器插件
- `@tauri-apps/plugin-notification` — 原生桌面通知插件
