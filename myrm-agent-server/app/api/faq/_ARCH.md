# api/faq — FAQ 管理 API

## 架构概述

Per-agent FAQ 语料库的 REST API。提供 CRUD、批量导入、索引重建、命中统计和未匹配查询发现。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | re-export router | ✅ |
| `router.py` | 核心 | FAQ CRUD + 索引重建 + 统计 API 端点 | ✅ |
| `schemas.py` | 辅助 | Pydantic request/response 模型 | ✅ |

## 依赖

- `app.services.faq` — FAQ 业务服务层
