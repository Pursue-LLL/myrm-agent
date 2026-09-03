# lib/desktop-bridge/ 模块架构

## 架构概述

Desktop Bridge 标准化原生桥接契约层：定义 `IDesktopBridge` 单一权威抽象契约（SSOT），提供 Tauri 桌面原生 IPC 实现（`TauriDesktopBridge`）与纯 Web / Cloud 托管沙箱环境下的安全降级实现（`WebFallbackDesktopBridge`）。

## 文件清单

| 文件                               | 职责                                                                                                                       |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `types.ts`                         | `IDesktopBridge`、`DesktopPlatform`、`DesktopBridgeCapabilities`、`DesktopWindowControlsState`、子桥接接口核心定义（SSOT） |
| `bridge.ts`                        | 运行时环境探测（`detectDesktopPlatform`、`getDesktopWindowControlsState`）与单例工厂（`createDesktopBridge`）              |
| `tauri-bridge.ts`                  | `TauriDesktopBridge` 原生实现（打通 Tauri Rust IPC：窗口控制、系统托盘、文件定位、原生通知、电源休眠锁）                   |
| `web-fallback-bridge.ts`           | `WebFallbackDesktopBridge` 安全降级实现（纯 Web / Cloud 托管沙箱零异常 No-Op 与 Web 标准 API 接入）                        |
| `context.tsx`                      | `DesktopBridgeProvider` 与 `useDesktopBridge` React 上下文与 Hook                                                          |
| `index.ts`                         | 模块对外聚合导出出口                                                                                                       |
| `__tests__/desktop-bridge.test.ts` | 桥接契约合规性、平台探测与安全降级全量单元测试                                                                             |

## 依赖

- `@/lib/tauri` — `isTauriEnvironment`, `invokeTauriCommand`
- `@tauri-apps/plugin-dialog` — 动态引入原生文件选择器
- `@tauri-apps/plugin-notification` — 动态引入原生桌面通知
