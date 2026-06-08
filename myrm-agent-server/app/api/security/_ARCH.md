# api/security/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 见源码 | — |
| `allowlist.py` | 模块 | 见源码 | — |
| `dashboard_models.py` | 模块 | 见源码 | — |
| `generate.py` | 模块 | Business-layer bridge between frontend NL input and harness-level policy generation | ✅ |
| `profiles.py` | 模块 | REST API layer for security profile management | ✅ |
| `router.py` | 路由 | 见源码 | — |
| `schemas.py` | 模块 | 见源码 | — |
| `vault.py` | 模块 | 金库解锁 API 路由。供无凭证环境（Local/Docker）的终端用户安全输入密码派生主密钥。 | ✅ |
| `vault_credentials.py` | 模块 | 见源码 | — |
