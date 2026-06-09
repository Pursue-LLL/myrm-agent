# services/connect/

## 架构概述

外部 AI Agent（Claude Code、Cursor、Windsurf 等）连接向导：生成 MCP 配置片段、API token、健康检查与连接档案管理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `service.py` | 核心 | `ConnectService`：连接档案、token 签发、ingress URL 解析与健康检查 | ✅ |

## 依赖

- `app.core.infra.ingress` — 公网 ingress 基址
- `app.config.settings` — 应用配置
