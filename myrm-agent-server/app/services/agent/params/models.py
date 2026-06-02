from __future__ import annotations

import logging
from typing import Literal

from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from pydantic import BaseModel, Field, field_validator
from pydantic.alias_generators import to_camel

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
    enabled_builtin_tools: list[str] = ["web_search", "memory"]
    browser_engine: str | None = Field(default=None, description="Default browser engine (e.g. chromium_patchright, firefox_camoufox)")
    auto_restore_domains: list[str] = []
    tool_gateway_config: ToolGatewayConfig | None = None

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class GoalBudgetRequest(BaseModel):
    max_tokens: int | None = None
    max_usd: float | None = None
    max_time_seconds: int | None = None
    acceptance_criteria: list[dict[str, object]] | None = None
    constraints: list[str] | None = None
    ui_summary: str = Field(default="", max_length=120)

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
    ]
    path: str | None = Field(None, max_length=4096)
    file_id: str | None = Field(None, max_length=256)
    url: str | None = Field(None, max_length=4096)
    label: str | None = Field(None, max_length=512)
    start_line: int | None = Field(None, ge=1)
    end_line: int | None = Field(None, ge=1)

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
    blueprint_id: str | None = None
    ephemeral_subagents: dict[str, object] | None = None
    task_adaptive_digest: dict[str, object] | None = None
    query: MultimodalQuery = ""
    goal: GoalBudgetRequest | None = None

    model_selection: ModelSelection | None = None
    fallback_model_selection: ModelSelection | None = None
    safety_fallback_model_selection: ModelSelection | None = None
    lite_model_selection: ModelSelection | None = None
    fallback_lite_model_selection: ModelSelection | None = None
    vision_fallback_model_selection: ModelSelection | None = None

    light_model_selection: ModelSelection | None = None
    fallback_light_model_selection: ModelSelection | None = None
    reasoning_model_selection: ModelSelection | None = None
    fallback_reasoning_model_selection: ModelSelection | None = None
    research_model_selection: ModelSelection | None = None

    agent_config: AgentConfigRequest | None = None

    user_instructions: str | None = None
    fetch_raw_webpage: bool = False
    enable_memory: bool = True
    memory_require_confirmation: bool = True
    enable_memory_auto_extraction: bool = True
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
    timestamp: float | None = None
    quote: str | None = None

    mention_references: list[MentionReferenceRequest] | None = None
    archive_restore_actions: list[ArchiveRestoreActionRequest] | None = None
    engine_params: dict[str, object] | None = None

    resume_value: dict[str, object] | None = None
    sibling_group_id: str | None = None
    regenerate_instruction: str | None = None

    class Config:
        alias_generator = to_camel
        populate_by_name = True
