# utils/url_utils/

## 架构概述

URL 解析与 SSRF 原语：解析、黑名单、安全校验与 DNS pin 分层，`__init__.py` 是唯一入口。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合导出全部 URL 工具 |
| `parsing.py` | 规范化、域名提取、图片/文件 URL 判断 |
| `blocking.py` | SSRF 黑名单、动态主机名注册、IP 拦截 |
| `security.py` | scheme/主机校验、外泄检测、错误脱敏 |
| `dns.py` | DNS pin 映射与解析规则 |
