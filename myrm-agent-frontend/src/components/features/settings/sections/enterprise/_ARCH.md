# settings/sections/enterprise/ 模块架构

## 架构概述

SaaS / sandbox 部署下的 Enterprise Org 管理 Section（`SettingsMenu` 中 `group: system`、`sandboxOnly: true`）。单机 OSS 构建不展示此 Tab。

`EnterpriseOrgSection` 作为入口 Tab 容器，通过 `React.lazy` 按需加载子 Tab 组件以保持代码体积合理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `EnterpriseOrgSection.tsx` | 核心入口 | Tab 容器，lazy 加载六个子 Tab；nav 支持 `overflow-x-auto` 移动端横滑 | ✅ |
| `EnterpriseMembersTab.tsx` | 子 Tab | 组织信息、成员列表、离职交接、Volume 转移；全部管理操作（Add/Remove/Offboard/Transfer/Unlink）按 `isOrgAdmin` 门控，非 admin 仅只读；角色徽标本地化；Transfer source 仅列**已归档（offboard completed）成员**，防止 409 报错 | ✅ |
| `EnterpriseMembersDialogs.tsx` | 子模块 | AddMember（shadcn Select 角色选择）/ UnlinkOauth / RemoveMember 确认对话框；RemoveMember 明示将撤销组织工具与治理策略（MCP/审批策略/模型白名单）访问 + IdP 权威语义提示（SSO 自动准入可能重新加回，永久撤销需在 IdP 侧移除） | ✅ |
| `EnterpriseHandoffDialogs.tsx` | 子模块 | Offboard / Transfer 对话框（shadcn Select 成员下拉，避免手输 user_id；source 非 owner 且需已归档、target 全员、自转禁用） | ✅ |
| `EnterpriseSsoTab.tsx` | 子 Tab | Org OIDC SSO 配置 CRUD（issuer/client_id/secret 留空保留、auto-provision、group 白名单、enabled）；组织登录链接展示与复制；按 org `sso_domain` 与组白名单状态动态展示 auto-provision 准入范围提示；owner/admin 可见 | ✅ |
| `EnterpriseModelPolicyTab.tsx` | 子 Tab | Org 模型白名单 CRUD（fnmatch pattern 列表）；`orgId` 经 `getMyOrg()` 获取；add/remove 后 fanout 部分失败 warning toast | ✅ |
| `EnterpriseApprovalPolicyTab.tsx` | 子 Tab | Org Managed Approval Policy CRUD（ignore allowlist / force auto-review patterns + YOLO / allow-always 开关）；`orgId` 经 `getMyOrg()` 获取 | ✅ |
| `EnterpriseAuditTab.tsx` | 子 Tab | 审计大盘（Tabs 容器）：`platform` 平台审计（KPI 卡片、时间线图表、事件列表、导出）+ `agent` Agent 行为审计（`AgentAuditView`） | ✅ |
| `AgentAuditView.tsx` | 子模块 | 组织级 Agent 行为审计视图：消费 CP `/api/enterprise/org/{org_id}/agent-audit/events` 聚合事件；KPI（总事件/工具调用/安全事件/扫描沙箱数）、failed_sandboxes 告警条、事件流编排、时间范围选择（24h/7d/30d） | ✅ |
| `AgentEventRow.tsx` | 子模块 | Agent 审计事件行（含 tone 分类徽标、tool_name/事件类型标题、security decisions 详情、展开 JSON 明细）；消费 CP 注入的 `user_id`/`sandbox_id` 归属 → 渲染成员徽标（短码 + tooltip 完整值）；导出 `eventKey`（sandbox_id 前缀防跨沙箱 key 碰撞）与 `AgentEventRow` | ✅ |
| `EnterpriseUsageTab.tsx` | 子 Tab | 成本报表：月度用量进度、成员排行、分类分布、预算设置 | ✅ |
| `OrgMcpAdminPanel.tsx` | 子模块 | Org 级 MCP 列表与 CRUD 编排 | ✅ |
| `OrgMcpAdminDialogs.tsx` | 子模块 | Create/Edit/Delete 对话框 | ✅ |
| `OrgMcpServerFormFields.tsx` | 子模块 | MCP 表单字段（create/edit 共用） | ✅ |
| `orgMcpAdminUtils.ts` | 工具 | delivery toast 辅助 | ✅ |
| `orgMcpAccess.ts` | 工具 | `canManageOrgMcp` — 前端 RBAC，与 CP `require_admin` 对齐 | ✅ |
| `TunnelAdminPanel.tsx` | 子模块 | MCP Private Tunnel 列表、注册、删除、token 轮换；degraded 时展示 `last_upstream_error` 与 `last_error_at` | ✅ |

## Tab 结构

```
EnterpriseOrgSection (Tab 容器)
├── Members Tab (lazy) — EnterpriseMembersTab
├── SSO Tab (lazy) — EnterpriseSsoTab
├── Model Policy Tab (lazy) — EnterpriseModelPolicyTab
├── Approval Policy Tab (lazy) — EnterpriseApprovalPolicyTab
├── Cost & Usage Tab (lazy) — EnterpriseUsageTab
└── Audit Logs Tab (lazy) — EnterpriseAuditTab
```

## 依赖

- `@/services/enterprise-org` — Org API 客户端（成员、离职、MCP、Tunnel、模型/审批策略）；直连 CP 走 `resolveCpBaseUrl` + `getAuthHeaders`
- `@/services/enterprise-admin` — Audit + Usage API 客户端（安全审计、Agent 行为审计、用量查询、预算）
- `@/lib/cp-base-url` — `resolveCpBaseUrl` CP Base URL（部署模式感知）
- `@/lib/utils/authHeaders` — Bearer 认证头（直连 CP 必需）
- [`../SettingsSection.tsx`](../SettingsSection.tsx) — Section 容器
- `recharts` — 数据可视化图表
- 父模块 [`../_ARCH.md`](../_ARCH.md)
