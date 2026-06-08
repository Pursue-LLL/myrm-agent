# channels/providers/msteams/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `api.py` | 模块 | Bot Framework HTTP layer. Wraps OAuth token management, serviceUrl caching, activity POST/PUT/DELETE, providing low-level API capabilities for MSTeamsChannel. " | ✅ |
| `auth.py` | 模块 | app.channels.providers.msteams.auth — Bot Framework JWT validator. Fetches public keys via OpenID Connect metadata, verifies JWT signature, issuer, audience, an | ✅ |
| `channel.py` | 模块 | MSTeams Bot channel implementation. Supports message edit/delete, Adaptive Card interactive components, file attachments, typing indicator, and placeholder stre | ✅ |
| `helpers.py` | 模块 | Stateless helpers extracted from MSTeamsChannel to keep channel.py focused on the Channel lifecycle and I/O. """ | ✅ |
| `models.py` | 模块 | Pydantic models for Microsoft Bot Framework activity payloads. """ | ✅ |
