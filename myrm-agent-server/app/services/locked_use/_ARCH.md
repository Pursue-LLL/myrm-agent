# services/locked_use/

## 架构概述

Computer Use 会话的屏幕解锁编排：在 macOS 上检测锁屏、临时解锁、会话结束后恢复锁屏，并抑制显示器休眠。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `service.py` | 核心 | `LockedUseService` / `LockedUseSession`：display keep-awake + 锁屏检测与临时解锁 | ✅ |

## 依赖

- `app.services.infra.sleep_inhibitor` — 显示器休眠抑制
- macOS Keychain — CU 解锁凭据
