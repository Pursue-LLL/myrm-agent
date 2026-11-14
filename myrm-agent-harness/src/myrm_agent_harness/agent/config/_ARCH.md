# config/

## Overview
Agent configuration package — unified export of all config types and utilities.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Agent configuration package — unified export of all config types and utilities. | — |
| exceptions.py | Core | Framework-level exception definitions. Business layer can inherit these | ✅ |
| file_io.py | Core | File I/O configuration. Defines resource limits (concurrent reads, file size caps), compiler-grade read output caps (max_chars/max_lines/max_line_length), regex safety (Re | ✅ |
| llm.py | Core | Agent configuration layer. Re-exports CustomModelDef/LLMConfig from core.config.llm (SSoT) and defines agent-specific AgentConfig, TracingConfig. | ✅ |
| llm_safety.py | Core | Provider safety normalization for LLM calls made outside the middleware chain (summary prefix, grace call). `normalize_messages()` is the production pair `sanitize_tool_history()` → `repair_dangling_tool_calls()`; a well-formed history is returned unchanged. | ✅ |
| provider_routing.py | Core | 供应商路由表、前缀规则 `route_prefix_for_effective`（路由表声明的每个供应商都必须得到它声明的路由段，由 `tests/agent/config/test_provider_routing.py` 逐项校验）、`normalize_env_model_selection_string`（含 `openai-like`、`siliconflow`、`opencode-go` 等别名）、前端常量生成数据源 | ✅ |
| parsers.py | Core | `to_route_model_id` 组合 provider_routing 前缀规则 | ✅ |
| presets.py | Core | Configuration presets layer. Provides best-practice configuration presets for common scenarios. | ✅ |
| readiness.py | Core | Framework-level readiness check infrastructure. Business layer inherits to implement | ✅ |
| validator.py | Core | Configuration validation layer. Checks config validity, consistency, and security, producing structu | ✅ |

## Key Dependencies

- `core.config` (CustomModelDef, LLMConfig — Single Source of Truth)
- `agent.middlewares.tooling` (`llm_safety` loads the production tool-pairing functions lazily: the middleware package imports this package's consumers, so a module-level import would be circular)
- `backends`
- `toolkits`
- `utils`
