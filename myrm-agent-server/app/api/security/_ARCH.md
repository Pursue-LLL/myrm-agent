# api/security 模块架构


## 架构概述

安全管理 API。提供工具调用白名单、安全仪表盘、密钥保管库接口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包初始化 | — |
| `allowlist.py` | 核心 | 工具调用白名单 CRUD | ⚠️ 待补 |
| `generate.py` | 核心 | NL → SecurityConfig 生成 API（POST /security/generate-policy） | ✅ |
| `profiles.py` | 核心 | 安全配置 Profile CRUD（list/get/create/update/delete/clone/activate） | ✅ |
| `router.py` | 核心 | `/dashboard` `/setup-hints` `/rate-limits` `/audit/*` | ✅ |
| `dashboard_models.py` | 核心 | 仪表盘 / setup / rate-limit Pydantic（camelCase） | ✅ |
| `schemas.py` | 核心 | Profile API Pydantic 模型（ProfileResponse/ProfileCreateRequest/ProfileCloneRequest） | ✅ |
| `vault.py` | 核心 | 密钥保管库（加密存储、访问控制） | ⚠️ 待补 |
