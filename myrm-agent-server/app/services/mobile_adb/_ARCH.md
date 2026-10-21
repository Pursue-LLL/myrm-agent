# services/mobile_adb 模块架构

## 架构概述

移动端 Wireless ADB 业务服务层。对接 harness `toolkits.mobile_adb.MobileSession`，向 Integrations API 提供设备列表、配对、连接、快照与交互。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 包声明 | 导出 `MobileDeviceService` / `get_mobile_device_service` | ✅ |
| `service.py` | 核心服务 | 适配 harness `MobileSession` → API DTO（list/pair/connect/snapshot/interact） | ✅ |

## 边界

- harness 负责 ADB 驱动与语义动作；本层不做第二套 ADB 封装。
- 无设备时 snapshot/interact 返回 `success=False`，不抛未捕获异常阻断进程启动。
