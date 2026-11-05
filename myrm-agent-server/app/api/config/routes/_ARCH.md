# api/config/routes/

## 架构概述

配置 API 的域路由：每个文件负责一类配置端点，`router.py` 是唯一组合根；`support.py` 放跨域共享的锁、超时与写入前校验。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 子包标记 | — |
| `support.py` | 支撑 | 就绪超时、Second Brain 文件锁、`_VALID_CONFIG_KEYS`、写入校验、浏览器/代理热重载 | ✅ |
| `catalog.py` | 路由 | `GET /schema/{key}`、`GET /readiness` | ✅ |
| `onboarding.py` | 路由 | 引导完成、Second Brain 状态/应用、SearXNG 启停与探测 | ✅ |
| `media_health.py` | 路由 | `POST /vision-health`、`POST /video-health` | ✅ |
| `crud.py` | 路由 | `GET/PUT/DELETE /{config_key}`、历史、回滚、批量同步 | ✅ |
| `diagnostics.py` | 路由 | `POST /test-local-model`、`POST /test-proxy` | ✅ |
