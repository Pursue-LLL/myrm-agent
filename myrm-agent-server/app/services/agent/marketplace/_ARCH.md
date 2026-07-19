# marketplace 模块

## 架构概述

Agent Marketplace 导入/导出与包契约 SSOT。跨沙箱分发 Agent 配置 + bundled Skills/MCP/Subagents。

上级文档：[../_ARCH.md](../_ARCH.md)。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `package_contract.py` | 核心 | 包类型/版本/trust 契约 + 完整性校验 + transport HMAC | ✅ |
| `export.py` | 核心 | `export_agent_package` — 剥离敏感字段、打包依赖 | ✅ |
| `import_.py` | 核心 | `import_agent_package` — 契约门 + 原子回滚安装 | ✅ |
| `__init__.py` | 门面 | 对外 re-export 公共 API | ✅ |

---

## 依赖关系

- `app/services/agent/profile_snapshot_service.py` — Agent 字段序列化
- `app/core/skills/` — Skill 读写
- `app/services/agent/agent_service.py` — Agent CRUD
- `app/api/agents/agent.py` — WebUI marketplace export/import 端点
