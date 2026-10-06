# services/locked_use/

## 架构概述

Computer Use 会话的屏幕解锁编排：在 macOS 上用 harness 原生探针检测锁屏、临时解锁、会话结束后经同一探针校验回锁，并抑制显示器休眠。含无人值守编排——CU 工具撞上锁屏时按需代解锁（Locked Use 已授权、帷幕有效、静默期满、机前无人（硬件输入空闲）才获取代解锁租约续跑）；租约在帷幕持有期间始终保持（电平语义，非单次脉冲），CU 会话结束且系统确认已回锁后才交还，回锁失败则保留租约、帷幕继续遮盖。帷幕活在桌面壳进程里：壳存活由 `MYRM_SHELL_PID` 判定并折入有效帷幕态，壳崩溃/被强杀后不再代解锁、持租约则立即校验回锁；壳优雅退出时 lifespan 关闭期最先回锁交还。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `service.py` | 核心 | `MacScreenUnlocker`（`is_locked` 原生探针 / `user_present` 在场探针：硬件输入空闲不足 `PRESENCE_IDLE_THRESHOLD_SECONDS`（15 s）或探测未知即视为人在机前 / `get_password` 经 `security -g` 带标记输出逐字节还原密码 / `unlock` 持锁串行且持锁后复探锁态与在场 / `relock_verified` 回锁校验 / `ensure_locked`）、`release_unlock_lease`（确认已锁才清租约位）与 `locked_use_session`：display keep-awake + 租约式临时解锁与交还（人在机前时不取租约、不解锁） | ✅ |
| `unattended.py` | 核心 | 无人值守编排。**按需获取**：`attach_desktop_session` 把 CU 会话接入帷幕（截图排除通道 + harness `ScreenUnlockCallback`），Guardian 撞上锁屏才回调 `unlock_screen_on_demand`（纯文本任务不触碰屏幕）；五条件齐备（Locked Use 已授权 `MYRM_LOCKED_USE_ENABLED`、帷幕有效、静默期满、重试未超限、机前无人则整次放弃——不置租约位、不计失败、不键入）才先置租约位再代解锁，Guardian 重探测放行；获取单飞（并发调用共享一次键入）、有界等待（20s，超时/调用方取消只放弃等待、获取照常收尾）、仅 watcher 运行时受理、与交还经 `_lease_guard` 串行。**watcher（5s tick）监护**：CU 会话结束时校验回锁后交还（失败按 60s 冷却重试）；帷幕被撤或屏幕被外部锁定即作废租约；用户亲自解锁重置失败计数；启动时接管上一进程遗留的租约位（含壳已失联的遗留）；壳失联时持租约不等会话结束立即校验回锁（失败同样冷却重试）、未持租约不再代解锁；`stop_unattended_curtain_watcher` 供 lifespan 关闭期最先停 watcher、等在途获取走完再回锁交还 | ✅ |
| `curtain_bridge.py` | 核心 | 帷幕状态桥：`curtain_state.json` 读写（server 只写租约位，电平语义，整文件原子替换）、`curtain_status_payload` 对外载荷、截图排除 titles 穿透 CuaDriver fallback 链注入；`shell_alive`（`MYRM_SHELL_PID` 指向的进程存在、非僵尸且不晚于本进程创建——PID 被无关新进程复用即判失联；缺失/非法 fail-closed）折入有效帷幕态 `active`（文件 active ∧ 壳存活），代解锁授权 / 目标评估截图授权 / 手机端「屏幕已保护」徽标三个消费方读到的都是真实遮蔽状态 | ✅ |

## 依赖

- `app.services.infra.sleep_inhibitor` — 显示器休眠抑制
- `myrm_agent_harness.api.security` — `get_default_screen_detector`（macOS Quartz 进程内锁屏探针，锁屏状态的唯一事实来源）、`hid_idle_seconds`（硬件输入空闲秒数，在场判定的唯一事实来源）
- `myrm_agent_harness.toolkits.computer_use` — `ComputerSession.set_screen_unlock_callback`（Guardian 锁屏按需解锁注入点；harness 只回调不解锁，是否解锁、如何解锁由本模块决定）
- macOS Keychain — CU 解锁凭据
- `MYRM_CURTAIN_STATE_FILE` 环境变量 — desktop 帷幕状态桥文件定位
- `MYRM_SHELL_PID` 环境变量 — desktop 壳进程身份（Tauri `python_backend` 注入；release sidecar 为 PyInstaller `--onefile`，`getppid` 不指向壳）
