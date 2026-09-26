# schemas/security 模块架构

安全仪表盘与平台审计相关的共享 Pydantic DTO。

## 文件清单

| 文件 | 职责 |
|------|------|
| `base.py` | `CamelModel`：camelCase 别名契约基类（同时接受 camelCase 与 snake_case 输入），供本包各 DTO 复用 |
| `dashboard.py` | SecurityDashboard、PlatformAudit*、RateLimit* 等 API/services 共用模型 |
| `scan_comparison.py` | FindingItem、ScanRunSummary、ScanComparisonResult 等安全漏洞与跨版本差量比对模型 |

## 依赖

- 被 `app/api/security/` 与 `app/services/security/` 导入
- 禁止 services 经 `app.api` 获取 DTO
