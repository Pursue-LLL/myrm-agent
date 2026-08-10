# profile/

## 架构概述

Agent Profile 业务域：统一配置解析、builtin 工具标志映射与配置快照回滚服务。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `profile_resolver.py` | ✅ 核心 | 统一智能体配置解析 — re-export `resolve_builtin_tool_flags`（见 `profile_builtin_tools.py`）；TTL 缓存 | ✅ |
| `profile_builtin_tools.py` | ✅ 核心 | `enabled_builtin_tools` → enable_xxx 标志映射唯一入口（`resolve_builtin_tool_flags(..., allow_answer_tool=False)`，strip deploy 不兼容工具；Fast Search 在 converter 显式 `allow_answer_tool=True`）+ metadata 规范化 helper | ✅ |
| `profile_snapshot_service.py` | ✅ 核心 | Agent 配置快照与回滚专用服务 — `save_profile_snapshot` / `list_profile_snapshots` / `count_profile_snapshots` / `rollback_profile` / `rollback_profile_to_snapshot`。含完整 mutable 字段 diff 检测（`has_mutable_diff`，含 `cron_post_run_verify` DB 列）、pre-rollback 保险快照、10 条 retention 裁剪；`updates_from_snapshot_data` 回滚时写回该列。由 `AgentService` 委托，供 WebUI 时光机 API 使用 | ✅ |

## 依赖

- 父模块 [`agent/_ARCH.md`](../_ARCH.md)
- `builtin_specs/builtin_tool_ids`（工具 ID 清单）
