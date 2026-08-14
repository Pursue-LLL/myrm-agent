# services/connect/

## 架构概述

外部 AI Agent（Claude Code、Cursor、Windsurf 等）连接向导：生成 MCP 配置片段、API token、健康检查与连接档案管理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `service.py` | 核心 | `ConnectService`：连接档案、token 签发（携带 agent_id 作用域）、ingress URL 解析、resolve_token 返回 VerifiedConnectToken(profile_id, agent_id)、健康检查与 Agent Plugins bundle 生成 | ✅ |
| `snippet_builder.py` | 纯函数 | 各工具 MCP 配置片段（JSON/TOML）与向导文案构建 | — |
| `agent_plugin.py` | 纯函数 | Agent Plugins 1.0.0 便携 bundle（plugin.json/mcp.json/SKILL.md）模板渲染 | — |

## 依赖

- `app.core.infra.ingress` — 公网 ingress 基址
- `app.config.settings` — 应用配置

## 测试契约

- Agent Plugins 官方 schema 冻结于 `tests/fixtures/agent_plugins/`（plugin.schema.json / mcp.schema.json），`test_agent_plugin_bundle.py` 用 `jsonschema.validate()` 全量校验 bundle 产物，防止模板改动破坏规范合规性。
