# services/integrations/tools/

## 架构概述

Skill-gated integration tool factories. Credentials come from session context, not static config.

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `x_live_search.py` | 模块 | x-live-search prebuilt skill LangChain tool factory (xAI credentials via SessionCredentialAssembler) | ✅ |
