# api/external_agents/

## 架构概述

外部 CLI Agent（Codex / Claude Code 等）订阅鉴权 HTTP 层：安装状态、SSE 交互式登录、凭据导入/登出。local + SaaS 全模式注册。

上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `router.py` | 路由 | `/external-agents/auth/*` 与 `/install/{backend}` SSE | ✅ |
