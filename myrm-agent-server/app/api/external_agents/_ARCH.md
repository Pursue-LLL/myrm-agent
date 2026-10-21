# api/external_agents/

## 架构概述

外部 Agent 连接档案 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | External delegated agent auth endpoints. | ✅ |
| `router.py` | 路由 | 外部 Agent 订阅鉴权 HTTP API。`/auth/status` 强制 fresh detect（`refresh=True`）返回各 backend 安装/登录态（Settings badge），并回填进程级探测缓存鲜度；不含 ephemeral RuntimePool health metrics。 | ✅ |
