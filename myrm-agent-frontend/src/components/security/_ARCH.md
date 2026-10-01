# components/security/

## 概述

GitHub Security Center 页面组件（`/security`）。与 Settings 内 Agent 安全策略（`settings/security`）分离。

## 文件

| 文件                                     | 职责                                                                             |
| ---------------------------------------- | -------------------------------------------------------------------------------- |
| `SecurityDashboard.tsx`                  | 页面容器：Tab 切换、数据拉取                                                     |
| `SecuritySetupPanel.tsx`                 | Webhook + monitored repos 配置                                                   |
| `IndirectInjectionAlertCard.tsx`         | 间接注入主动阻断与上下文净化自愈卡片（双主题自适应、无原生 emoji、ToC 安全抽屉） |
| `CapabilityAttenuationCapsule.tsx`       | 对象能力（OCap）受限沙箱胶囊状态组件（只读/拘禁标记、动词展开、路径/域名约束抽屉） |
| `CapabilityViolationAlertCard.tsx`        | 对象能力（OCap）越界硬拦截警告证据卡片（操作分类、目标高亮、证据链展开、一键级联撤销应急处置、双主题自适应） |
| `DependenciesTab.tsx`                    | 告警与 Dependabot PR                                                             |
| `RateLimitTab.tsx`                       | 平台限流（SaaS）                                                                 |
| `AuditLogsTab.tsx` / `AuditStatsTab.tsx` | 平台审计                                                                         |
| `auditMappers.ts`                        | 审计 API 响应映射                                                                |
| `shared.tsx`                             | SeverityBadge、MetricCard                                                        |
| `types.ts`                               | 前端类型                                                                         |

## 依赖

- `myrm-agent-frontend/src/app/security/page.tsx`
- Server `/api/v1/security/*`
