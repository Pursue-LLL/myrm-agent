# api/wiki/

## 架构概述

Wiki 知识库 HTTP 层：页面/空间 CRUD 与检索入口。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Wiki API router. | ✅ |
| `router.py` | 路由 | 业务层 Wiki API 路由。提供全量 REST 端点供前端 Brain Console 调用：查询/编译/维护/ingest wiki。/concepts (CRUD)、/queue (状态控制)、/pending (人工审核)、/ingest (artifact 内容写入知识库)。 | ✅ |
