# workspace 服务模块

## 架构概述

Project vault 工作区辅助服务。Epic #1 P1：服务端目录变更检测，经 AppEvent SSE 推送 WebUI 文件树自动刷新。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `workspace_path_policy.py` | 核心 | 工作区路径的唯一闸门：`resolve_workspace_path`（绝对路径 / 危险目录 / 范围过大（含家目录、盘符根、`/` 与应用状态目录 `state_dir` 本身及其上级）/ 非目录四类拒绝，错误带 `issue`）、`is_workspace_root_grantable`（读侧：已存储的工作区是否仍可交给沙箱做写根；与闸门共用同一范围判据 `_is_too_broad`，含 `state_dir`，所以「能绑定」与「仍可用」不会不一致）、`workspace_path_http_error`（400 + `ErrorDetail(field, issue)`）、`resolve_optional_workspace_path`（可空字段：空串/None 原样放行）、`ensure_root_grantable`（定时任务的允许根：与绑定同判据，但根可以是文件或尚未存在的路径）、`require_grantable_roots`（运行时再判一遍已存的根，过宽则抛 `TOO_BROAD`）；项目创建/接纳/更新、会话工作区 PATCH、IM `/bind`、转录导入、看板任务 `workspace_path` 与看板 `default_workdir`、定时任务 `allowed_roots` 共用 | ✅ |
| `file_watch_service.py` | 核心 | refcounted watchdog；`WORKSPACE_FILE_CHANGED` SSE（载荷带单调递增 `seq`：总线会丢弃与上一条载荷相同的事件，没有它第二次起的文件树刷新都会被吞掉） | ✅ |
| `promotion/` | 子包 | 便签草稿升格为正式工作区项目落盘服务。参见 [promotion/_ARCH.md](promotion/_ARCH.md) | ✅ |
## 依赖关系

### 内部依赖
- `watchdog` — 跨平台目录递归监听
- `app/services/event/app_event_bus` — SSE 事件总线
- `myrm_agent_harness.agent.security.path_security` — 危险路径校验（`is_dangerous_path` / `covers_dangerous_path`，与沙箱策略工厂同一判据）

### 被依赖方
- `app/services/project/workspace_path_resolve.py`、`app/api/chats/chat/core.py`（PATCH `/chats/{id}/workspace`）、`app/api/chats/chat/import_session.py`、`app/services/chat/effective_workspace.py`、`app/core/channel_bridge/topic_workspace_bind.py` · `executor_helpers/topic_workspace_sync.py` — 工作区路径校验
- `app/api/files/browse_watch.py` — POST/DELETE `/files/browse/watch` 注册/释放监听
