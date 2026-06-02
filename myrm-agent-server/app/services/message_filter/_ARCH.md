# services/message_filter 模块架构


## 架构概述

消息过滤服务层。提供过滤规则配置管理、版本控制和审计日志。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `config_manager.py` | 核心 | 过滤规则配置管理 | ⚠️ 待补 |
| `config_version_service.py` | 核心 | 配置版本控制服务 | ⚠️ 待补 |
| `audit_service.py` | 辅助 | 审计日志服务 | ⚠️ 待补 |
