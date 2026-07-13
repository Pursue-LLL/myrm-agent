# api/security/ 模块架构

## 架构概述

Security Center 与 Agent 工具安全策略的 HTTP 层：供应链仪表盘、平台审计、紧急停止、安全 Profile CRUD、NL 策略生成、Vault 解锁与凭据 CRUD。合并逻辑与 CP 拉取见 [services/security/_ARCH.md](../../services/security/_ARCH.md)；WebUI 入口 `/security`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `profiles_router` | — |
| `router.py` | 路由 | 仪表盘、setup-hints、rate-limits、alerts、audit、dependabot-prs | ✅ |
| `estop.py` | 路由 | `POST/GET /security/estop`：全局工具冻结 + activate 时 `CancellationRegistry.cancel_all`；状态 `{MYRM_DATA_DIR or ~/.myrm}/.estop_state.json` | ✅ |
| `generate.py` | 路由 | `POST /security/generate-policy`：NL → SecurityConfig | ✅ |
| `profiles.py` | 路由 | `/security/profiles` CRUD、clone、activate | ✅ |
| `schemas.py` | 模块 | Profile API schema | — |
| `allowlist.py` | 路由 | `/security/allowlist` 工具 allowlist 查询与删除 | ✅ |
| `vault.py` | 路由 | `POST /security/vault/unlock`：本地主密钥派生 | ✅ |
| `vault_credentials.py` | 路由 | `/security/vault-credentials` CRUD | ✅ |

## 路由（前缀 `/api/v1`）

### 仪表盘（`router.py`，`/security`）

| 方法 | 路径 | 职责 |
|------|------|------|
| GET | `/security/dashboard` | local：GitHub；sandbox：CP 告警 + 可选 GitHub PR/SBOM 合并 |
| GET | `/security/setup-hints` | SaaS webhook 与 env 配置提示 |
| GET | `/security/rate-limits` | sandbox：Control Plane 平台限流 |
| GET | `/security/alerts` | 按 severity/state 过滤近期告警 |
| GET | `/security/audit/logs` | sandbox→CP internal；local→auth JSONL |
| GET | `/security/audit/stats` | 审计统计聚合 |
| GET | `/security/audit/export` | CSV/JSON 导出 |
| GET | `/security/dependabot-prs` | 监控仓库 Dependabot PR（Omni-Config ≤3 仓） |

### 工具策略与 Vault

| 模块 | 路径 | 职责 |
|------|------|------|
| `estop.py` | `/security/estop` | 激活/解除全局 E-Stop |
| `generate.py` | `/security/generate-policy` | 自然语言生成安全策略 JSON |
| `profiles.py` | `/security/profiles` | 命名安全 Profile 列表/CRUD/clone/activate |
| `allowlist.py` | `/security/allowlist` | Agent 工具 allowlist 管理 |
| `vault.py` | `/security/vault/unlock` | 无预置密钥环境下的 Vault 解锁 |
| `vault_credentials.py` | `/security/vault-credentials` | Vault 标签凭据 CRUD |

## 模块依赖

- `app.services.security.merged_dashboard` — 仪表盘合并
- `app.services.security.platform_audit` — 审计读写
- `app.services.security.cp_rate_limit` — sandbox 限流
- `app.services.security.dashboard_settings` — `securityDashboardSettings.monitoredGithubRepos`
- `app.services.security.profile_manager` — Profile CRUD
- `myrm_agent_harness.agent.security` — E-Stop、NL policy generator
