# core/security/share/

## 架构概述

分享（share）安全域：无状态分享令牌的签名与校验、分享页面/解锁/状态页的鉴权访问控制。从 `app/core/security/` 平铺模块拆分而来。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出，保持外部 import 稳定 | ✅ |
| `share_hmac.py` | 模块 | 无状态分享令牌 HMAC 签名原语（签发/校验/防篡改） | ✅ |
| `share_headers.py` | 模块 | 分享请求头解析与校验（访问令牌、渠道标识） | ✅ |
| `share_unlock.py` | 模块 | 分享解锁鉴权（密码/令牌校验入口） | ✅ |
| `share_password_page.py` | 模块 | 密码分享页服务端渲染与提交处理 | ✅ |
| `share_status_page.py` | 模块 | 分享状态页（生效/失效展示） | ✅ |
