# api/budget 模块架构


## 架构概述

预算管理 API 层。提供日预算策略的 CRUD 和实时花费状态查询端点。

## 文件清单

| 文件            | 地位   | 职责                                          | I/O/P |
| --------------- | ------ | --------------------------------------------- | ----- |
| `__init__.py`   | 入口   | 导出 budget_router                            | ✅    |
| `router.py`     | 核心   | GET/PUT /policy + GET /status API 端点        | ✅    |

## 依赖关系

### 输入依赖

- `app.services.budget.enforcer`：预算策略加载/保存/状态查询

### 被依赖

- `app.api.router`：主路由注册
