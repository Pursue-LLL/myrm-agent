# api/workspace/

## 架构概述

工作区策略与路径 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `router.py` | 路由 | Subscribe to the multiplexed workspace stream. | ✅ |
| `rules.py` | 模块 | Workspace 规则自省 HTTP 层，供 Settings WorkspaceRulesSection 展示 | ✅ |
