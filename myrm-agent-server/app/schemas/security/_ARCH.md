# schemas/security 模块架构

安全仪表盘与平台审计相关的共享 Pydantic DTO。

## 文件清单

| 文件 | 职责 |
|------|------|
| `dashboard.py` | SecurityDashboard、PlatformAudit*、RateLimit* 等 API/services 共用模型 |

## 依赖

- 被 `app/api/security/` 与 `app/services/security/` 导入
- 禁止 services 经 `app.api` 获取 DTO
