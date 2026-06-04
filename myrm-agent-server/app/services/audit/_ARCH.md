# services/audit/

## 概述

平台与认证审计日志读取（JSONL），供 Security Center 与 admin API 复用。

## 文件

| 文件 | 职责 |
|------|------|
| `auth_log_reader.py` | 读取本地 `auth_audit.jsonl`，序列化为 API 事件字典 |

## 依赖

- `app/services/security/platform_audit.py` — sandbox 走 CP internal，local 走本模块
