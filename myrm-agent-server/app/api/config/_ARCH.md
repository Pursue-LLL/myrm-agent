# api/config/

## 架构概述

Omni-Config 读写与预检 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 配置管理 API | ✅ |
| `artifact_mappings.py` | 模块 | 工件类型映射 API 端点 | ✅ |
| `router.py` | 路由 | 配置服务 API 路由层。处理 HTTP 请求，进行 Pre-flight Validation 强类型校验。 | ✅ |
