# api/plugins/

## 架构概述

Agent Plugins 1.0.0 导入 HTTP 层：`preview`（解析 ZIP + 组件级预览）与 `confirm`（落盘技能/MCP + 绑定 Agent）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Plugin import API module | ✅ |
| `import_.py` | 模块 | `POST /plugins/import/preview` + `POST /plugins/import/confirm`；multipart 上传 → 持久化会话 → 落盘；归档安全错误输出结构化 `detail={message,error_code}` 供前端 i18n | ✅ |

## 设计原则

- **GUI-First**：预览阶段不落任何数据，用户逐项决策后才 confirm。
- **错误结构化**：archive security 拦截以 `error_code` 上报（复用前端 `resolveUserFacingArchiveSecurityError`）；普通错误使用英文消息。
- **异步清理**：过期会话清理通过 `BackgroundTasks` 调用 `PluginStaging.cleanup_expired_sessions`。
- **存储路径**：staging 根目录取自 `get_evolution_skill_store_db_path()`（core 统一 accessor），避免经 API helper 间接构造 store。
