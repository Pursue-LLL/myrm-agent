"""
[POS] app/schemas/introspection_shield.py
[INPUT] pydantic, enum
[OUTPUT] IntrospectionProbeTypeEnum, DecoupledTemplateStandardEnum, ShieldActionEnumResponse, EvaluatePathProbeRequest, EvaluatePathProbeResponse, HydrateTemplatesRequest, HydratedTemplateRecordResponse, HydrateTemplatesResponse, ScaffoldTemplatesRequest, ScaffoldTemplatesResponse, IntrospectionShieldMetricsResponse, BlackholePatternsResponse

Pydantic schemas for Agent Runtime Introspection Shield & Decoupled Workspace Template Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class IntrospectionProbeTypeEnum(StrEnum):
    """Categorized introspection probe vectors."""

    HOST_PATH_PROBE = "HOST_PATH_PROBE"
    SYSTEM_CONFIG_INSPECTION = "SYSTEM_CONFIG_INSPECTION"
    ENVIRONMENT_LEAK_PROBE = "ENVIRONMENT_LEAK_PROBE"
    FRAMEWORK_SOURCE_SNOOPING = "FRAMEWORK_SOURCE_SNOOPING"
    CONTAINER_TOPOLOGY_PROBE = "CONTAINER_TOPOLOGY_PROBE"


class DecoupledTemplateStandardEnum(StrEnum):
    """Standardized decoupled template types."""

    SOUL = "SOUL"
    USER = "USER"
    IDENTITY = "IDENTITY"
    BOOTSTRAP = "BOOTSTRAP"
    HEARTBEAT = "HEARTBEAT"


class ShieldActionEnumResponse(StrEnum):
    """Security action executed by the introspection shield."""

    ALLOW_UNRESTRICTED = "ALLOW_UNRESTRICTED"
    BLOCK_BLACKHOLE = "BLOCK_BLACKHOLE"
    FAKE_ROOT_REDIRECT = "FAKE_ROOT_REDIRECT"
    SANITIZE_MASK = "SANITIZE_MASK"


class EvaluatePathProbeRequest(BaseModel):
    """Payload to evaluate a target path access probe."""

    target_path: str = Field(..., min_length=1, description="Path accessed by agent tool")
    workspace_root: str | None = Field(default=None, description="Current workspace root path")


class EvaluatePathProbeResponse(BaseModel):
    """Security evaluation result for requested path probe."""

    is_blocked: bool = Field(..., description="True if access is intercepted or redirected")
    probe_type: IntrospectionProbeTypeEnum | None = Field(
        default=None, description="Detected probe category"
    )
    attempted_target: str = Field(..., description="Original path attempted")
    action_taken: ShieldActionEnumResponse = Field(..., description="Shield action taken")
    sanitized_path: str = Field(..., description="Sanitized safe or fake path")
    explanation: str = Field(..., description="Security justification")
    timestamp: float = Field(..., description="Evaluation timestamp")


class HydrateTemplatesRequest(BaseModel):
    """Payload to scan and hydrate decoupled templates from a workspace."""

    workspace_dir: str = Field(..., min_length=1, description="Target workspace directory")


class HydratedTemplateRecordResponse(BaseModel):
    """Descriptor of an active decoupled template specification."""

    standard: DecoupledTemplateStandardEnum = Field(..., description="Template standard")
    filename: str = Field(..., description="File name on disk")
    content: str = Field(..., description="Template text content")
    source_path: str = Field(..., description="Absolute path on disk")
    is_active: bool = Field(..., description="True if active")
    character_count: int = Field(..., ge=0, description="Character count")


class HydrateTemplatesResponse(BaseModel):
    """Collection of hydrated decoupled templates and formatted prompt context."""

    templates: list[HydratedTemplateRecordResponse] = Field(
        ..., description="List of discovered templates"
    )
    prompt_context: str = Field(..., description="Unified XML formatted prompt context")
    total_characters: int = Field(..., ge=0, description="Total characters loaded")


class ScaffoldTemplatesRequest(BaseModel):
    """Payload to scaffold default open standards template files."""

    workspace_dir: str = Field(..., min_length=1, description="Target workspace directory")
    overwrite: bool = Field(default=False, description="Whether to overwrite existing files")


class ScaffoldTemplatesResponse(BaseModel):
    """Confirmation of generated workspace template files."""

    workspace_dir: str = Field(..., description="Workspace directory")
    created_files: list[str] = Field(..., description="List of generated file names")


class IntrospectionShieldMetricsResponse(BaseModel):
    """Cumulative operational metrics for introspection shield."""

    probes_evaluated: int = Field(..., ge=0)
    probes_blocked: int = Field(..., ge=0)
    fake_root_redirects: int = Field(..., ge=0)
    templates_hydrated: int = Field(..., ge=0)
    scaffolds_generated: int = Field(..., ge=0)


class BlackholePatternsResponse(BaseModel):
    """Active introspection blackhole patterns."""

    patterns: list[str] = Field(..., description="Active blackhole matching patterns")
    count: int = Field(..., ge=0, description="Pattern count")
