# api/companion/

## 架构概述

Companion 伴随模式 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `router.py` | 路由 | Companion API 端点。Observer 生成宠物反应，Evolution 查询用户活跃度指标和进化资格。 | ✅ |
