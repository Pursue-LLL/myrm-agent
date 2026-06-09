# api/message_filter/

## 架构概述

消息过滤规则与版本审计 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Message filter API endpoints. | ✅ |
| `audit.py` | 模块 | Message filter audit API endpoints. | ✅ |
| `config.py` | 模块 | Message filter configuration API endpoints. | ✅ |
| `rules.py` | 模块 | Message filter rules API endpoints. | ✅ |
| `templates.py` | 模块 | Message filter rule templates API endpoints. | ✅ |
| `version.py` | 模块 | Message filter version history API endpoints. | ✅ |
