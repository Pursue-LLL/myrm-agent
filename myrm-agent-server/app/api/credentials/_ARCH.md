# api/credentials/

## 架构概述

工作区 `.credentials/` 凭证文件的 HTTP 层：列出文件（含到期状态）与按相对路径删除，拒绝绝对路径与 `..`。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Credentials API endpoints. | ✅ |
| `router.py` | 路由 | Credentials management API router: list and delete credential files. | ✅ |
