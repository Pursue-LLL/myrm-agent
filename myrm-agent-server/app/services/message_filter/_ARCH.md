# services/message_filter/

## 架构概述

消息过滤配置与审计服务。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Message filter services. | ✅ |
| `audit_service.py` | 模块 | Audit service for message filtering events. | ✅ |
| `config_manager.py` | 模块 | Database-backed ConfigManager for hot-reloading filter configurations. | ✅ |
| `config_version_service.py` | 模块 | Configuration version control service for message filtering. | ✅ |
