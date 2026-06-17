# api/a2a/ 模块架构

## 架构概述

A2A（Agent-to-Agent）发现入口：对外暴露 `/.well-known/agent-card.json`，供外部 Agent 按 A2A 规范拉取 AgentCard。由 `A2A_DISCOVERY_ENABLED` 或 sandbox 部署模式控制开关。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 入口 | 包导出 | — |
| `well_known.py` | 路由 | AgentCard GET/OPTIONS + CORS | ✅ |

## 模块依赖

- `app.config.settings` — 应用名称与版本
- `app.config.deploy_mode` — sandbox 默认启用发现
- `app.services.agent.agent_service` — 默认 Agent 与 skills
- `myrm_agent_harness.toolkits.a2a.types` — AgentCard 模型
