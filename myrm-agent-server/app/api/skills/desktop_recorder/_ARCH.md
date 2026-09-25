# api/skills/desktop_recorder/

## 架构概述

桌面工作流技能录制 HTTP 层：会话生命周期端点、事件采集入口、意图分析与 SKILL.md 编译发布。会话语义（保留/预算/采集循环）委托给 [`services/skills/desktop_recording/`](../../../services/skills/desktop_recording/_ARCH.md)。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router` | — |
| `router.py` | 核心 | `/desktop-recorder/*` 端点：`start`（建会话并启动采集）、`event`（事件落库）、`stop`、`session/{id}`（轮询采集状态）、`synthesize`、`analyze-plan`、`compile-plan`、`publish`（写本地技能库并 bump 配置版本）；会话解析统一走 `_require_session` => 未知 id 返回 404 | ✅ |
| `schemas.py` | 契约 | 请求/响应 Pydantic 模型 + `RecordingSessionState`（会话状态容器、事件环形缓冲上限、`SESSION_IDLE_TIMEOUT_SEC` 闲置阈值、`touch()` 活跃标记） | ✅ |

## 依赖

- [`../../../services/skills/desktop_recording/`](../../../services/skills/desktop_recording/_ARCH.md) — 会话注册表与采集循环
- `myrm_agent_harness.api` — `DesktopRecordedEvent`、`synthesize_desktop_skill_draft`、`WorkflowIntentPlan`、`WorkflowSkillCompiler`
