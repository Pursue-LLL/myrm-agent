# api/web_push/

## 架构概述

Web Push (VAPID) 订阅管理与推送测试 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `router.py` | 路由 | Web Push REST 接口层。提供 VAPID 公钥获取、订阅注册/注销、测试推送发送。 | ✅ |
| `schemas.py` | 模块 | Pydantic 请求/响应模型。订阅字段强制 min_length=1 校验。 | — |
