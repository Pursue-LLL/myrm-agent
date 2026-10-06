# services/locked_use/

## 架构概述

Computer Use 会话的屏幕解锁编排：在 macOS 上用 harness 原生探针检测锁屏、临时解锁、会话结束后经同一探针校验回锁，并抑制显示器休眠。含无人值守编排——帷幕静默期满后获取代解锁租约续跑；租约在帷幕持有期间始终保持（电平语义，非单次脉冲），CU 会话结束且系统确认已回锁后才交还，回锁失败则保留租约、帷幕继续遮盖。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `service.py` | 核心 | `MacScreenUnlocker`（`is_locked` 原生探针 / `get_password` 经 `security -g` 带标记输出逐字节还原密码 / `unlock` 持锁串行且持锁后复探 / `relock_verified` 回锁校验 / `ensure_locked`）、`release_unlock_lease`（确认已锁才清租约位）与 `locked_use_session`：display keep-awake + 租约式临时解锁与交还 | ✅ |
| `unattended.py` | 核心 | 无人值守 watcher（5s tick）：五条件齐备时获取代解锁租约并保持；CU 会话结束时校验回锁后交还（失败按 60s 冷却重试）；帷幕被撤或屏幕被外部锁定即作废租约；启动时接管上一进程遗留的租约位 | ✅ |
| `curtain_bridge.py` | 核心 | 帷幕状态桥：`curtain_state.json` 读写（server 只写租约位，电平语义，整文件原子替换）、`curtain_status_payload` 对外载荷、截图排除 titles 穿透 CuaDriver fallback 链注入 | ✅ |

## 依赖

- `app.services.infra.sleep_inhibitor` — 显示器休眠抑制
- `myrm_agent_harness.api.security` — `get_default_screen_detector`（macOS Quartz 进程内锁屏探针，锁屏状态的唯一事实来源）
- macOS Keychain — CU 解锁凭据
- `MYRM_CURTAIN_STATE_FILE` 环境变量 — desktop 帷幕状态桥文件定位
