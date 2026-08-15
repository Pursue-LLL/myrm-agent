# memory/operations/crud 模块架构

记忆 CRUD 域处理器。由父目录 `crud_handlers.py` 门面统一 re-export（见 `operations/_ARCH.md`），供 `app/api/memory/operations/crud.py` 路由绑定。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `_common.py` | 辅助 | `_record_memory_event`、`_SORT_KEYS` | ✅ |
| `list_write.py` | 核心 | 列表、创建、更新、纠正、删除、搜索、统计、评分、状态变更 | ✅ |
| `trash.py` | 核心 | 回收站列表、恢复、永久删除 | ✅ |
| `import_archive.py` | 核心 | 导出（JSON + Markdown ZIP）、归档、导入、回滚；竞品 dry-run 四车道；confirm 写入 Hermes `moa`→Agent `moa_overlay`（经 `hermes_moa_migrator`）；返回 `readiness` + `workspace_bind_candidates`；`POST /import/readiness-recheck` 用当前 provider 状态重算 readiness | ✅ |
| `import_readiness.py` | 辅助 | 导入后运行就绪合同聚合（provider/diagnostic/MCP/rules → ready/warning/critical + issue codes）；`build_readiness_issue` 填充 issue.settings_path；issue→settings_path SSOT 与 gap 文案 | ✅ |
| `preferences.py` | 核心 | 偏好摘要、偏好列表、pin/forget/unpin/unforget | ✅ |
