# utils/url_utils/

## 架构概述

URL 解析与 SSRF 原语：解析、黑名单、安全校验与 DNS pin 分层，`__init__.py` 是唯一入口。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出全部 URL 工具 | ✅ |
| `parsing.py` | 核心 | 去重键（`url_dedup_key`，折叠主机与路径的大小写（查询串只解码，不转小写）、`www.`、尾斜杠（站点根路径统一为 `/`）、片段、百分号写法，只用于比较；`keep_fragment=True` 时片段只解码、区分大小写，计入键）、展示 URL（`readable_url`，只把可打印的非 ASCII 百分号编码还原成字符，其余字节不动）、域名提取、图片/文件 URL 判断 | ✅ |
| `blocking.py` | 核心 | SSRF 黑名单、动态主机名注册、IP 拦截 | ✅ |
| `security.py` | 核心 | scheme/主机校验、外泄检测（白名单按规范化 URL 实际拨号的主机匹配，`@` 之前的凭据段不算主机）、错误与日志脱敏（`sanitize_url_for_error` 只显示 scheme、主机与路径：凭据、查询串、片段不显示；无 `//` 的不透明 URL（`blob:`、`data:`、`filesystem:`）只显示 scheme；不是 URL 的文本显示固定占位；永不抛异常） | ✅ |

## 依赖关系

- `security.py` → `blocking.py`
