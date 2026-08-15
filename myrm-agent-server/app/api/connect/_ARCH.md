# api/connect/ 模块架构

## 架构概述

Connect Wizard HTTP 入口：外部 AI Agent（Claude Code、Cursor 等）连接记忆 MCP 的配置生成、token 签发与健康检查。业务逻辑见 [services/connect/_ARCH.md](../../services/connect/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `router.py` | 路由 | Connect Wizard REST 端点；`DoctorResponse` 含 `detail`（机器可读健康明细码，前端做 i18n 映射）；`ConnectorStatusResponse` 含 `doctor_ok`/`last_doctor_at`（上次检查时间） | ✅ |

## 模块依赖

- `app.services.connect.service` — `ConnectService`
