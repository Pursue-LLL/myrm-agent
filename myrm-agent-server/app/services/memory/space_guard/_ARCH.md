# services/memory/space_guard 模块架构

## 架构概述

向量空间守卫：`VectorSpaceGuardService` 管理嵌入模型指纹，在检索前校验向量空间与当前模型是否一致，提供空间绑定、状态查询与重建索引（`VectorSpaceReindexer`）流程，DTO 来自 `app.schemas.space_guard`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 辅助 | 导出 `VectorSpaceGuardService` 与 `get_space_guard_service` | ✅ |
| `provider.py` | 核心 | `VectorSpaceGuardService`：validate_space / bind_space / get_space_status / execute_reindex；`get_space_guard_service` 单例入口 | ✅ |
