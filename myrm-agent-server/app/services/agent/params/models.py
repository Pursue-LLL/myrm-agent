from __future__ import annotations

import logging
from typing import Literal

from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from pydantic import BaseModel, Field, field_validator
from pydantic.alias_generators import to_camel

from app.services.agent.builtin_tool_ids import DEFAULT_ENABLED_BUILTIN_TOOLS
from app.services.agent.builtin_tool_validation import RequiredBuiltinTools

MultimodalQuery = str | list[dict[str, object]]

logger = logging.getLogger(__name__)


class ModelSelection(BaseModel):
    """Frontend model selection — no API Key, only the choice."""

    provider_id: str
    model: str
    base_url: str | None = None
    model_kwargs: dict[str, object] | None = None
    credential_pool_strategy: str | None = None
    supports_vision: bool | None = Field(
        default=None,
        description="Whether the model supports image input (from frontend customModelInfo)",
    )
    fallback_provider_id: str | None = None
    fallback_model: str | None = None
    safety_fallback_provider_id: str | None = None
    safety_fallback_model: str | None = None

    @field_validator("provider_id", mode="before")
    @classmethod
    def _coerce_provider_id(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        from app.services.agent.params.providers import normalize_storage_provider_id

        return normalize_storage_provider_id(value)

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class AgentConfigRequest(BaseModel):
    """Agent configuration from frontend (replaces DB-only agent profile)."""

    skill_ids: list[str] = []
    skill_configs: dict[str, dict] | None = None
    enabled_builtin_tools: RequiredBuiltinTools = Field(
        default_factory=lambda: list(DEFAULT_ENABLED_BUILTIN_TOOLS),
    )
    browser_source: str | None = Field(
        default=None, description="Browser acquisition mode (launch/connect/extension/auto/remote)"
    )
    dialog_policy: str | None = Field(
        default=None, description="Dialog handling strategy (smart/auto_accept/auto_dismiss/wait_for_agent)"
    )
    session_recording: str | None = Field(
        default=None, description="Browser session recording mode (off/on_failure/always)"
    )
    auto_restore_domains: list[str] = []
    kanban_default_board_id: str | None = Field(
        default=None,
        description="Chat session target kanban board for LLM tool default_board_id",
    )
    tool_gateway_config: ToolGatewayConfig | None = None

    @field_validator("kanban_default_board_id")
    @classmethod
    def validate_kanban_default_board_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            return None
        if len(trimmed) > 32:
            raise ValueError("kanban_default_board_id must be at most 32 characters")
        return trimmed

    @field_validator("browser_source")
    @classmethod
    def validate_browser_source(cls, v: str | None) -> str | None:
        valid = {"auto", "launch", "connect", "extension", "remote"}
        if v is not None and v not in valid:
            raise ValueError(f"browser_source must be one of {valid}, got '{v}'")
        return v

    @field_validator("dialog_policy")
    @classmethod
    def validate_dialog_policy(cls, v: str | None) -> str | None:
        valid = {"smart", "auto_accept", "auto_dismiss", "wait_for_agent"}
        if v is not None and v not in valid:
            raise ValueError(f"dialog_policy must be one of {valid}, got '{v}'")
        return v

    @field_validator("session_recording")
    @classmethod
    def validate_session_recording(cls, v: str | None) -> str | None:
        valid = {"off", "on_failure", "always"}
        if v is not None and v not in valid:
            raise ValueError(f"session_recording must be one of {valid}, got '{v}'")
        return v

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class GoalBudgetRequest(BaseModel):
    max_tokens: int | None = None
    max_usd: float | None = None
    max_time_seconds: int | None = None
    max_turns: int | None = None
    convergence_window: int | None = None
    loop_on_pause: bool = False
    max_loop_restarts: int = 10
    acceptance_criteria: list[dict[str, object]] | None = None
    constraints: list[str] | None = None
    protected_paths: list[str] | None = None
    ui_summary: str = Field(default="", max_length=120)
    checkpoint_mode: str = "none"

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class MentionReferenceRequest(BaseModel):
    """Structured GUI @ reference selected by the user."""

    type: Literal[
        "workspace_file",
        "workspace_folder",
        "uploaded_file",
        "generated_file",
        "git_diff",
        "git_staged",
        "url",
        "codebase",
        "wiki_concept",
        "wiki_raw_file",
    ]
    path: str | None = Field(None, max_length=4096)
    file_id: str | None = Field(None, max_length=256)
    url: str | None = Field(None, max_length=4096)
    label: str | None = Field(None, max_length=512)
    start_line: int | None = Field(None, ge=1)
    end_line: int | None = Field(None, ge=1)
    concept_name: str | None = Field(None, max_length=512)

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class ArchiveRestoreActionRequest(BaseModel):
    """Typed GUI archive restore action."""

    type: Literal["archive_restore"] = "archive_restore"
    restore_arg: str = Field(..., min_length=1, max_length=4096)

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class AgentRequest(BaseModel):
    """Agent streaming request — backend resolves API keys from DB."""

    message_id: str
    chat_id: str | None = None
    agent_id: str | None = None
    multiplexed: bool = False
    blueprint_id: str | None = None
    ephemeral_subagents: dict[str, object] | None = None
    query: MultimodalQuery = ""
    use_workflow: bool = False
    goal: GoalBudgetRequest | None = None

    model_selection: ModelSelection | None = None
    fallback_model_selection: ModelSelection | None = None
    safety_fallback_model_selection: ModelSelection | None = None
    lite_model_selection: ModelSelection | None = None
    fallback_lite_model_selection: ModelSelection | None = None
    vision_fallback_model_selection: ModelSelection | None = None

    light_model_selection: ModelSelection | None = None
    fallback_light_model_selection: ModelSelection | None = None

    multiplexed: bool = False
    reasoning_model_selection: ModelSelection | None = None
    fallback_reasoning_model_selection: ModelSelection | None = None
    research_model_selection: ModelSelection | None = None

    agent_config: AgentConfigRequest | None = None

    user_instructions: str | None = None
    fetch_raw_webpage: bool = False
    enable_memory: bool = True
    memory_require_confirmation: bool = True
    enable_memory_auto_extraction: bool = True
    enable_conversation_search: bool = False
    incognito_mode: bool = False
    enable_advanced_retrieval: bool = False
    mcp_cfg: list[dict[str, object]] | None = None
    retrieval_dict: dict[str, object] | None = None
    timezone: str | None = None
    action_mode: str = "fast"
    search_depth: str = "normal"
    locale: str | None = None
    force_delegate_agent: str | None = None
    privacy_enabled: bool = False
    privacy_s2_action: str = "redact"
    privacy_s3_action: str = "alert"
    privacy_routing: dict[str, str] | None = None
    privacy_custom_keywords_s2: list[str] | None = None
    privacy_custom_keywords_s3: list[str] | None = None
    privacy_custom_patterns_s2: list[str] | None = None
    privacy_custom_patterns_s3: list[str] | None = None
    privacy_sensitive_tools_s2: list[str] | None = None
    privacy_sensitive_tools_s3: list[str] | None = None
    privacy_deep_scan: bool = False
    code_execution_allow_network: bool | None = None
    sandbox_mode: bool = Field(
        default=False,
        description="When True, agent operates in an isolated git worktree. "
        "Changes are confined to a temporary branch until explicitly merged or discarded.",
    )
    timestamp: float | None = None
    quote: str | None = None

    mention_references: list[MentionReferenceRequest] | None = None
    mentioned_agent_ids: list[str] | None = Field(default=None, description="Explicitly @ mentioned agent IDs")
    uploaded_file_ids: list[str] | None = Field(
        default=None,
        description="IDs of files attached to this message (from drag-and-drop upload). "
        "Large files will be copied to the agent workspace for code execution access.",
    )
    archive_restore_actions: list[ArchiveRestoreActionRequest] | None = None
    engine_params: dict[str, object] | None = None

    resume_value: dict[str, object] | None = None
    sibling_group_id: str | None = None
    regenerate_instruction: str | None = None
    client_surface: str | None = Field(
        default=None,
        description="Client rendering surface for inline A2UI: web, tauri, or headless.",
    )

    class Config:
        alias_generator = to_camel
        populate_by_name = True
