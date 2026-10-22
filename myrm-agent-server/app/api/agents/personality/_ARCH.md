# api/agents/personality/ 模块架构

## 架构概述

通信风格目录 HTTP 层：把 `ai_agents/personality_templates.py` 的预置风格序列化给前端。
上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包门面：聚合沟通风格路由，挂载在 `/agents` 前缀下 | ✅ |
| `catalog.py` | 核心 | 只读目录端点 `GET /agents/personalities`：返回 17 个预置风格的中英双语名称/描述/示例回复、GUI 图标标识与分类；序列化时排除 `system_prompt_suffix` 与 `emoji`，提示词内部文本不出服务端 | ✅ |

## 依赖

- [../_ARCH.md](../_ARCH.md)
- `app.ai_agents.personality_templates` — 目录唯一事实源
