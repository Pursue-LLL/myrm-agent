# services/skills/desktop_recording/

## 架构概述

桌面工作流录制业务层：会话注册表（保留上限 + 并发采集预算）、采集循环生命周期（启动/停止/闲置自停）。HTTP 契约见 [`api/skills/desktop_recorder/`](../../../api/skills/desktop_recorder/_ARCH.md)。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 服务导出（会话注册表 API + 采集任务） | ✅ |
| `session_manager.py` | 核心 | 会话注册表：`create_session` 建会话并启动采集、`lookup_session` 解析并刷新活跃时间、`stop_session` 终结会话、`reset`（测试/诊断）；保留上限淘汰已结束会话、并发采集预算超出时释放最早的录制；闲置超时（`SESSION_IDLE_TIMEOUT_SEC`）由采集循环自我终止 | ✅ |
| `capture_task.py` | 核心 | `DesktopCaptureTask`：轮询前台 AX 快照、差分出交互事件并追加到会话；部署不支持/无权限时降级为手动录入并回传原因；`AXTreeEmptyError` 视为瞬时帧跳过，避免一次抖动废掉整段录制 | ✅ |

## 依赖

- [`../../../api/skills/desktop_recorder/schemas.py`](../../../api/skills/desktop_recorder/schemas.py) — 会话状态容器与 DTO
- `myrm_agent_harness.api::DesktopCaptureDriver` — AX 快照差分采集驱动
- `app.config.computer_use_deploy::is_computer_use_deploy_supported` — 桌面能力部署门控
