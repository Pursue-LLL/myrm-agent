# api/companion/

## 架构概述

Companion 伴随模式 HTTP 层：Observer 反应、Evolution 指标、Companion 配置、Petdex 安装/list/serve/uninstall。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `router.py` | 路由 | Companion API 端点。Observer 反应、Evolution 指标、Companion 配置、Petdex 安装/list/serve/uninstall（DELETE 同步清匹配 sprite config）。 | ✅ |
