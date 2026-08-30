# lib/desktop-bridge/ 模块架构

## 架构概述

Desktop Bridge 标准化原生契约层：封装 OS 级窗口几何留白探测、原生对话框、桌面通知、能力自检与 Web 优雅降级管道。

## 文件清单

| 文件 | 职责 |
| --- | --- |
| `types.ts` | DesktopBridge、DesktopPlatform、DesktopWindowControlsState、DesktopBridgeCapabilities 核心接口定义 |
| `bridge.ts` | StandardDesktopBridge 单例与 getDesktopWindowControlsState / detectDesktopPlatform 实现 |
| `index.ts` | 模块对外聚合导出出口 |

## 依赖
- `@/lib/tauri` — `isTauriEnvironment`
- `@tauri-apps/plugin-dialog` — 动态引入原生文件选择器
- `@tauri-apps/plugin-notification` — 动态引入原生桌面通知
