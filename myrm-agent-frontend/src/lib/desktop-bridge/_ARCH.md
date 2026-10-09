# lib/desktop-bridge/ 模块架构

## 架构概述

Desktop Bridge 标准化原生桥接契约层：定义 `IDesktopBridge` 单一权威抽象契约（SSOT），提供基于官方 Tauri 插件的桌面原生实现（`TauriDesktopBridge`）与纯 Web / Cloud 托管沙箱环境下的安全降级实现（`WebFallbackDesktopBridge`）。契约只收录有后端实现的能力：新增原生能力须先有已注册的 Rust 命令或官方插件授权，再扩展契约，禁止先声明后补。

## 文件清单

| 文件                               | 职责                                                                                                                          |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `types.ts`                         | `IDesktopBridge`、`DesktopPlatform`、`DesktopBridgeCapabilities`、`DesktopWindowControlsState`、子桥接接口核心定义（SSOT）    |
| `platform-detection.ts`            | 纯运行时平台探测叶子（`detectDesktopPlatform`、`getDesktopWindowControlsState`），供工厂与 Tauri 实现共同引用保持域内单向无环 |
| `bridge.ts`                        | 单例工厂（`createDesktopBridge`）与桥接实例出口                                                                               |
| `tauri-bridge.ts`                  | `TauriDesktopBridge` 原生实现（官方插件：外链 `plugin-shell`、文件选择 `plugin-dialog`、原生通知；托盘/截屏事件监听）          |
| `web-fallback-bridge.ts`           | `WebFallbackDesktopBridge` 安全降级实现（纯 Web / Cloud 托管沙箱零异常 No-Op 与 Web 标准 API 接入）                           |
| `context.tsx`                      | `DesktopBridgeProvider` 与 `useDesktopBridge` React 上下文与 Hook                                                             |
| `index.ts`                         | 模块对外聚合导出出口                                                                                                          |
| `__tests__/desktop-bridge.test.ts` | 桥接契约合规性、平台探测、外链插件/浏览器降级与安全降级全量单元测试                                                          |

## 依赖

- `@/lib/tauri` — `isTauriEnvironment`
- `@tauri-apps/plugin-shell` — 动态引入系统外链打开（可打开的协议由 Rust 侧 `plugins.shell.open` 白名单决定）
- `@tauri-apps/plugin-dialog` — 动态引入原生文件选择器
- `@tauri-apps/plugin-notification` — 动态引入原生桌面通知
