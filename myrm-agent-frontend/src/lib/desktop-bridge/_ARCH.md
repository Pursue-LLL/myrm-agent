# lib/desktop-bridge/ 模块架构

## 架构概述

Desktop Bridge 标准化原生桥接契约层：定义 `IDesktopBridge` 单一权威抽象契约（SSOT），提供基于官方 Tauri 插件的桌面原生实现（`TauriDesktopBridge`）与纯 Web / Cloud 托管沙箱环境下的安全降级实现（`WebFallbackDesktopBridge`）。契约只收录有后端实现的能力：新增原生能力须先有已注册的 Rust 命令或官方插件授权，再扩展契约，禁止先声明后补。

桌面壳（wry）不为 `window.open` 开窗且静默丢弃请求，壳自带的拦截只处理 `<a target="_blank">` 点击。外链策略（`external-link-policy.ts`）在 JS 层把"新窗口目标（缺省/空/`_blank`）+ http(s) URL"的 `window.open` 路由到桥接的外链通道，其余调用交还原生实现；由 `app-shell/external-link-initializer.tsx` 在 Tauri 环境安装。外链通道只有 `plugin-shell` 一条：被拒绝时如实返回 `false`，不得再降级 `window.open`（策略会把它路由回桥接，形成无界重入）。

## 文件清单

| 文件                                     | 职责                                                                                                                                                 |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `types.ts`                               | `IDesktopBridge`、`DesktopPlatform`、`DesktopBridgeCapabilities`、`DesktopWindowControlsState`、子桥接接口核心定义（SSOT）                           |
| `platform-detection.ts`                  | 纯运行时平台探测叶子（`detectDesktopPlatform`、`getDesktopWindowControlsState`），供工厂与 Tauri 实现共同引用保持域内单向无环                        |
| `bridge.ts`                              | 单例工厂（`createDesktopBridge`）与桥接实例出口                                                                                                      |
| `tauri-bridge.ts`                        | `TauriDesktopBridge` 原生实现（官方插件：外链 `plugin-shell` 单通道、被拒绝如实返回 `false`，文件选择 `plugin-dialog`、原生通知；托盘/截屏事件监听） |
| `external-link-policy.ts`                | `installExternalLinkPolicy`：把新窗口目标的 http(s) `window.open` 路由到系统浏览器并返回卸载函数，其余调用交还原生实现                               |
| `web-fallback-bridge.ts`                 | `WebFallbackDesktopBridge` 安全降级实现（纯 Web / Cloud 托管沙箱零异常 No-Op 与 Web 标准 API 接入）                                                  |
| `index.ts`                               | 模块对外聚合导出出口                                                                                                                                 |
| `__tests__/desktop-bridge.test.ts`       | 桥接契约合规性、平台探测、外链被拒绝如实上报与安全降级全量单元测试                                                                                   |
| `__tests__/external-link-policy.test.ts` | 外链策略路由/放行矩阵、卸载与 StrictMode、不覆盖第三方包装，以及叠加真实 Tauri 桥接时插件拒绝只尝试一次的回归                                        |

## 依赖

- `@/lib/tauri` — `isTauriEnvironment`
- `@tauri-apps/plugin-shell` — 动态引入系统外链打开（可打开的协议由 Rust 侧 `plugins.shell.open` 白名单决定）
- `@tauri-apps/plugin-dialog` — 动态引入原生文件选择器
- `@tauri-apps/plugin-notification` — 动态引入原生桌面通知
