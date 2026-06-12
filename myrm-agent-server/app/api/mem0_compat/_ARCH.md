# api/mem0_compat/

## 架构概述

Mem0 API 兼容层。使 Mem0 SDK 用户仅修改 `host` 参数即可无缝接入 Myrm 记忆后端。上级文档：[../_ARCH.md](../_ARCH.md)。

## 设计原则

- **纯转换层**：不包含业务逻辑，仅做请求/响应格式转换
- **委托现有 handler**：所有操作最终委托给 `MemoryManager` 和现有 CRUD 服务
- **与 openai_compat 平行**：遵循相同的模块划分和挂载模式
- **零影响**：不修改任何现有核心逻辑，可随时移除

## 路由映射

| Mem0 SDK 调用 | HTTP 路径 | 对应内部操作 |
|---|---|---|
| `client.ping()` | `GET /mem0/v1/ping/` | 健康检查 |
| `client.add()` | `POST /mem0/v3/memories/add/` | 创建 semantic 记忆 |
| `client.get()` | `GET /mem0/v1/memories/{id}/` | 按 ID 查询 |
| `client.get_all()` | `POST /mem0/v3/memories/` | 分页列出所有记忆 |
| `client.search()` | `POST /mem0/v3/memories/search/` | 语义搜索 |
| `client.update()` | `PUT /mem0/v1/memories/{id}/` | 更新记忆内容 |
| `client.delete()` | `DELETE /mem0/v1/memories/{id}/` | 删除单条记忆 |
| `client.delete_all()` | `DELETE /mem0/v1/memories/` | 删除全部记忆 |
| `client.history()` | `GET /mem0/v1/memories/{id}/history/` | 记忆变更历史 |

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Mem0 API compatibility layer. | ✅ |
| `router.py` | 路由 | 聚合所有 Mem0 兼容端点到 /mem0 前缀 | ✅ |
| `types.py` | 模块 | Mem0 wire-format 请求/响应 Pydantic 模型 | ✅ |
| `converter.py` | 模块 | Myrm ↔ Mem0 格式双向转换 | ✅ |
| `endpoints.py` | 模块 | FastAPI 路由处理器实现 | ✅ |
