# services/skills/desktop_recording/

## 架构概述

桌面工作流录制业务层：会话注册表（保留上限 + 并发采集预算）、采集循环生命周期（启动/停止/闲置自停）。HTTP 契约见 [`api/skills/desktop_recorder/`](../../../api/skills/desktop_recorder/_ARCH.md)。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 服务导出（会话注册表 API + 采集任务） | ✅ |
| `state.py` | 核心 | `RecordingSessionState` 会话运行时状态容器（事件环形缓冲上限 `_MAX_EVENTS_PER_SESSION`、`SESSION_IDLE_TIMEOUT_SEC` 闲置阈值、`touch()` 活跃标记），及 `is_password` 等字段的落库投影 | ✅ |
| `session_manager.py` | 核心 | 会话注册表：`create_session` 建会话并启动采集、`lookup_session` 解析并刷新活跃时间、`stop_session` 终结会话、`reset`（测试/诊断）；保留上限淘汰已结束会话、并发采集预算超出时释放最早的录制；闲置超时由采集循环自我终止 | ✅ |
| `capture_task.py` | 核心 | `DesktopCaptureTask`：轮询前台 AX 快照、差分出交互事件并追加到会话；部署不支持时降级为手动录入；`AXTreeEmptyError` 视为瞬时帧跳过；**权限缺失时在宽限期（`_PERMISSION_GRACE_SEC`）内继续轮询**，用户中途授权即自动恢复，超时才释放会话 | ✅ |

## 依赖

- `app.services.skills.desktop_recording.state` — 会话状态容器（本层自持，不依赖 `app.api`）
- `myrm_agent_harness.api::DesktopCaptureDriver` — AX 快照差分采集驱动
- `app.config.computer_use_deploy::is_computer_use_deploy_supported` — 桌面能力部署门控
