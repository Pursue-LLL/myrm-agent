# components/security/

## 概述

GitHub Security Center 页面组件（`/security`）。与 Settings 内 Agent 安全策略（`settings/security`）分离。

## 文件

| 文件 | 职责 |
|------|------|
| `SecurityDashboard.tsx` | 页面容器：Tab 切换、数据拉取 |
| `SecuritySetupPanel.tsx` | Webhook + monitored repos 配置 |
| `DependenciesTab.tsx` | 告警与 Dependabot PR |
| `RateLimitTab.tsx` | 平台限流（SaaS） |
| `AuditLogsTab.tsx` / `AuditStatsTab.tsx` | 平台审计 |
| `auditMappers.ts` | 审计 API 响应映射 |
| `shared.tsx` | SeverityBadge、MetricCard |
| `types.ts` | 前端类型 |

## 依赖

- `myrm-agent-frontend/src/app/security/page.tsx`
- Server `/api/v1/security/*`
