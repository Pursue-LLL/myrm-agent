# services/auth 模块架构


---

## 架构概述

认证服务包目前只保留包标记，运行时不再提供独立的认证服务。单租户身份由 `app.middleware.auth` 和 `app.core.security.auth.dependencies` 处理。

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包标记，无运行时导出。 |

---

## 依赖关系

- `app.middleware.auth`：请求级身份注入
- `app.core.security.auth.dependencies`：FastAPI 依赖注入
