# api/plugins/

## 架构概述

Agent Plugins 1.0.0 导入 HTTP 层：`preview`（解析 ZIP + 组件级预览）与 `confirm`（落盘技能/MCP + 绑定 Agent）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Plugin import API module | ✅ |
| `import_.py` | 模块 | `POST /plugins/import/preview` + `POST /plugins/import/confirm`；multipart 上传 → 持久化会话 → 批量落盘（技能、MCP、Agent 团队与模板物料）；归档安全错误输出结构化 `detail={message,error_code}` 供前端 i18n；`GET /plugins/import/installed`（已导入插件列表，含 `server_meta` 每 server `{name, enabled}` 状态）+ `DELETE /plugins/import/{plugin_name}`（插件卸载） | ✅ |

## 设计原则

- **GUI-First**：预览阶段不落任何数据，用户逐项决策后才 confirm。
- **错误结构化**：archive security 拦截以 `error_code` 上报（复用前端 `resolveUserFacingArchiveSecurityError`）；普通错误使用英文消息。
- **异步清理**：过期会话清理通过 `BackgroundTasks` 调用 `PluginStaging.cleanup_expired_sessions`。
- **存储路径**：staging 根目录取自 `get_evolution_skill_store_db_path()`（core 统一 accessor），避免经 API helper 间接构造 store。
- **列表/卸载代理**：`GET /installed` 与 `DELETE /{plugin_name}` 均为薄代理，直接转发 `import_service.list_installed_plugins` / `uninstall_plugin` 结果并做 Pydantic 校验；卸载返回结构化摘要（移除 server 数 / 解绑 Agent 数 / 是否删除文件）供前端展示。
