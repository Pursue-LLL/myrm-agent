# builtin_specs 模块

## 架构概述

预置智能体规格数据（纯数据层）。对外聚合门面在根目录 `../builtin_agent_specs.py`；初始化逻辑在 `../builtin_initializer.py`。

上级文档：[../_ARCH.md](../_ARCH.md)。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.py` | 核心 | `_BuiltInAgentSpec` dataclass + `_TOOL_*` 工具集常量 SSOT（含 `_TOOL_COWORK` = default + kanban） | ✅ |
| `core.py` | 核心 | 核心预置智能体规格（`_CORE_BUILTIN_AGENTS`）；`builtin-economy` = Knowledge Work Cowork preset（`KNOWLEDGE_WORK_SYSTEM_PROMPT`） | ✅ |
| `search.py` | 核心 | Web 搜索预置智能体（`prompt_mode=search`）；Web UI  persona，非 Channel 绑定目标 | ✅ |
| `extended.py` | 核心 | 扩展预置智能体规格（`_EXTENDED_BUILTIN_AGENTS`） | ✅ |
| `vertical.py` | 核心 | 垂直领域预置智能体规格（`_VERTICAL_BUILTIN_AGENTS`）；含 **`builtin-ko-office`**（`response_locale_policy` 正式韩语） | ✅ |
| `__init__.py` | 辅助 | 子包标识；公共 API 由根门面 re-export | ✅ |

---

## 依赖关系

- `app/services/agent/builtin_tool_ids.py` — `DEFAULT_ENABLED_BUILTIN_TOOLS`
- `app/ai_agents/prompts/deliverable_discipline.py` — `KNOWLEDGE_WORK_SYSTEM_PROMPT`
- `app/services/agent/builtin_agent_specs.py` — 聚合 `_BUILTIN_AGENTS` 并 re-export 类型/常量
- `app/services/agent/builtin_initializer.py` — lifespan Phase 1b 幂等写入 DB
