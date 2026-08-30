# lib/desktop-bridge/ 模块架构

## 架构概述

Desktop Bridge 标准化原生契约层：提供纯 WebUI、Tauri 桌面端与 Cloud 托管沙箱三端同构的原生桥接契约（`IDesktopBridge`），封装 OS 级窗口几何留白探测、原生对话框、桌面通知、系统休眠锁、屏幕快照与 Web 优雅降级管道。

## 文件清单

| 文件 | 职责 |
| --- | --- |
| `types.ts` | `IDesktopBridge`、`DesktopPlatform`、`DesktopBridgeCapabilities`、`DesktopWindowControlsState` 等核心接口与类型契约（SSOT） |
| `bridge.ts` | `detectDesktopPlatform`、`getDesktopWindowControlsState`、`createDesktopBridge` 工厂函数与全局单例导出 |
| `tauri-bridge.ts` | `TauriDesktopBridge`：基于 Tauri 2.0 Rust IPC 的原生桌面端桥接实现 |
| `web-fallback-bridge.ts` | `WebFallbackDesktopBridge`：纯 Web 与 Cloud 沙箱环境下的零异常安全 No-Op 与标准 Web API 降级实现 |
| `context.tsx` | `DesktopBridgeProvider` 与 `useDesktopBridge` React 上下文与 Hook |
| `index.ts` | 模块对外聚合导出出口 |
| `__tests__/desktop-bridge.test.ts` | 单元测试：验证契约一致性、安全降级与平台探测 |

## 依赖
- `@/lib/tauri` — `isTauriEnvironment`, `invokeTauriCommand`
- `@tauri-apps/plugin-dialog` — 动态引入原生文件选择器
- `@tauri-apps/plugin-notification` — 动态引入原生桌面通知
