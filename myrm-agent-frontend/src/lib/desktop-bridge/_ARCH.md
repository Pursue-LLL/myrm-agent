# lib/desktop-bridge/ 模块架构

## 架构概述

Desktop Bridge 标准化原生契约层：提供统一的 `IDesktopBridge` 抽象与双实现（`TauriDesktopBridge` 与 `WebFallbackDesktopBridge`）。
抹平 WebUI、Tauri 桌面端与 Cloud 托管沙箱的环境差异，提供 OS 级窗口几何留白探测、原生对话框、桌面通知、系统托盘、电源锁与安全 Web 降级。

## 文件清单

| 文件 | 职责 |
| --- | --- |
| `types.ts` | `IDesktopBridge`、`DesktopPlatform`、`DesktopWindowControlsState`、`DesktopBridgeCapabilities` 等核心契约定义 (SSOT) |
| `bridge.ts` | `detectDesktopPlatform`、`getDesktopWindowControlsState`、`createDesktopBridge` 工厂函数与单例导出 |
| `tauri-bridge.ts` | `TauriDesktopBridge` 原生 IPC 实现类 |
| `web-fallback-bridge.ts` | `WebFallbackDesktopBridge` 纯 Web / Cloud 零异常安全降级实现类 |
| `context.tsx` | `DesktopBridgeProvider` 与 `useDesktopBridge` React 上下文与 Hook |
| `index.ts` | 模块对外聚合导出出口 |
| `__tests__/desktop-bridge.test.ts` | 单元测试，保证双环境接口合规与降级韧性 |

## 依赖
- `@/lib/tauri` — `isTauriEnvironment`, `invokeTauriCommand`
- `@tauri-apps/plugin-dialog` — 动态引入原生文件选择器
- `@tauri-apps/plugin-notification` — 动态引入原生桌面通知
