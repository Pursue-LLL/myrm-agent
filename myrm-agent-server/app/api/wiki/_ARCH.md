# api/wiki 模块架构


## 架构概述

Wiki 知识库 API。提供 Wiki 页面的 CRUD、图谱查询和记忆转 Wiki 接口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 路由导出 | — |
| `router.py` | 核心 | Wiki REST 接口（CRUD、`/graph` 3D图谱、队列、草稿审核） | ✅ 完整 |
