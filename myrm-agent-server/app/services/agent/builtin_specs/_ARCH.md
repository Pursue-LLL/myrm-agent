# builtin_specs 模块

## 架构概述

预置智能体规格与 builtin 工具域：规格数据（纯数据层）+ 工具 ID SSOT + DTO validators + 自动初始化。对外聚合门面在根目录 `../builtin_agent_specs.py`。

上级文档：[../_ARCH.md](../_ARCH.md)。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.py` | 核心 | `_BuiltInAgentSpec` dataclass（含 `max_iterations` 轮数语义字段）+ `_TOOL_*` 工具集常量 SSOT（含 `_TOOL_COWORK` = default + kanban） | ✅ |
| `core.py` | 核心 | 核心预置智能体规格（`_CORE_BUILTIN_AGENTS`）；`builtin-economy` = Knowledge Work Cowork preset（`KNOWLEDGE_WORK_SYSTEM_PROMPT`） | ✅ |
| `search.py` | 核心 | Web 搜索预置智能体（`prompt_mode=search`，`max_iterations=30/50` 轮数预算）；Web UI  persona，非 Channel 绑定目标 | ✅ |
| `extended.py` | 核心 | 扩展预置智能体规格（`_EXTENDED_BUILTIN_AGENTS`） | ✅ |
| `vertical.py` | 核心 | 垂直领域预置智能体规格（`_VERTICAL_BUILTIN_AGENTS`）；含 **`builtin-ko-office`**（`response_locale_policy` 正式韩语） | ✅ |
| `builtin_tool_ids.py` | 核心 | `enabled_builtin_tools` SSOT：19 canonical IDs（17 UI 可切换 + 2 Agent 基线无开关）；含 `skill_market` / `skill_manage`（默认 OFF，Turn1 条件挂载）；`strip_deploy_incompatible_builtin_tools()` 按 deploy 剔除 `computer_use`（VNC）与 `external_cli`（仅 local/Tauri）；`normalize` 静默剥离 baseline ID；`persist_enabled_builtin_tools` DB 写校验 | ✅ |
| `builtin_tool_validation.py` | 辅助 | Pydantic `RequiredBuiltinTools` / `OptionalBuiltinTools` validators for DTO/API models | ✅ |
| `builtin_initializer.py` | 核心 | Built-in Agent 自动初始化 — lifespan Phase 1b 幂等创建 27 个预置智能体（从 `builtin_agent_specs` 导入规格）；sync spec-controlled 字段含 `memory_extraction_preset` 与 `max_iterations`；`suggestion_prompts` 仅在 DB 值为空时填充（保护用户自定义）；re-export `_BUILTIN_AGENTS`/`_TOOL_*` 保持外部导入兼容 | ✅ |
| `__init__.py` | 辅助 | 子包标识；公共 API 由根门面 re-export | ✅ |

---

## 依赖关系

- 本目录 `builtin_tool_ids.py` — `DEFAULT_ENABLED_BUILTIN_TOOLS`
- `app/ai_agents/prompts/deliverable_discipline.py` — `KNOWLEDGE_WORK_SYSTEM_PROMPT`
- `app/services/agent/builtin_agent_specs.py` — 聚合 `_BUILTIN_AGENTS` 并 re-export 类型/常量
