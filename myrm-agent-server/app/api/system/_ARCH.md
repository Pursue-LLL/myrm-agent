# app/api/system 模块架构

系统级 HTTP 端点（公网 ingress 解析、优雅停机、统一工具网关状态代理等）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `router.py` | ✅ 核心 | GET `/ingress-url`；POST `/gateway/health`；GET/POST `/tunnel/*` Quick Tunnel 控制 | ✅ |
| `shutdown.py` | ✅ 核心 | POST `/shutdown` 优雅停机 | ✅ |
