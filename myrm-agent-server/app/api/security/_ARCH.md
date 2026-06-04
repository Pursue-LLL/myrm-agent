# api/security 模块架构

## 架构概述

本包包含两个域，共用 `/api/v1/security` 前缀：

1. **Agent 工具安全** — 白名单、NL 策略生成、Profile、密钥保管库（`allowlist.py` / `generate.py` / `profiles.py` / `vault.py`）
2. **GitHub Security Center** — 仪表盘、CP 聚合、平台审计（`router.py` / `dashboard_models.py`）

## 文件清单

| 文件 | 域 | 职责 | I/O/P |
|------|-----|------|-------|
| `__init__.py` | — | 包初始化 | — |
| `allowlist.py` | Agent | 工具调用白名单 CRUD | ⚠️ 待补 |
| `generate.py` | Agent | NL → SecurityConfig（POST /security/generate-policy） | ✅ |
| `profiles.py` | Agent | 安全配置 Profile CRUD | ✅ |
| `router.py` | Security Center | `/dashboard` `/setup-hints` `/rate-limits` `/audit/*` | ✅ |
| `dashboard_models.py` | Security Center | 仪表盘 / setup / audit Pydantic（camelCase） | ✅ |
| `schemas.py` | Agent | Profile API Pydantic 模型 | ✅ |
| `vault.py` | Agent | 密钥保管库 | ⚠️ 待补 |
