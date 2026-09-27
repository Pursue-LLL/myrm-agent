# api/skills/desktop_recorder/

## 架构概述

桌面工作流技能录制 HTTP 层：会话生命周期端点、事件采集入口、意图分析与 SKILL.md 编译发布。会话语义（保留/预算/采集循环）委托给 [`services/skills/desktop_recording/`](../../../services/skills/desktop_recording/_ARCH.md)。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router` | — |
| `router.py` | 核心 | `/desktop-recorder/*` 端点：`start`（建会话并启动采集）、`event`（事件落库）、`stop`、`session/{id}`（轮询采集状态）、`synthesize`、`analyze-plan`、`compile-plan`、`publish`（写本地技能库并 bump 配置版本；同名技能默认返回 409，需显式 `overwrite=true` 才覆盖，避免默认名互相践踏）；会话解析统一走 `_require_session` => 未知 id 返回 404。动作判定一律使用 `RecordedActionType` 枚举（禁止裸字面量，否则改名后静默落入通用分支）；`allowed_tools` 取自 harness SSOT `DEFAULT_ALLOWED_TOOLS`（禁止本地硬编码，伪造工具名会被技能衰减过滤掉真实工具）；密码角色统一掩码（`is_password` 或 `element_role` 命中安全角色）；`session/{id}` 返回 `events_dropped` 以如实披露轨迹被裁剪 | ✅ |
| `schemas.py` | 契约 | 端点契约门面：从 `app.schemas.desktop_recorder` re-export 请求/响应 DTO，并从 [`services/skills/desktop_recording/state.py`](../../../services/skills/desktop_recording/state.py) re-export 会话运行时状态（`RecordingSessionState`、`SESSION_IDLE_TIMEOUT_SEC`）。依赖方向为 api → services，DTO 层不反向依赖 services | ✅ |

## 依赖

- [`../../../services/skills/desktop_recording/`](../../../services/skills/desktop_recording/_ARCH.md) — 会话注册表与采集循环
- `myrm_agent_harness.api` — `DesktopRecordedEvent`、`RecordedActionType`、`is_secure_role`、`DEFAULT_ALLOWED_TOOLS`、`synthesize_desktop_skill_draft`、`WorkflowIntentPlan`、`WorkflowSkillCompiler`
