# services/locked_use/

## 架构概述

Computer Use 会话的屏幕解锁编排：在 macOS 上检测锁屏、临时解锁、会话结束后恢复锁屏，并抑制显示器休眠。含无人值守编排——帷幕静默期满后代解锁续跑。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `service.py` | 核心 | `LockedUseService` / `LockedUseSession`：display keep-awake + 锁屏检测与临时解锁 | ✅ |
| `curtain_bridge.py` | 核心 | 帷幕状态桥：`curtain_state.json` 读写（server 只写 pending 位）、截图排除 titles 穿透 CuaDriver fallback 链注入 | ✅ |
| `unattended.py` | 核心 | 无人值守 watcher（5s tick）：CU 会话活跃+帷幕 active+静默期满时代理解锁；`PRIVACY_CURTAIN_UPDATED` 事件发布 | ✅ |

## 依赖

- `app.services.infra.sleep_inhibitor` — 显示器休眠抑制
- macOS Keychain — CU 解锁凭据
- `MYRM_CURTAIN_STATE_FILE` 环境变量 — desktop 帷幕状态桥文件定位
