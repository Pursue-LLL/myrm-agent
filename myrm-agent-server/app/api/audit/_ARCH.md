# api/audit/

## 架构概述

Bash 命令与 WebUI 认证审计 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Audit API module | ✅ |
| `alert_notifier.py` | 模块 | Bash 审计异常告警通知（webhook/Slack/email） | — |
| `anomaly_detector.py` | 模块 | Bash命令异常检测 | ✅ |
| `auth_router.py` | 模块 | Auth audit query API. | ✅ |
| `bash_router.py` | 模块 | Bash审计日志REST API | ✅ |
