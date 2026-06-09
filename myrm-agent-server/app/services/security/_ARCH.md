# services/security/

## 架构概述

安全策略与审计相关业务服务。详见 [../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `cp_security_dashboard.py` | 核心 | Sandbox 部署时从 Control Plane internal API 拉供应链仪表盘 | ✅ |
| `cp_rate_limit.py` | 核心 | Sandbox 部署时从 Control Plane internal API 拉平台 rate limit | ✅ |
| `merged_dashboard.py` | 核心 | CP 告警 + GitHub PR/SBOM 合并；setup-hints | ✅ |
| `platform_audit.py` | 核心 | `/security/audit/*`：sandbox→CP internal，local→auth JSONL | ✅ |
| `github_supplement.py` | 核心 | 多仓库 Dependabot PR / SBOM 拉取 | ✅ |
| `github_full.py` | 核心 | Local 全量 GitHub 仪表盘（支持多仓 PR 补充） | ✅ |
| `dashboard_settings.py` | 核心 | Omni-Config `securityDashboardSettings` 读取 | ✅ |
