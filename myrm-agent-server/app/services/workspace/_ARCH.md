# workspace 服务模块

## 架构概述

Project vault 工作区辅助服务。Epic #1 P1：服务端目录变更检测，经 AppEvent SSE 推送 WebUI 文件树自动刷新。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `file_watch_service.py` | 核心 | refcounted watchdog；`WORKSPACE_FILE_CHANGED` SSE | ✅ |

## 依赖关系

### 内部依赖
- `watchdog` — 跨平台目录递归监听
- `app/services/event/app_event_bus` — SSE 事件总线
- `myrm_agent_harness.agent.security.path_security` — 危险路径校验

### 被依赖方
- `app/api/files/browse_watch.py` — POST/DELETE `/files/browse/watch` 注册/释放监听
