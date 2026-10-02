# components/security/

## 概述

GitHub Security Center 页面组件（`/security`）。与 Settings 内 Agent 安全策略（`settings/security`）分离。

## 文件

| 文件                                     | 职责                                                                                                            |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `SecurityDashboard.tsx`                  | 页面容器：Tab 切换、数据拉取                                                                                    |
| `SecuritySetupPanel.tsx`                 | Webhook + monitored repos 配置                                                                                  |
| `IndirectInjectionAlertCard.tsx`         | 间接注入主动阻断与上下文净化自愈卡片（双主题自适应、无原生 emoji、ToC 安全抽屉）                                |
| `CapabilityAttenuationCapsule.tsx`       | 对象能力（OCap）受限沙箱胶囊状态组件（只读/拘禁标记、动词展开、路径/域名约束抽屉）                              |
| `CapabilityViolationAlertCard.tsx`       | 对象能力（OCap）越界硬拦截警告证据卡片（操作分类、目标高亮、证据链展开、一键级联撤销应急处置、双主题自适应）    |
| `AutonomyBreakerAlertCard.tsx`           | 自主等级异常断路器跳闸熔断接管卡片（10ms 物理阻断、L4->L2 强制降级指示、技术堆栈展开、确认恢复/降级防连击交互） |
| `ZDRComplianceDrawer.tsx`                | 企业级零数据保留（ZDR）合规状态徽章与多端抽屉（RAM-Only 状态、哈希指纹复制、合规证明导出、0x00 物理覆写抹零）   |
| `DependenciesTab.tsx`                    | 告警与 Dependabot PR                                                                                            |
| `RateLimitTab.tsx`                       | 平台限流（SaaS）                                                                                                |
| `AuditLogsTab.tsx` / `AuditStatsTab.tsx` | 平台审计                                                                                                        |
| `auditMappers.ts`                        | 审计 API 响应映射                                                                                               |
| `shared.tsx`                             | SeverityBadge、MetricCard                                                                                       |
| `types.ts`                               | 前端类型                                                                                                        |

## 依赖

- `myrm-agent-frontend/src/app/security/page.tsx`
- Server `/api/v1/security/*`
