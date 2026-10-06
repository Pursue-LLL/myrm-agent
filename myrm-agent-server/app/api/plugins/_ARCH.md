# api/plugins/

## 架构概述

Agent Plugins 1.0.0 导入/导出 HTTP 层。导入：`preview`（解析 ZIP + 组件级预览，含冲突、阻断原因、部署开关、专家生效值与未解析引用）与 `confirm`（技能走隔离安装管线 + MCP + 专家落盘，响应带逐专家结果 `agents` 与逐组件 `failures`）。导出：`export/preview`（专家闭包卡片、未随包带出清单、脱敏发现与 `review_digest`、试构建结果）与 `export`（经脱敏决策核验后的 ZIP 下载）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Plugin import API module | ✅ |
| `import_.py` | 模块 | `POST /plugins/import/preview` + `POST /plugins/import/confirm`；multipart 上传 → 持久化会话 → 批量落盘（技能、MCP、专家团队与模板物料）；响应模型经 `model_validate` 与服务层字典对齐（`blocked_reason` / `deployment` / `failures` 等字段不会在序列化中丢失）；归档安全错误输出结构化 `detail={message,error_code}` 供前端 i18n；`GET /plugins/import/installed`（已导入插件列表，含 `server_meta` 每 server `{name, enabled}` 状态）+ `DELETE /plugins/import/{plugin_name}`（插件卸载） | ✅ |
| `export.py` | 模块 | `POST /plugins/export/preview` + `POST /plugins/export`；预览返回专家 / 技能 / 连接器（仅密钥名）/ 工作区文件卡片、`omitted`（结构化原因码）、复用技能导出的 `RedactionResponse` 脱敏差异与 `review_digest`、试构建包大小或 `build_error`；导出接收 `apply_redactions` / `ignored_redactions` / `review_digest`，成功返回 `application/zip`；拒绝一律 `detail={message,error_code}`（`expert_not_found` 404、`built_in_expert` 422、`redaction_review_required` / `export_changed_since_preview` 409、`package_rejected` 422） | ✅ |

## 设计原则

- **GUI-First**：预览阶段不落任何数据，用户逐项决策后才 confirm。
- **错误结构化**：archive security 拦截以 `error_code` 上报（复用前端 `resolveUserFacingArchiveSecurityError`）；普通错误使用英文消息。
- **异步清理**：过期会话清理通过 `BackgroundTasks` 调用 `PluginStaging.cleanup_expired_sessions`。
- **存储路径**：staging 根目录取自 `get_evolution_skill_store_db_path()`（core 统一 accessor），避免经 API helper 间接构造 store。
- **导出评审与技能导出同形**：脱敏发现沿用技能导出的契约（`apply_redactions` / `ignored_redactions` / `review_digest`，409 + `{message,error_code}`），前端复用同一评审组件；服务端强制评审（未处置的发现无法下载），不依赖前端自觉。
- **列表/卸载代理**：`GET /installed` 与 `DELETE /{plugin_name}` 均为薄代理，直接转发 `import_service.list_installed_plugins` / `uninstall_plugin` 结果并做 Pydantic 校验；卸载返回结构化摘要（移除 server 数 / 解绑 Agent 数 / 是否删除文件）供前端展示。
