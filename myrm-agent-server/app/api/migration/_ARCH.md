# api/migration 模块架构


## 架构概述

竞品数据迁移 API 路由层。暴露本地竞品数据自动发现与 opt-in secrets 导入接口供前端消费。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `discovery.py` | 核心 | `GET /migration/discover` 扫描；`POST /migration/secrets/import` opt-in 导入 API Key | ✅ |
| `__init__.py` | 辅助 | 包初始化 | ✅ |

## 部署约束

- discover 与 secrets/import 仅在 `is_local_mode()` 时可用
- SaaS 模式返回空 sources / 403
