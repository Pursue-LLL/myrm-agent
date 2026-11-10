# core/config/

## Overview
Framework-agnostic configuration types. Provides LLMConfig, CustomModelDef, ToolGatewayConfig, and wire protocol identifiers used by both agent/ and toolkits/ without coupling.

## File & Submodule Index

| File | Role | Description |
|------|------|-------------|
| __init__.py | Package | Re-exports CustomModelDef, LLMConfig, ToolGatewayConfig. |
| llm.py | Core | CustomModelDef (dataclass) and LLMConfig (Pydantic BaseModel with from_env classmethod). |
| gateway.py | Core | ToolGatewayConfig for external tool gateway connection settings. |
| wire.py | Core | Wire protocol identifiers (`chat_completions`, `responses`, `anthropic_messages`) for LLM HTTP transports. |

## Key Dependencies

- No internal dependencies (foundation layer)
