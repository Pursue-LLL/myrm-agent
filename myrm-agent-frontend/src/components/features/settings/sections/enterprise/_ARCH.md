# settings/sections/enterprise/ 模块架构

## 架构概述

SaaS / sandbox 部署下的 Enterprise Org 管理 Section（`SettingsMenu` 中 `group: system`、`sandboxOnly: true`）。单机 OSS 构建不展示此 Tab。

`EnterpriseOrgSection` 作为入口 Tab 容器，通过 `React.lazy` 按需加载子 Tab 组件以保持代码体积合理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `EnterpriseOrgSection.tsx` | 核心入口 | 轻量 Tab 容器，lazy 加载三个子 Tab | ✅ |
| `EnterpriseMembersTab.tsx` | 子 Tab | 组织信息、成员 CRUD、离职交接、Volume 转移；org owner/admin 可见 Org MCP 面板 | ✅ |
| `EnterpriseAuditTab.tsx` | 子 Tab | 安全审计大盘：KPI 卡片、时间线图表、事件列表、导出 | ✅ |
| `EnterpriseUsageTab.tsx` | 子 Tab | 成本报表：月度用量进度、成员排行、分类分布、预算设置 | ✅ |
| `OrgMcpAdminPanel.tsx` | 子模块 | Org 级 MCP 列表与 CRUD 编排 | ✅ |
| `OrgMcpAdminDialogs.tsx` | 子模块 | Create/Edit/Delete 对话框 | ✅ |
| `OrgMcpServerFormFields.tsx` | 子模块 | MCP 表单字段（create/edit 共用） | ✅ |
| `orgMcpAdminUtils.ts` | 工具 | delivery toast 辅助 | ✅ |
| `orgMcpAccess.ts` | 工具 | `canManageOrgMcp` — 前端 RBAC，与 CP `require_admin` 对齐 | ✅ |

## Tab 结构

```
EnterpriseOrgSection (Tab 容器, 58 行)
├── Members Tab (lazy) — EnterpriseMembersTab
├── Cost & Usage Tab (lazy) — EnterpriseUsageTab
└── Audit Logs Tab (lazy) — EnterpriseAuditTab
```

## 依赖

- `@/services/enterprise-org` — Org API 客户端（成员、离职）
- `@/services/enterprise-admin` — Audit + Usage API 客户端（安全审计、用量查询、预算）
- [`../SettingsSection.tsx`](../SettingsSection.tsx) — Section 容器
- `recharts` — 数据可视化图表
- 父模块 [`../_ARCH.md`](../_ARCH.md)
